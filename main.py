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

@app.route('/api/crear_trampa', methods=['POST'])
def crear_trampa():
    data = request.json
    nombre = data.get('nombre', 'Trampa Sin Nombre')
    token = generar_token()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO trampas (token, nombre) VALUES (%s, %s)", (token, nombre))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({"status": "ok", "link": f"{request.host_url}s/{token}"})

@app.route('/s/<token>')
def trampa_activada(token):
    # 1. Obtener IP Real
    ip_victima = request.headers.get('X-Forwarded-For', request.remote_addr)
    # Si hay varias IPs, tomamos la primera (la real)
    if ip_victima and ',' in ip_victima:
        ip_victima = ip_victima.split(',')[0].strip()
        
    user_agent = request.headers.get('User-Agent')
    
    # 2. RASTREO SATELITAL (GEO)
    ubicacion = obtener_ubicacion(ip_victima)
    print(f"⚠️ INTRUSO: {ip_victima} desde {ubicacion}")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM trampas WHERE token = %s", (token,))
    trampa = cur.fetchone()
    
    if trampa:
        trampa_id = trampa[0]
        # Guardamos también la CIUDAD en la base de datos
        cur.execute(
            "INSERT INTO intrusos (trampa_id, ip_address, user_agent, city) VALUES (%s, %s, %s, %s)",
            (trampa_id, ip_victima, user_agent, ubicacion)
        )
        conn.commit()
    
    cur.close()
    conn.close()

    return redirect("https://www.google.com/error?code=404")

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)