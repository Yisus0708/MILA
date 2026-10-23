import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed.")


def _paste_text(text: str):
    _require_pyautogui()
    os_name = _get_os()
    paste_hotkey = ("command", "v") if os_name == "mac" else ("ctrl", "v")
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(*paste_hotkey)
        time.sleep(0.1)
    else:
        pyautogui.write(text, interval=0.03)


# Moods en español → query de búsqueda para Spotify
_MOOD_MAP = {
    "triste":      "sad songs playlist",
    "tristeza":    "sad songs playlist",
    "llorar":      "sad emotional songs",
    "deprimido":   "sad songs playlist",
    "feliz":       "happy songs playlist",
    "alegre":      "happy upbeat songs",
    "fiesta":      "party hits playlist",
    "relajar":     "relaxing chill music",
    "relajado":    "relaxing chill music",
    "estudiar":    "study music focus",
    "concentrar":  "focus study music",
    "ejercicio":   "workout motivation music",
    "gym":         "gym workout music",
    "dormir":      "sleep music calm",
    "romantico":   "romantic songs playlist",
    "romántico":   "romantic songs playlist",
    "energía":     "energy hype music",
    "energia":     "energy hype music",
    "reggaeton":   "reggaeton playlist",
    "salsa":       "salsa playlist",
    "bachata":     "bachata playlist",
    "perreo":      "perreo playlist",
}

def _resolve_query(query: str) -> str:
    q_lower = query.lower().strip()
    for mood, search in _MOOD_MAP.items():
        if mood in q_lower:
            return search
    return query


def _open_spotify_app() -> bool:
    _require_pyautogui()
    os_name = _get_os()
    try:
        if os_name == "windows":
            # deep link directo — mucho más confiable que Win key search
            subprocess.Popen(["explorer.exe", "spotify://"])
            time.sleep(4.0)
            return True
        elif os_name == "mac":
            subprocess.run(["open", "-a", "Spotify"], capture_output=True, timeout=10)
            time.sleep(3.0)
            return True
        else:
            for launcher in [["spotify"], ["flatpak", "run", "com.spotify.Client"]]:
                try:
                    subprocess.Popen(launcher, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(3.0)
                    return True
                except FileNotFoundError:
                    continue
            return False
    except Exception as e:
        print(f"[Spotify] Could not open app: {e}")
        return False


def _playback(action: str) -> str:
    _require_pyautogui()
    if not _open_spotify_app():
        return "Could not open Spotify."
    os_name = _get_os()
    time.sleep(0.5)
    if action in ("play", "resume", "play_pause"):
        pyautogui.press("space")
        return "Playback toggled."
    elif action == "pause":
        pyautogui.press("space")
        return "Paused."
    elif action == "next":
        keys = ("command", "right") if os_name == "mac" else ("ctrl", "right")
        pyautogui.hotkey(*keys)
        return "Next track."
    elif action == "previous":
        keys = ("command", "left") if os_name == "mac" else ("ctrl", "left")
        pyautogui.hotkey(*keys)
        return "Previous track."
    elif action == "volume_up":
        keys = ("command", "up") if os_name == "mac" else ("ctrl", "up")
        pyautogui.hotkey(*keys)
        return "Volume up."
    elif action == "volume_down":
        keys = ("command", "down") if os_name == "mac" else ("ctrl", "down")
        pyautogui.hotkey(*keys)
        return "Volume down."
    return f"Unknown action: {action}"


def _search_and_play(query: str) -> str:
    _require_pyautogui()
    if not _open_spotify_app():
        return "No pude abrir Spotify. Asegurate de tenerlo instalado."
    time.sleep(1.5)
    os_name = _get_os()

    # resolver mood/género a query real
    resolved = _resolve_query(query)
    is_mood = resolved != query  # mood/género → basta con reproducir el top result

    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")

    # Ctrl+K abre el buscador en Spotify Windows (Ctrl+L no funciona)
    search_hotkey = ("command", "k") if os_name == "mac" else ("ctrl", "k")
    pyautogui.hotkey(*search_hotkey)
    time.sleep(0.9)

    # BUG FIX: el buscador puede conservar texto de una búsqueda previa; al pegar
    # encima quedaba "cancionanteriorcancionnueva" → Spotify no encontraba nada y
    # reproducía algo al azar. Limpiamos el campo antes de escribir.
    pyautogui.hotkey(*select_all)
    time.sleep(0.15)
    pyautogui.press("delete")
    time.sleep(0.2)

    _paste_text(resolved)
    time.sleep(2.2)  # dar tiempo a que carguen los resultados en vivo
    pyautogui.press("enter")
    time.sleep(2.5)

    if is_mood:
        # playlist/género: reproducir el resultado principal
        pyautogui.press("tab")
        time.sleep(0.3)
        pyautogui.press("enter")
    else:
        # BUG FIX: antes se hacía Tab + Enter y el foco caía en la tarjeta
        # "Mejor resultado", cuyo Enter NAVEGA a la portada del álbum/artista en
        # lugar de reproducir → parecía que sonaba una canción aleatoria.
        # Filtramos por "Canciones" y reproducimos la primera fila de la lista,
        # que siempre es la canción buscada.
        _play_first_song_result()

    time.sleep(0.5)
    label = query if not is_mood else f"{query} → {resolved}"
    return f"✅ Reproduciendo en Spotify: {label}"


def _play_first_song_result():
    """En la página de resultados, filtra por Canciones y reproduce la 1ª fila."""
    # Los chips de filtro (Todo / Canciones / Artistas / ...) son un grupo de
    # pestañas: un solo Tab los enfoca y las flechas se mueven entre ellos.
    pyautogui.press("tab")
    time.sleep(0.3)
    pyautogui.press("home")           # ir al primer chip ("Todo")
    time.sleep(0.2)
    pyautogui.press("right")          # "Todo" -> "Canciones" (2º chip)
    time.sleep(0.2)
    pyautogui.press("enter")          # aplicar filtro "Canciones"
    time.sleep(1.5)
    # Entrar a la lista de canciones y reproducir la primera fila.
    pyautogui.press("tab")
    time.sleep(0.3)
    pyautogui.press("enter")


def _current_track() -> str:
    os_name = _get_os()
    try:
        if os_name == "mac":
            r = subprocess.run(
                ["osascript", "-e", 'tell app "Spotify" to get name of current track & " - " & artist of current track'],
                capture_output=True, text=True, timeout=5
            )
            if r.stdout.strip():
                return f"Now playing: {r.stdout.strip()}"
        return "Could not detect current track."
    except Exception:
        return "Could not detect current track."


def _like_song() -> str:
    _require_pyautogui()
    if not _open_spotify_app():
        return "Could not open Spotify."
    time.sleep(0.5)
    os_name = _get_os()
    key = ("command", "shift", "l") if os_name == "mac" else ("ctrl", "shift", "l")
    pyautogui.hotkey(*key)
    return "Song liked."


def _shuffle() -> str:
    _require_pyautogui()
    if not _open_spotify_app():
        return "Could not open Spotify."
    time.sleep(0.5)
    os_name = _get_os()
    key = ("command", "s") if os_name == "mac" else ("ctrl", "s")
    pyautogui.hotkey(*key)
    return "Shuffle toggled."


def spotify_control(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "").strip().lower()
    query = params.get("query", "").strip()
    if player:
        player.write_log(f"[Spotify] {action}")
    if not _PYAUTOGUI:
        return "PyAutoGUI is not installed."
    try:
        if action in ("play", "resume", "pause", "play_pause", "next", "previous", "volume_up", "volume_down"):
            result = _playback(action)
            if player and hasattr(player, "set_dancing"):
                if action in ("play", "resume"):
                    player.set_dancing(True)
                elif action == "pause":
                    player.set_dancing(False)
            return result
        elif action in ("search", "play_song", "play_playlist"):
            q = params.get("playlist", "") or query
            if not q:
                return "Please specify a song or playlist."
            result = _search_and_play(q)
            if player and hasattr(player, "set_dancing"):
                player.set_dancing(True)
            return result
        elif action == "current":
            return _current_track()
        elif action == "like":
            return _like_song()
        elif action == "shuffle":
            return _shuffle()
        elif action == "stop":
            result = _playback("pause")
            if player and hasattr(player, "set_dancing"):
                player.set_dancing(False)
            return result
        else:
            result = _search_and_play(action)
            if player and hasattr(player, "set_dancing"):
                player.set_dancing(True)
            return result
    except Exception as e:
        return f"Spotify error: {e}"
