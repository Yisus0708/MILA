 #!/usr/bin/env python3
"""
🔄 MILA — Script de Actualización Inteligente
Verifica compatibilidad antes de actualizar cada librería
"""

import sys
import subprocess
import json
from pathlib import Path

# Colores para la terminal
VERDE   = "\033[92m"
AMARILLO = "\033[93m"
ROJO    = "\033[91m"
AZUL    = "\033[94m"
RESET   = "\033[0m"
NEGRITA = "\033[1m"

def log_ok(msg):      print(f"{VERDE}✅ {msg}{RESET}")
def log_warn(msg):    print(f"{AMARILLO}⚠️  {msg}{RESET}")
def log_error(msg):   print(f"{ROJO}❌ {msg}{RESET}")
def log_info(msg):    print(f"{AZUL}ℹ️  {msg}{RESET}")
def log_titulo(msg):  print(f"\n{NEGRITA}{AZUL}{msg}{RESET}\n")

def verificar_python():
    # Verificamos que la versión de Python sea compatible con Mila
    version = sys.version_info
    log_info(f"Python detectado: {version.major}.{version.minor}.{version.micro}")
    
    if version.major != 3:
        log_error("Mila requiere Python 3. Por favor instala Python 3.11 o 3.12.")
        sys.exit(1)
    
    if version.minor < 10:
        log_error(f"Python {version.minor} es demasiado antiguo. Mila requiere 3.10 o superior.")
        sys.exit(1)
    
    if version.minor > 12:
        log_warn(f"Python {version.minor} es muy nuevo y puede causar problemas. Se recomienda 3.11 o 3.12.")
    else:
        log_ok(f"Python {version.minor} es compatible con Mila.")

def obtener_version_instalada(paquete: str) -> str | None:
    # Obtenemos la versión actual instalada de un paquete
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", paquete],
            capture_output=True, text=True
        )
        for linea in result.stdout.splitlines():
            if linea.startswith("Version:"):
                return linea.split(":", 1)[1].strip()
    except Exception:
        pass
    return None

def obtener_version_disponible(paquete: str) -> str | None:
    # Consultamos la última versión disponible en PyPI
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", paquete],
            capture_output=True, text=True
        )
        # Extraemos la primera versión de la lista
        for linea in result.stdout.splitlines():
            if "Available versions:" in linea:
                versiones = linea.split(":", 1)[1].strip()
                return versiones.split(",")[0].strip()
    except Exception:
        pass
    return None

def verificar_compatibilidad(paquete: str, version_nueva: str) -> bool:
    # Verificamos si la nueva versión es compatible antes de instalar
    # Librerías críticas que necesitan versiones específicas
    restricciones = {
        "PyQt6":        (6, 4),   # Mínimo PyQt6 6.4
        "sounddevice":  (0, 4),   # Mínimo sounddevice 0.4
        "google-genai": (1, 0),   # Mínimo google-genai 1.0
        "playwright":   (1, 40),  # Mínimo playwright 1.40
    }

    if paquete not in restricciones:
        return True

    try:
        # Parseamos la versión mayor y menor
        partes = version_nueva.split(".")
        mayor  = int(partes[0]) if len(partes) > 0 else 0
        menor  = int(partes[1]) if len(partes) > 1 else 0

        min_mayor, min_menor = restricciones[paquete]

        # Verificamos que la versión cumpla el mínimo requerido
        if mayor < min_mayor or (mayor == min_mayor and menor < min_menor):
            log_warn(f"{paquete} {version_nueva} puede ser demasiado antigua. Mínimo recomendado: {min_mayor}.{min_menor}")
            return False
    except Exception:
        pass

    return True

def hacer_backup_requirements():
    # Hacemos una copia de seguridad del requirements.txt antes de actualizar
    req_path    = Path("requirements.txt")
    backup_path = Path("requirements.backup.txt")

    if req_path.exists():
        backup_path.write_text(req_path.read_text(encoding="utf-8"), encoding="utf-8")
        log_ok(f"Backup guardado en: {backup_path}")
    else:
        log_warn("No se encontró requirements.txt")

def actualizar_paquete(paquete: str) -> bool:
    # Actualizamos un paquete específico verificando compatibilidad primero
    version_actual    = obtener_version_instalada(paquete)
    version_disponible = obtener_version_disponible(paquete)

    if not version_actual:
        log_warn(f"{paquete} no está instalado. Instalando...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", paquete, "-q"],
                check=True
            )
            log_ok(f"{paquete} instalado correctamente.")
            return True
        except Exception as e:
            log_error(f"No se pudo instalar {paquete}: {e}")
            return False

    if not version_disponible:
        log_warn(f"No se pudo consultar la versión disponible de {paquete}. Omitiendo.")
        return False

    # Comparamos versiones para ver si hay actualización disponible
    if version_actual == version_disponible:
        log_ok(f"{paquete} ya está actualizado ({version_actual})")
        return True

    # Verificamos compatibilidad antes de actualizar
    if not verificar_compatibilidad(paquete, version_disponible):
        log_warn(f"Omitiendo actualización de {paquete} por posible incompatibilidad.")
        return False

    # Procedemos con la actualización
    log_info(f"Actualizando {paquete}: {version_actual} → {version_disponible}")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", paquete, "-q"],
            check=True
        )
        log_ok(f"{paquete} actualizado a {version_disponible}")
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"Error al actualizar {paquete}: {e}")
        return False

def leer_requirements() -> list[str]:
    # Leemos los paquetes del archivo requirements.txt
    req_path = Path("requirements.txt")
    if not req_path.exists():
        log_error("No se encontró requirements.txt")
        return []

    paquetes = []
    for linea in req_path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        # Ignoramos comentarios y líneas vacías
        if linea and not linea.startswith("#"):
            # Extraemos solo el nombre del paquete sin versión
            nombre = linea.split(">=")[0].split("==")[0].split("<=")[0].split("~=")[0].strip()
            paquetes.append(nombre)

    return paquetes

def main():
    log_titulo("🤖 MILA — Actualizador Inteligente de Dependencias")

    # Verificamos Python primero
    verificar_python()

    # Hacemos backup antes de cualquier cambio
    log_titulo("📦 Creando backup de requirements.txt...")
    hacer_backup_requirements()

    # Leemos los paquetes a actualizar
    paquetes = leer_requirements()
    if not paquetes:
        log_error("No hay paquetes para actualizar.")
        sys.exit(1)

    log_titulo(f"🔍 Verificando {len(paquetes)} dependencias...")

    # Actualizamos cada paquete
    exitosos  = 0
    fallidos  = 0
    omitidos  = 0

    for paquete in paquetes:
        print(f"\n{AZUL}→ {paquete}{RESET}")
        resultado = actualizar_paquete(paquete)
        if resultado:
            exitosos += 1
        else:
            fallidos += 1

    # Resumen final
    log_titulo("📊 Resumen de actualización")
    log_ok(f"Exitosos:  {exitosos}")
    if fallidos:
        log_error(f"Fallidos:  {fallidos}")
    log_info(f"Total:     {len(paquetes)}")

    if fallidos == 0:
        print(f"\n{VERDE}{NEGRITA}✅ Todas las dependencias están al día. Mila lista para usar.{RESET}\n")
    else:
        print(f"\n{AMARILLO}{NEGRITA}⚠️  Algunas dependencias no se pudieron actualizar. Revisa los errores arriba.{RESET}\n")
        print(f"{AZUL}Si algo falla, restaura el backup con:{RESET}")
        print(f"  pip install -r requirements.backup.txt\n")

if __name__ == "__main__":
    main()
