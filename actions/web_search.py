import json
import sys
from pathlib import Path

# Función para obtener el directorio base del proyecto
def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    # Leemos la clave de API desde el archivo de configuración
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _gemini_search(query: str) -> str:
    # Usamos Gemini con búsqueda de Google integrada
    from google import genai

    client   = genai.Client(api_key=_get_api_key())
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=query,
        config={"tools": [{"google_search": {}}]},
    )

    # Extraemos el texto de todos los bloques de la respuesta
    text = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            text += part.text

    text = text.strip()
    if not text:
        raise ValueError("Gemini devolvió una respuesta vacía.")
    return text


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    # Buscamos usando DuckDuckGo como alternativa a Gemini
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title":   r.get("title",  ""),
                "snippet": r.get("body",   ""),
                "url":     r.get("href",   ""),
            })
    return results


def _format_ddg(query: str, results: list[dict]) -> str:
    # Formateamos los resultados de DuckDuckGo en texto legible
    if not results:
        return f"No se encontraron resultados para: {query}"

    lines = [f"Resultados para: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):   lines.append(f"{i}. {r['title']}")
        if r.get("snippet"): lines.append(f"   {r['snippet']}")
        if r.get("url"):     lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()

def _compare(items: list[str], aspect: str) -> str:
    # Construimos una consulta de comparación entre múltiples elementos
    query = (
        f"Compara {', '.join(items)} en términos de {aspect}. "
        "Da hechos y datos específicos."
    )
    try:
        return _gemini_search(query)
    except Exception as e:
        print(f"[WebSearch] ⚠️ Gemini falló en comparación: {e} — usando DDG")

    # Fallback: buscamos cada elemento por separado con DuckDuckGo
    all_results: dict[str, list] = {}
    for item in items:
        try:
            all_results[item] = _ddg_search(f"{item} {aspect}", max_results=3)
        except Exception:
            all_results[item] = []

    lines = [f"Comparación — {aspect.upper()}", "─" * 40]
    for item in items:
        lines.append(f"\n▸ {item}")
        for r in all_results.get(item, [])[:2]:
            if r.get("snippet"):
                lines.append(f"  • {r['snippet']}")
    return "\n".join(lines)

def web_search(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    # Extraemos los parámetros de búsqueda
    params = parameters or {}
    query  = params.get("query", "").strip()
    mode   = params.get("mode",  "search").lower().strip()
    items  = params.get("items", [])
    aspect = params.get("aspect", "general").strip() or "general"

    if not query and not items:
        return "Por favor proporciona una consulta de búsqueda."

    # Si hay elementos para comparar, forzamos el modo comparación
    if items and mode != "compare":
        mode = "compare"

    if player:
        player.write_log(f"[Búsqueda] {query or ', '.join(items)}")

    print(f"[WebSearch] 🔍 Consulta: {query!r}  Modo: {mode}")

    try:
        # Modo comparación: comparamos múltiples elementos
        if mode == "compare" and items:
            print(f"[WebSearch] 📊 Comparando: {items}")
            result = _compare(items, aspect)
            print("[WebSearch] ✅ Comparación lista.")
            return result

        # Intentamos primero con Gemini
        print("[WebSearch] 🌐 Intentando con Gemini...")
        try:
            result = _gemini_search(query)
            print("[WebSearch] ✅ Gemini OK.")
            return result
        except Exception as e:
            # Si Gemini falla, usamos DuckDuckGo como respaldo
            print(f"[WebSearch] ⚠️ Gemini falló ({e}) — intentando con DDG...")
            results = _ddg_search(query)
            result  = _format_ddg(query, results)
            print(f"[WebSearch] ✅ DDG: {len(results)} resultado(s).")
            return result

    except Exception as e:
        print(f"[WebSearch] ❌ Todos los backends fallaron: {e}")
        return f"Búsqueda fallida: {e}"
