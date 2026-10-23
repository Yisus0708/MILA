"""
whatsapp_watcher.py — Módulo desactivado.
El envío de mensajes de WhatsApp se maneja desde send_message.py
cuando el usuario lo pide explícitamente.
"""

class WhatsAppWatcher:
    def __init__(self, *args, **kwargs):
        self.access_granted = False

    def start(self): pass
    def stop(self):  pass
    def track_outbound(self, receiver): pass
