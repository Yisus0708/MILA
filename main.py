import asyncio
import re
import threading
import json
import sys
import time
import traceback
from pathlib import Path

if sys.platform == "win32":  
    # La consola de Windows suele usar cp1252/cp850, que no puede imprimir
    # los emojis usados en los logs de MILA y hace crashear el proceso
    # con UnicodeEncodeError apenas arranca. Forzamos UTF-8 en stdout/stderr.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from ui import MilaUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.whatsapp_watcher  import WhatsAppWatcher
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.db_reader         import db_reader
from actions.system_analyzer   import system_analyzer
from actions.code_helper       import code_helper
from actions.code_runner       import code_runner
from actions.image_generator   import image_generator
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.spotify_control    import spotify_control
from actions.email_control     import email_control
from actions.shopping_assistant import shopping_assistant
from memory.learning_memory    import (
    get_session_context, record_interaction, record_correction, add_knowledge,
    record_tool_failure, save_session_recap, get_session_recap,
)


# Detectamos el directorio base del proyecto
def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
import platform as _platform
print(f"[MILA] 🖥️  SO detectado: {_platform.system()}")
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-latest"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_voice_name() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("voice_name", "Kore")
    except Exception:
        return "Kore"


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are MILA, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "whatsapp_autochat",
        "description": (
            "Controls whether MILA replies autonomously to a WhatsApp contact on the user's behalf, "
            "impersonating the user's writing style. Call action='activate' when MILA just told the user "
            "that someone replied on WhatsApp and asked 'quieres que hable con X en tu nombre?' and the "
            "user says yes. Call action='deactivate' when the user says stop ('para', 'ya no le hables a X') "
            "or answers no to that question. Call action='status' if the user asks whether MILA is currently "
            "talking to someone for them."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING", "description": "activate | deactivate | status"},
                "contact": {"type": "STRING", "description": "Exact contact name MILA should talk to / stop talking to"}
            },
            "required": ["action", "contact"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": (
            "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage. "
            "ALWAYS pass 'path' as exactly the location the user named — never default to 'desktop' if they "
            "specified a folder, drive, or absolute path. If they gave a plain folder name with no drive/shortcut "
            "(e.g. 'Proyectos'), pass it as-is; it resolves relative to their Desktop, not somewhere else."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "db_reader",
        "description": "Lee bases de datos MySQL o PostgreSQL (solo lectura). Úsalo cuando el usuario pida ver tablas, columnas o datos de su base de datos.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "list_tables | describe_table | query"},
                "table":    {"type": "STRING", "description": "Nombre de la tabla (para describe_table)"},
                "query":    {"type": "STRING", "description": "Consulta SQL SELECT (para query)"},
                "max_rows": {"type": "INTEGER", "description": "Máximo de filas a devolver (default 50)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "system_analyzer",
        "description": "Analiza el sistema del usuario: procesos, puertos abiertos, disco, red, programas de inicio, actualizaciones pendientes y vulnerabilidades básicas. Úsalo cuando el usuario pida analizar su sistema, ver vulnerabilidades, revisar procesos o puertos.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "full_scan | processes | suspicious | open_ports | disk_info | network_info | startup_info | windows_updates | system_info"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "image_generator",
        "description": "Generates or edits images using Gemini 3.1 Flash Image (Nano Banana 2). Saves to desktop and opens automatically. Use when user asks to generate, create or edit an image.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt":      {"type": "STRING", "description": "Description of the image to generate"},
                "output_path": {"type": "STRING", "description": "File name to save (optional)"},
                "image_size":  {"type": "STRING", "description": "Image size: 512, 1K, 2K, 4K (default: 1K)"},
                "image_path":  {"type": "STRING", "description": "Path to existing image to edit (optional)"},
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "code_runner",
        "description": "Generates code, executes it automatically, and self-corrects up to 3 times if errors occur. Use when the user wants to create AND run code in one step. Shows the code preview and execution result.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description": {"type": "STRING", "description": "What the code should do"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file (optional)"},
                "args":        {"type": "STRING", "description": "CLI arguments (optional)"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "spotify_control",
        "description": "Controls Spotify: play, pause, next, previous, search and play a song or playlist, volume up/down, like song, shuffle. Use for ANY Spotify request.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | pause | next | previous | search | play_song | play_playlist | current | like | shuffle | stop | volume_up | volume_down"},
                "query":  {"type": "STRING", "description": "Song or playlist name to search and play"},
                "playlist": {"type": "STRING", "description": "Playlist name (optional)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "email_control",
        "description": "Send and compose emails via Gmail or Outlook. Can open browser compose window or send directly via SMTP. Use for any email request.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "send | compose | open | desktop | configure"},
                "provider": {"type": "STRING", "description": "gmail | outlook (default: gmail)"},
                "to":       {"type": "STRING", "description": "Recipient email address"},
                "subject":  {"type": "STRING", "description": "Email subject"},
                "body":     {"type": "STRING", "description": "Email body content"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "shopping_assistant",
        "description": "Searches products across multiple stores (Amazon, MercadoLibre, Walmart, eBay, BestBuy), compares prices, analyzes reviews, and finds the best deal. Use for any shopping or product comparison request.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING", "description": "search | navigate | reviews | add_to_cart | buy | compare_urls"},
                "query":   {"type": "STRING", "description": "Product to search"},
                "store":   {"type": "STRING", "description": "amazon | mercadolibre | walmart | bestbuy | ebay (optional)"},
                "stores":  {"type": "STRING", "description": "Comma-separated list of stores to search (optional)"},
                "url":     {"type": "STRING", "description": "Product URL for reviews/cart/buy actions"},
                "urls":    {"type": "STRING", "description": "Comma-separated URLs for compare_urls action"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_mila",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Mila. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "record_correction",
        "description": (
            "Call this silently whenever the user corrects a mistake you made or a wrong assumption "
            "you had (e.g. 'no, that's wrong', 'actually it's...', 'I told you before that...'). "
            "This is stored so you don't repeat the same mistake in future sessions. "
            "Do NOT announce that you are saving it — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic":      {"type": "STRING", "description": "Short topic/subject of the correction (e.g. 'user's sister name')"},
                "correction": {"type": "STRING", "description": "The correct information, stated plainly"},
                "context":    {"type": "STRING", "description": "Optional extra context about the mistake"},
            },
            "required": ["topic", "correction"]
        }
    },
    {
        "name": "add_knowledge",
        "description": (
            "Call this silently whenever the user teaches you a new fact, explains a concept, or "
            "shares useful information about a topic (not personal facts about the user — use "
            "save_memory for those). This builds long-term knowledge across sessions. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic": {"type": "STRING", "description": "Short topic name (e.g. 'project MILA architecture')"},
                "fact":  {"type": "STRING", "description": "The fact or explanation to remember, concise"},
            },
            "required": ["topic", "fact"]
        }
    },
]

class MilaLive:

    def __init__(self, ui: MilaUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._send_lock: asyncio.Lock | None = None
        self._executing_tool = False
        self._speech_cooldown_until: float = 0.0
        self._last_speech_started: float = 0.0
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._transcript: list[str] = []
        self._resumption_handle: str | None = None
        self.wa_watcher = WhatsAppWatcher(speak_callback=self.speak, write_log=self.ui.write_log)
        self.wa_watcher.start()

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self._safe_send_client_content(text),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            prev = self._is_speaking
            self._is_speaking = value
            if prev and not value:
                # Cooldown de 400ms tras terminar de hablar para disipar el eco
                # acústico residual de los altavoces antes de reabrir el micrófono.
                self._speech_cooldown_until = time.time() + 0.4
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    async def _safe_send_client_content(self, text: str):
        if not self.session or not self._send_lock:
            return
        if self._executing_tool:
            # Si hay una herramienta en ejecución, Gemini Live está esperando
            # estrictamente un tool_response. Enviar client_content violaría el protocolo
            # y provocaría el cierre de la conexión (código 1011).
            self.ui.write_log(f"Mila: {text}")
            return
        try:
            async with self._send_lock:
                await self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                )
        except Exception as e:
            print(f"[MILA] ⚠️ Error enviando client content: {e}")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self._safe_send_client_content(text),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory       = load_memory()
        mem_str      = format_memory_for_prompt(memory)
        recap_str    = get_session_recap()
        learning_str = get_session_context()
        sys_prompt   = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        if recap_str:
            parts.append(recap_str)
        if learning_str:
            parts.append(learning_str)
        parts.append(sys_prompt)

        config_kwargs = {
            "response_modalities": ["AUDIO"],
            "output_audio_transcription": {},
            "input_audio_transcription": {},
            "system_instruction": "\n".join(parts),
            "tools": [{"function_declarations": TOOL_DECLARATIONS}],
            "speech_config": types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=_get_voice_name()
                    )
                )
            ),
        }

        return types.LiveConnectConfig(**config_kwargs)

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        self._executing_tool = True
        try:
            return await self._do_execute_tool(fc)
        finally:
            self._executing_tool = False

    async def _do_execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[MILA] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        if name == "record_correction":
            topic      = args.get("topic", "")
            correction = args.get("correction", "")
            context    = args.get("context", "")
            if topic and correction:
                record_correction(topic, correction, context)
                print(f"[Memory] 📝 record_correction: {topic} -> {correction}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        if name == "add_knowledge":
            topic = args.get("topic", "")
            fact  = args.get("fact", "")
            if topic and fact:
                add_knowledge(topic, fact)
                print(f"[Memory] 📚 add_knowledge: {topic} -> {fact}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        if name == "set_emotion":
            emotion = (args.get("emotion") or "neutral").lower().strip()
            self.ui.set_emotion(emotion)
            print(f"[MILA] 🙂 emotion -> {emotion}")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "db_reader":
                r = await loop.run_in_executor(None, lambda: db_reader(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_analyzer":
                r = await loop.run_in_executor(None, lambda: system_analyzer(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None, watcher=self.wa_watcher))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "whatsapp_autochat":
                action  = (args.get("action") or "").lower().strip()
                contact = args.get("contact", "")
                if action == "activate":
                    result = self.wa_watcher.activate(contact)
                elif action == "deactivate":
                    result = self.wa_watcher.deactivate(contact)
                elif action == "status":
                    result = self.wa_watcher.status(contact)
                else:
                    result = f"Unknown whatsapp_autochat action: {action}"

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "image_generator":
                r = await loop.run_in_executor(None, lambda: image_generator(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "code_runner":
                r = await loop.run_in_executor(None, lambda: code_runner(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "spotify_control":
                r = await loop.run_in_executor(None, lambda: spotify_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "email_control":
                r = await loop.run_in_executor(None, lambda: email_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "shopping_assistant":
                r = await loop.run_in_executor(None, lambda: shopping_assistant(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "shutdown_mila":
                self.ui.write_log("SYS: Shutdown requested.")
                save_session_recap(self._transcript)
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            record_tool_failure(name, args, str(e))
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[MILA] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            now = time.time()
            if self._is_speaking or (now < self._speech_cooldown_until):
                continue
            if not self.session or not self._send_lock:
                continue
            try:
                async with self._send_lock:
                    blob = types.Blob(data=msg["data"], mime_type=msg["mime_type"]) if isinstance(msg, dict) else msg
                    await asyncio.wait_for(self.session.send_realtime_input(media=blob), timeout=15)
            except asyncio.TimeoutError:
                print("[MILA] ⚠️ send_realtime_input timeout — skipping chunk")
                continue
            except Exception as e:
                print(f"[MILA] ⚠️ send_realtime_input error: {e}")
                await asyncio.sleep(0.05)

    async def _listen_audio(self):
        print("[MILA] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def _enqueue(item):
            try:
                self.out_queue.put_nowait(item)
            except asyncio.QueueFull:
                pass

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                mila_speaking = self._is_speaking
            now = time.time()
            if not mila_speaking and not self.ui.muted and now >= self._speech_cooldown_until:
                data = indata.tobytes()
                blob = types.Blob(data=data, mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}")
                loop.call_soon_threadsafe(_enqueue, blob)

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[MILA] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[MILA] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[MILA] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while self.session:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.session_resumption_update and response.session_resumption_update.resumable:
                        self._resumption_handle = response.session_resumption_update.new_handle

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.interrupted:
                            now = time.time()
                            # Solo consideramos interrupción real si MILA lleva hablando más de 1.2 segundos
                            # Esto evita que el eco acústico inicial de los altavoces corte la respuesta antes de empezar.
                            if (now - self._last_speech_started) > 1.2:
                                print("[MILA] 🛑 Interrupción detectada por usuario (barge-in)")
                                while not self.audio_in_queue.empty():
                                    try:
                                        self.audio_in_queue.get_nowait()
                                    except asyncio.QueueEmpty:
                                        break
                                self.set_speaking(False)
                                if self._turn_done_event:
                                    self._turn_done_event.clear()
                            else:
                                print("[MILA] ℹ️ Ignorando corte prematuro por eco acústico")

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                record_interaction()
                                self._transcript.append(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Mila: {full_out}")
                                self._transcript.append(f"Mila: {full_out}")
                            out_buf = []
                            self._transcript = self._transcript[-40:]

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[MILA] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        async with self._send_lock:
                            await self.session.send_tool_response(
                                function_responses=fn_responses
                            )

                # Al terminar un turno (turn_complete), el generador finaliza normalmente.
                # Pausa mínima y continuamos esperando el siguiente turno en la misma sesión viva.
                await asyncio.sleep(0.02)
        except Exception as e:
            print(f"[MILA] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[MILA] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        idle_ticks = 0
        IDLE_LIMIT = 8  # 8 * 0.1s = 800ms sin audio nuevo

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if self._is_speaking:
                        idle_ticks += 1
                        turn_done = (
                            self._turn_done_event and self._turn_done_event.is_set()
                        )
                        # Solo finalizamos el turno de habla si la cola de audio está vacía
                        # y el turno se completó o se superó el límite de inactividad
                        if self.audio_in_queue.empty() and (turn_done or idle_ticks >= IDLE_LIMIT):
                            self.set_speaking(False)
                            if self._turn_done_event:
                                self._turn_done_event.clear()
                            idle_ticks = 0
                    continue
                idle_ticks = 0
                if not self._is_speaking:
                    self._last_speech_started = time.time()
                    self.set_speaking(True)
                try:
                    samples = np.frombuffer(chunk, dtype=np.int16)
                    if samples.size:
                        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
                        self.ui.set_mouth_level(min(1.0, rms / 6000.0))
                except Exception:
                    pass
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[MILA] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[MILA] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self._send_lock     = asyncio.Lock()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=60)
                    self._turn_done_event = asyncio.Event()

                    print("[MILA] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: MILA online.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[MILA] ⚠️ {e}")
                traceback.print_exc()
                err_str = str(e).lower()
                # Solo invalidamos el handle de reanudación si el servidor lo rechazó explícitamente
                if "invalid" in err_str or "400" in err_str or "unauthorized" in err_str or "403" in err_str:
                    self._resumption_handle = None
            finally:
                self.session = None
            save_session_recap(self._transcript)
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            err_str = str(e).lower() if 'e' in locals() else ""
            retry_delay = 10 if ("quota" in err_str or "1011" in err_str or "429" in err_str) else 3
            print(f"[MILA] 🔄 Reconnecting in {retry_delay}s...")
            await asyncio.sleep(retry_delay)

def main():
    ui = MilaUI("face.png")

    def runner():
        ui.wait_for_api_key()
        mila = MilaLive(ui)
        try:
            asyncio.run(mila.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()