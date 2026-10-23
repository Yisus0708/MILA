import json
import sys
import time
import shutil
import subprocess
import platform
from pathlib import Path

# Directorio base del proyecto
def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# Modelo de generación de imágenes de Google (Nano Banana 2)
MODELO_IMAGEN = "gemini-3.1-flash-image-preview"


def _leer_api_key() -> str:
    # Leemos la API Key desde el archivo de configuración
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _resolver_ruta(nombre: str) -> Path:
    # Siempre guardamos las imágenes en el escritorio
    escritorio = Path.home() / "Desktop"
    escritorio.mkdir(parents=True, exist_ok=True)

    if nombre:
        p = Path(nombre)
        # Aseguramos extensión .png
        if not p.suffix:
            p = p.with_suffix(".png")
        return escritorio / p.name

    # Nombre por defecto con timestamp
    timestamp = int(time.time())
    return escritorio / f"mila_imagen_{timestamp}.png"


def _abrir_imagen(ruta: Path) -> bool:
    # Abrimos la imagen generada automáticamente según el SO
    sistema = platform.system()

    try:
        if sistema == "Windows":
            subprocess.Popen(["start", str(ruta)], shell=True)
        elif sistema == "Darwin":
            subprocess.Popen(["open", str(ruta)])
        else:
            # Linux — intentamos varios visores
            for visor in ["eog", "feh", "display", "xdg-open"]:
                if shutil.which(visor):
                    subprocess.Popen([visor, str(ruta)],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    break
        print(f"[ImageGen] 🖼️  Imagen abierta: {ruta.name}")
        return True
    except Exception as e:
        print(f"[ImageGen] ⚠️ No pude abrir la imagen: {e}")
        return False


def _abrir_en_vscode(ruta: Path) -> bool:
    # Abrimos la imagen en VSCode como alternativa
    sistema = platform.system()
    candidatos = {
        "Windows": ["code", "code.cmd"],
        "Darwin":  ["code"],
        "Linux":   ["code", "code-oss", "codium"],
    }.get(sistema, ["code"])

    for cmd in candidatos:
        if shutil.which(cmd):
            try:
                subprocess.Popen(
                    [cmd, str(ruta)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True
            except Exception:
                pass
    return False


def image_generator(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None
) -> str:
    """
    Genera imágenes usando Gemini 3.1 Flash Image (Nano Banana 2).
    Guarda en el escritorio y abre automáticamente.

    Parámetros:
        prompt      : Descripción de la imagen a generar
        output_path : Nombre del archivo (opcional)
        image_size  : Tamaño: 512, 1K, 2K, 4K (default: 1K)
        image_path  : Ruta a imagen existente para editar (opcional)
    """
    p           = parameters or {}
    prompt      = p.get("prompt", "").strip()
    ruta_salida = p.get("output_path", "").strip()
    tamaño      = p.get("image_size", "1K").strip()
    imagen_base = p.get("image_path", "").strip()

    # Validamos que haya un prompt
    if not prompt:
        return "Por favor dime qué imagen quieres que genere."

    if player:
        player.write_log(f"[ImageGen] Generando: {prompt[:50]}...")

    print(f"[ImageGen] 🎨 Generando imagen: {prompt[:60]}")

    # Resolvemos la ruta de guardado
    ruta = _resolver_ruta(ruta_salida)

    try:
        from google import genai
        from google.genai import types
        from PIL import Image as PILImage
        import io

        # Inicializamos el cliente de Gemini
        cliente = genai.Client(api_key=_leer_api_key())

        # Construimos el contenido del prompt
        contenido = [prompt]

        # Si hay imagen base para editar, la cargamos
        if imagen_base:
            base_path = Path(imagen_base)
            if base_path.exists():
                img = PILImage.open(base_path)
                contenido.append(img)
                print(f"[ImageGen] 📎 Editando imagen base: {base_path.name}")
            else:
                print(f"[ImageGen] ⚠️ Imagen base no encontrada: {imagen_base}")

        print(f"[ImageGen] 🤖 Llamando a {MODELO_IMAGEN}...")

        # Llamamos al modelo de generación de imágenes
        respuesta = cliente.models.generate_content(
            model=MODELO_IMAGEN,
            contents=contenido,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                image_config=types.ImageConfig(image_size=tamaño)
            )
        )

        # Buscamos la imagen en la respuesta
        imagen_guardada = False
        for parte in respuesta.candidates[0].content.parts:
            if parte.inline_data is not None:
                # Guardamos la imagen en el escritorio
                imagen = parte.as_image()
                imagen.save(str(ruta), format="PNG")
                imagen_guardada = True
                print(f"[ImageGen] ✅ Imagen guardada: {ruta.name}")
                break

        if not imagen_guardada:
            return "❌ Gemini no devolvió ninguna imagen. Intenta con otro prompt."

        # Abrimos la imagen automáticamente
        abierta = _abrir_imagen(ruta)
        if not abierta:
            # Como respaldo intentamos con VSCode
            _abrir_en_vscode(ruta)

        if player:
            player.write_log(f"[ImageGen] ✅ Imagen lista: {ruta.name}")

        return (
            f"✅ Imagen generada exitosamente.\n"
            f"📁 Guardada en escritorio: {ruta.name}\n"
            f"🎨 Prompt: {prompt}\n"
            f"📐 Tamaño: {tamaño}"
        )

    except ImportError as e:
        # Falta Pillow
        if "PIL" in str(e) or "pillow" in str(e).lower():
            return (
                "❌ Falta instalar Pillow. Ejecuta:\n"
                "pip install Pillow --break-system-packages"
            )
        return f"❌ Error de importación: {e}"

    except Exception as e:
        error_str = str(e).lower()

        # Error de cuota — plan gratuito no soporta generación de imágenes
        if "429" in str(e) or "quota" in error_str or "exceeded" in error_str:
            return (
                "❌ Tu plan gratuito de Gemini no incluye generación de imágenes.\n"
                "Para usar esta función necesitas activar facturación en:\n"
                "https://aistudio.google.com → Billing"
            )

        # Modelo no disponible
        if "404" in str(e) or "not found" in error_str:
            return (
                "❌ El modelo de imágenes no está disponible en tu región o cuenta.\n"
                "Verifica en: https://aistudio.google.com"
            )

        print(f"[ImageGen] ❌ Error: {e}")
        return f"❌ Error al generar imagen: {e}"
