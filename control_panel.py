import requests
import os
import time

# --- CONFIGURACIÓN ---
# Aquí está tu servidor real en la nube:
SERVER_URL = "https://honeypot-cloud-production.up.railway.app" 
# ---------------------

def limpiar():
    # Limpia la pantalla para que se vea hacker
    os.system('cls' if os.name == 'nt' else 'clear')

def crear_trampa():
    print("\n--- 🕸️  GENERANDO NUEVA TRAMPA ---")
    nombre = input("Nombre para esta trampa (ej: 'Fotos Fiesta'): ")
    
    try:
        # Enviamos la orden al servidor en Railway
        response = requests.post(f"{SERVER_URL}/api/crear_trampa", json={"nombre": nombre})
        
        if response.status_code == 200:
            data = response.json()
            link = data['link']
            print("\n" + "█" * 60)
            print(f"✅ TRAMPA CREADA EXITOSAMENTE")
            print(f"🔗 ENLACE MALICIOSO: {link}")
            print("█" * 60)
            print("   (Copia este link y envíaselo a tu objetivo)")
        else:
            print("❌ El servidor respondió con error.")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        print("   (Verifica que Railway esté en VERDE)")
    input("\nPresiona Enter para volver...")

def ver_ataques():
    print("\n--- 🕵️‍♂️  BUSCANDO INTRUSOS ---")
    try:
        response = requests.get(f"{SERVER_URL}/api/ver_ataques")
        ataques = response.json()
        
        if not ataques:
            print("\n   💤 Nadie ha caído en la trampa todavía.")
        else:
            print(f"\n   🚨 SE HAN DETECTADO {len(ataques)} INTRUSIONES:\n")
            print(f"   {'HORA':<20} | {'TRAMPA':<15} | {'IP DEL INTRUSO'}")
            print("   " + "-"*65)
            
            for a in ataques:
                print(f"   {a['hora']:<20} | {a['trampa']:<15} | {a['ip']}")
                # Detectamos el tipo de dispositivo
                if "iPhone" in a['dispositivo']:
                    print(f"   ╚═ 📱 Dispositivo: iPhone")
                elif "Android" in a['dispositivo']:
                    print(f"   ╚═ 📱 Dispositivo: Android")
                elif "Windows" in a['dispositivo']:
                    print(f"   ╚═ 💻 Dispositivo: Windows PC")
                else:
                    print(f"   ╚═ ❓ Dispositivo: {a['dispositivo'][:30]}...")
                print("")
                
    except Exception as e:
        print(f"Error conectando al servidor: {e}")
    input("\nPresiona Enter para volver...")

# --- MENÚ PRINCIPAL ---
while True:
    limpiar()
    print("""
    ╔══════════════════════════════════════╗
    ║      🕵️‍♂️  HONEYPOT CLOUD C&C        ║
    ║      Centro de Mando y Control       ║
    ╚══════════════════════════════════════╝
    """)
    print(f"📡 CONECTADO A: {SERVER_URL}")
    print("-" * 40)
    print("1. 🔗 Crear Link Trampa")
    print("2. 👁️  Ver Intrusos (Logs)")
    print("3. 🚪 Salir")
    
    opcion = input("\nElige una opción: ")
    
    if opcion == '1':
        crear_trampa()
    elif opcion == '2':
        ver_ataques()
    elif opcion == '3':
        break