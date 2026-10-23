import subprocess
import sys
import json
import re
import time
import shutil
import platform
from pathlib import Path

# Directorio base del proyecto
def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
MAX_INTENTOS    = 3
MODELO_GEMINI   = "gemini-2.5-flash"

# Extensiones de archivo por lenguaje
EXTENSIONES = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "bash": ".sh", "shell": ".sh",
    "powershell": ".ps1",
    "html": ".html", "css": ".css",
    "java": ".java", "cpp": ".cpp",
    "c": ".c", "rust": ".rs", "go": ".go",
}

# Intérpretes por extensión de archivo
INTERPRETES = {
    ".py":  [sys.executable],
    ".js":  ["node"],
    ".ts":  ["ts-node"],
    ".sh":  ["bash"],
    ".ps1": ["powershell", "-File"],
    ".rb":  ["ruby"],
    ".php": ["php"],
    ".go":  ["go", "run"],
}


def _leer_api_key() -> str:
    # Leemos la API Key desde el archivo de configuración
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _obtener_modelo():
    # Inicializamos el cliente de Gemini
    from google import genai
    return genai.Client(api_key=_leer_api_key())


def _limpiar_codigo(texto: str) -> str:
    # Eliminamos bloques de markdown del código generado
    texto = texto.strip()
    texto = re.sub(r"^```[a-zA-Z]*\n?", "", texto)
    texto = re.sub(r"\n?```$", "", texto)
    return texto.strip()


def _resolver_ruta(nombre: str, lenguaje: str) -> Path:
    # Siempre guardamos en el escritorio del usuario
    ext        = EXTENSIONES.get((lenguaje or "python").lower(), ".py")
    escritorio = Path.home() / "Desktop"

    if nombre:
        p = Path(nombre)
        # Si no tiene extensión la agregamos
        if not p.suffix:
            p = p.with_suffix(ext)
        # Siempre forzamos que quede en el escritorio
        return escritorio / p.name

    # Nombre por defecto con timestamp para no sobreescribir
    timestamp = int(time.time())
    return escritorio / f"mila_{timestamp}{ext}"


def _tiene_error(salida: str) -> bool:
    # Detectamos señales de error en la salida
    señales = [
        "error", "exception", "traceback", "syntaxerror",
        "nameerror", "typeerror", "importerror", "valueerror",
        "attributeerror", "indexerror", "keyerror", "stderr",
        "failed", "crash", "killed", "segfault"
    ]
    return any(s in salida.lower() for s in señales)


def _ejecutar_archivo(ruta: Path, args: list, timeout: int) -> tuple:
    # Ejecutamos el archivo y retornamos (salida, hubo_error)
    interprete = INTERPRETES.get(ruta.suffix.lower())
    if not interprete:
        return f"No hay intérprete para archivos {ruta.suffix}.", True

    try:
        resultado = subprocess.run(
            interprete + [str(ruta)] + (args or []),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(ruta.parent)
        )

        salida  = resultado.stdout.strip()
        errores = resultado.stderr.strip()

        partes = []
        if salida:   partes.append(f"📤 Salida:\n{salida}")
        if errores:  partes.append(f"⚠️ Stderr:\n{errores}")
        salida_completa = "\n\n".join(partes) if partes else "✅ Ejecutado sin salida."

        hubo_error = resultado.returncode != 0 or _tiene_error(errores)
        return salida_completa, hubo_error

    except subprocess.TimeoutExpired:
        return f"⏱️ Tiempo agotado después de {timeout}s.", True
    except FileNotFoundError:
        return f"❌ Intérprete no encontrado: {interprete[0]}", True
    except Exception as e:
        return f"❌ Error de ejecución: {e}", True


def _abrir_en_vscode(ruta: Path) -> bool:
    # Abrimos el archivo generado en Visual Studio Code automáticamente
    sistema = platform.system()

    # Candidatos de ejecutable según el sistema operativo
    if sistema == "Windows":
        candidatos = ["code", "code.cmd"]
    elif sistema == "Darwin":
        candidatos = ["code", "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"]
    else:
        # Linux/Ubuntu
        candidatos = ["code", "code-oss", "codium"]

    # Intentamos abrir con cada candidato disponible
    for cmd in candidatos:
        if shutil.which(cmd):
            try:
                subprocess.Popen(
                    [cmd, str(ruta)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print(f"[CodeRunner] 🖥️  Abierto en VSCode: {ruta}")
                return True
            except Exception as e:
                print(f"[CodeRunner] ⚠️ Error con {cmd}: {e}")

    print("[CodeRunner] ⚠️ VSCode no encontrado.")
    return False


def _generar_codigo(descripcion: str, lenguaje: str) -> str:
    # Generamos el código inicial con Gemini
    cliente = _obtener_modelo()

    prompt = f"""Eres un experto desarrollador de {lenguaje}.
Escribe código {lenguaje} limpio y funcional para lo siguiente:

{descripcion}

REGLAS ESTRICTAS:
- Responde ÚNICAMENTE con el código. Sin explicaciones, sin markdown, sin backticks.
- El código debe ser ejecutable directamente.
- Agrega comentarios inline útiles en español.
- Maneja errores y casos extremos.
- Usa las mejores prácticas modernas de {lenguaje}.

Código:"""

    respuesta = cliente.models.generate_content(
        model=MODELO_GEMINI,
        contents=prompt
    )
    return _limpiar_codigo(respuesta.text)


def _corregir_codigo(codigo: str, error: str, descripcion: str, intento: int) -> str:
    # Pedimos a Gemini que corrija el código basándose en el error
    cliente = _obtener_modelo()

    prompt = f"""Eres un experto debugger. El siguiente código falló con un error.
Corrígelo. Responde ÚNICAMENTE con el código corregido — sin explicaciones, sin markdown.

Objetivo original: {descripcion}

Error (intento {intento}):
{error[:3000]}

Código con error:
{codigo}

Código corregido:"""

    respuesta = cliente.models.generate_content(
        model=MODELO_GEMINI,
        contents=prompt
    )
    return _limpiar_codigo(respuesta.text)


def _guardar_codigo(ruta: Path, codigo: str) -> None:
    # Guardamos el código en el escritorio
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(codigo, encoding="utf-8")


def _preview_codigo(codigo: str, max_lineas: int = 15) -> str:
    # Mostramos las primeras líneas del código como preview
    lineas  = codigo.splitlines()
    preview = "\n".join(lineas[:max_lineas])
    if len(lineas) > max_lineas:
        preview += f"\n... ({len(lineas) - max_lineas} líneas más)"
    return preview


def code_runner(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None
) -> str:
    """
    Genera código, lo ejecuta y se autocorrige hasta 3 veces.
    Guarda en el escritorio y abre automáticamente en VSCode.
    """
    p           = parameters or {}
    descripcion = p.get("description", "").strip()
    lenguaje    = p.get("language", "python").strip().lower()
    ruta_salida = p.get("output_path", "").strip()
    args        = p.get("args", [])
    timeout     = int(p.get("timeout", 30))

    # Validamos que haya una descripción
    if not descripcion:
        return "Por favor dime qué código quieres que genere."

    if player:
        player.write_log(f"[CodeRunner] Iniciando: {descripcion[:50]}...")

    print(f"[CodeRunner] 🚀 Generando {lenguaje}: {descripcion[:60]}")

    # Resolvemos la ruta — siempre en el escritorio
    ruta = _resolver_ruta(ruta_salida, lenguaje)

    # ── FASE 1: Generamos el código ──
    try:
        print("[CodeRunner] 🤖 Generando con Gemini...")
        codigo = _generar_codigo(descripcion, lenguaje)
        _guardar_codigo(ruta, codigo)
        print(f"[CodeRunner] ✅ Guardado en escritorio: {ruta.name}")
    except Exception as e:
        return f"❌ No pude generar el código: {e}"

    # ── FASE 2: Loop ejecutar → corregir ──
    ultima_salida = ""
    for intento in range(1, MAX_INTENTOS + 1):
        print(f"[CodeRunner] ▶️  Ejecutando intento {intento}/{MAX_INTENTOS}...")

        if player:
            player.write_log(f"[CodeRunner] Ejecutando intento {intento}...")

        ultima_salida, hubo_error = _ejecutar_archivo(ruta, args, timeout)

        # ── Sin errores: éxito ──
        if not hubo_error:
            veces = f"{intento} intento" if intento == 1 else f"{intento} intentos"

            if player:
                player.write_log(f"[CodeRunner] ✅ Éxito en intento {intento}")

            # Abrimos en VSCode automáticamente
            abierto_en_vscode = _abrir_en_vscode(ruta)
            vscode_msg        = "Abierto en VSCode ✅" if abierto_en_vscode else "VSCode no encontrado ⚠️"

            return (
                f"✅ Código funcionando después de {veces}.\n"
                f"📁 Guardado en escritorio: {ruta.name}\n"
                f"🖥️  {vscode_msg}\n\n"
                f"{'─'*40}\n"
                f"📋 Preview:\n{_preview_codigo(codigo)}\n\n"
                f"{'─'*40}\n"
                f"{ultima_salida}"
            )

        print(f"[CodeRunner] ⚠️ Error intento {intento}, corrigiendo...")

        # Corregimos si no es el último intento
        if intento < MAX_INTENTOS:
            try:
                codigo = _corregir_codigo(codigo, ultima_salida, descripcion, intento)
                _guardar_codigo(ruta, codigo)
            except Exception as e:
                return f"❌ Error al corregir: {e}"

    # ── Agotamos los intentos: abrimos igual en VSCode para que lo vea ──
    if player:
        player.write_log(f"[CodeRunner] ❌ Falló tras {MAX_INTENTOS} intentos")

    # Abrimos el último intento en VSCode para que el usuario lo revise
    abierto_en_vscode = _abrir_en_vscode(ruta)
    vscode_msg        = "Abierto en VSCode para que lo revises ✅" if abierto_en_vscode else "VSCode no encontrado ⚠️"

    return (
        f"❌ No logré hacerlo funcionar tras {MAX_INTENTOS} intentos.\n"
        f"📁 Último intento en escritorio: {ruta.name}\n"
        f"🖥️  {vscode_msg}\n\n"
        f"{'─'*40}\n"
        f"📋 Último código:\n{_preview_codigo(codigo)}\n\n"
        f"{'─'*40}\n"
        f"⚠️ Último error:\n{ultima_salida[:500]}"
    )
