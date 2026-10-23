import webbrowser
from urllib.parse import quote_plus


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    # Obtenemos la ciudad y el momento del reporte desde los parámetros
    city     = parameters.get("city")
    when     = parameters.get("time", "today")

    # Validamos que se haya proporcionado una ciudad
    if not city or not isinstance(city, str) or not city.strip():
        msg = "Falta la ciudad para el reporte del clima."
        _log(msg, player)
        return msg

    city = city.strip()
    when = (when or "today").strip()

    # Construimos la URL de búsqueda del clima en Google
    search_query  = f"weather in {city} {when}"
    url           = f"https://www.google.com/search?q={quote_plus(search_query)}"

    # Abrimos el navegador con la búsqueda del clima
    try:
        opened = webbrowser.open(url)
        if not opened:
            raise RuntimeError("webbrowser.open devolvió False")
    except Exception as e:
        msg = f"No pude abrir el navegador para el clima: {e}"
        _log(msg, player)
        return msg

    msg = f"Mostrando el clima de {city}, {when}."
    _log(msg, player)

    # Guardamos en memoria de sesión si está disponible
    if session_memory:
        try:
            session_memory.set_last_search(query=search_query, response=msg)
        except Exception:
            pass

    return msg


def _log(message: str, player=None) -> None:
    # Registramos el mensaje en consola y en el log de la UI
    print(f"[Clima] {message}")
    if player:
        try:
            player.write_log(f"Mila: {message}")
        except Exception:
            pass
