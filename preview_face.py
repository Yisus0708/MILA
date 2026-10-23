"""Standalone preview for MILA animated assistant — no mic, no Gemini connection needed.

Run:  python preview_face.py

Keys:
  S     toggle "speaking" animation (assets/mila_speaking.gif vs assets/mila_idle.gif)
  M     toggle muted
  Tab   toggle Consola & Archivos side panel
  T     test subtitle display
  Esc   quit
"""
from PyQt6.QtGui import QKeySequence, QShortcut
from ui import MilaUI

ui = MilaUI("face.png")
win = ui._win

_speaking = {"v": False}
def toggle_speak():
    _speaking["v"] = not _speaking["v"]
    if _speaking["v"]:
        ui.set_state("SPEAKING")
        ui.write_log("Mila: ¡Hola! Soy MILA, tu asistente de inteligencia artificial personal. ¿En qué te puedo ayudar hoy?")
    else:
        ui.set_state("LISTENING")

QShortcut(QKeySequence("S"), win, activated=toggle_speak)
QShortcut(QKeySequence("M"), win, activated=lambda: setattr(ui, "muted", not ui.muted))
QShortcut(QKeySequence("T"), win, activated=lambda: ui.write_log("Mila: Procesando tu consulta en segundo plano con máxima precisión."))
QShortcut(QKeySequence("Escape"), win, activated=win.close)

ui.set_state("LISTENING")
win._log.append_log("SYS: Preview de MILA — Tecla [S] Hablar / Quieta, [M] Mute, [Tab / ≡] Consola, [T] Probar subtítulo, [Esc] Salir")
ui.root.mainloop()
