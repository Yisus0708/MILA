# language_detector.py — Detección automática de idioma para Mila
import re

# Palabras clave por idioma para detección rápida
_IDIOMAS = {
    "es": [
        "hola", "qué", "que", "cómo", "como", "por", "para", "gracias",
        "abre", "busca", "pon", "dime", "hazme", "puedes", "quiero",
        "necesito", "cuál", "cuánto", "cuando", "donde", "ayuda"
    ],
    "en": [
        "hello", "what", "how", "open", "search", "play", "find", "show",
        "can", "could", "please", "thanks", "help", "where", "when", "why",
        "make", "create", "run", "start", "stop", "get", "set"
    ],
    "pt": [
        "olá", "ola", "como", "abrir", "buscar", "por", "para", "obrigado",
        "preciso", "quero", "pode", "onde", "quando", "ajuda"
    ],
    "fr": [
        "bonjour", "comment", "ouvrir", "chercher", "merci", "aide",
        "pouvoir", "vouloir", "faire", "trouver", "où", "quand"
    ],
    "de": [
        "hallo", "wie", "öffnen", "suchen", "danke", "hilfe",
        "können", "wollen", "machen", "finden", "wo", "wann"
    ],
}

# Nombres completos de los idiomas
_NOMBRES = {
    "es": "Español",
    "en": "English",
    "pt": "Português",
    "fr": "Français",
    "de": "Deutsch",
}


def detectar_idioma(texto: str) -> str:
    # Convertimos el texto a minúsculas para comparar
    texto_lower = texto.lower().strip()
    palabras    = re.findall(r'\b\w+\b', texto_lower)

    if not palabras:
        return "es"  # Español por defecto

    # Contamos coincidencias por idioma
    puntuaciones = {}
    for codigo, keywords in _IDIOMAS.items():
        puntuacion = sum(1 for p in palabras if p in keywords)
        if puntuacion > 0:
            puntuaciones[codigo] = puntuacion

    if not puntuaciones:
        return "es"  # Si no detectamos nada, español por defecto

    # Devolvemos el idioma con más coincidencias
    return max(puntuaciones, key=puntuaciones.get)


def obtener_nombre_idioma(codigo: str) -> str:
    # Devolvemos el nombre completo del idioma
    return _NOMBRES.get(codigo, "Español")


def es_mismo_idioma(texto1: str, texto2: str) -> bool:
    # Verificamos si dos textos están en el mismo idioma
    return detectar_idioma(texto1) == detectar_idioma(texto2)
