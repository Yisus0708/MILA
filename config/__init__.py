# config/__init__.py
import json
import platform
from pathlib import Path

# Ruta al archivo de configuración con la API Key
_CONFIG_PATH = Path(__file__).parent / "api_keys.json"

def get_config() -> dict:
    # Leemos el archivo de configuración
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_os() -> str:
    # Detectamos el sistema operativo automáticamente
    system = platform.system().lower()

    # Mapeamos el nombre del SO al formato que usa Mila
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "mac"
    elif system == "linux":
        return "linux"
    
    # Si no reconocemos el SO, usamos el del archivo de config como respaldo
    return get_config().get("os_system", "windows").lower()

# Funciones de conveniencia para verificar el sistema operativo
def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"
