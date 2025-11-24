import os
import random
import string
from flask import Flask, request, jsonify, redirect
from datetime import datetime
import psycopg2 

app = Flask(__name__)

# --- CONEXIÓN A LA BASE DE DATOS ---
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    # Si estamos en local y no hay URL, avisamos (pero no fallamos al importar)
    if not DATABASE_URL:
        return None
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- INICIALIZADOR DE TABLAS (MIGRACIÓN AUTOMÁTICA) ---
def inicializar_db():
    try:
        conn = get_db_connection()
        if conn is None:
            print("⚠️ No hay base de datos conectada aún (Localhost).")
            return

        cur = conn.cursor()
        
        # Crear Tabla Trampas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trampas (
                id SERIAL PRIMARY KEY,
                token VARCHAR(50) UNIQUE NOT NULL,
                nombre VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Crear Tabla Intrusos
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
        print("✅ Base de datos inicializada y tablas listas.")
    except Exception as e:
        print(f"❌ Error iniciando DB: {e}")

# --- LÓGICA DEL SISTEMA ---
def generar_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

@app.route('/')
def home():
    return "<h1>🛡️ HONEYPOT SYSTEM ONLINE</h1><p>Status: Active & Listening...</p>"

# RUTA 1: CREAR TRAMPA
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
    
    host_url = request.host_url
    # Eliminamos el http:// para que se vea más limpio si quieres
    return jsonify({"status": "ok", "link": f"{host_url}s/{token}"})

# RUTA 2: LA TRAMPA (Captura de datos)
@app.route('/s/<token>')
def trampa_activada(token):
    ip_victima = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM trampas WHERE token = %s", (token,))
    trampa = cur.fetchone()
    
    if trampa:
        trampa_id = trampa[0]
        print(f"⚠️ INTRUSO DETECTADO: {ip_victima}")
        cur.execute(
            "INSERT INTO intrusos (trampa_id, ip_address, user_agent) VALUES (%s, %s, %s)",
            (trampa_id, ip_victima, user_agent)
        )
        conn.commit()
    
    cur.close()
    conn.close()

    # Redirección de engaño (Google Error)
    return redirect("https://www.google.com/error?code=404")

# RUTA 3: DASHBOARD (Ver ataques)
@app.route('/api/ver_ataques', methods=['GET'])
def ver_ataques():
    conn = get_db_connection()
    cur = conn.cursor()
    query = """
        SELECT t.nombre, i.ip_address, i.captured_at, i.user_agent 
        FROM intrusos i
        JOIN trampas t ON i.trampa_id = t.id
        ORDER BY i.captured_at DESC LIMIT 50
    """
    cur.execute(query)
    ataques = cur.fetchall()
    cur.close()
    conn.close()
    
    resultado = []
    for a in ataques:
        resultado.append({
            "trampa": a[0],
            "ip": a[1],
            "hora": a[2].strftime("%Y-%m-%d %H:%M:%S"),
            "dispositivo": a[3]
        })
        
    return jsonify(resultado)

# EJECUTAR INICIALIZACIÓN AL ARRANCAR
inicializar_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)