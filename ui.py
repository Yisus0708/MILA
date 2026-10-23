from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import cv2

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QCursor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QIcon, QImage, QKeySequence, QLinearGradient, QMovie, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGraphicsDropShadowEffect,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QScrollArea, QSizePolicy, QTextBrowser, QTextEdit, QVBoxLayout,
    QWidget,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1060, 730
_MIN_W,     _MIN_H     = 880, 600
_LEFT_W  = 190
_RIGHT_W = 365

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    # Deep midnight luxury background
    BG          = "#070b12"
    BG_DARK     = "#04070c"
    BG_CARD     = "#0d1624"
    BG_CARD_ALT = "#101d30"
    BG_HOVER    = "#14253d"
    
    # Glassmorphism borders & accents
    BORDER_DIM  = "#132338"
    BORDER      = "#1a3250"
    BORDER_HI   = "#2d5485"
    BORDER_GLOW = "#00f0ff"
    
    # Primary Cyber Neons
    PRI         = "#00f0ff"   # Electric Cyan
    PRI_DARK    = "#00a0b8"
    PRI_DIM     = "#007a94"
    PRI_GHO     = "rgba(0, 240, 255, 0.08)"
    PRI_GLOW    = "#38f9d7"
    
    # Accents
    VIOLET      = "#a855f7"   # Electric Violet
    VIOLET_GLOW = "#c084fc"
    PINK        = "#ec4899"   # Neon Pink
    AMBER       = "#f59e0b"   # Amber Gold
    ORANGE      = "#f97316"   # Electric Orange
    
    # Status
    GREEN       = "#10b981"   # Emerald Green
    GREEN_GLOW  = "#34d399"
    GREEN_BG    = "#06281e"
    RED         = "#f43f5e"   # Crimson Red
    RED_GLOW    = "#fb7185"
    RED_BG      = "#2d0810"
    MUTED_C     = "#f43f5e"
    
    # Text Hierarchy
    WHITE       = "#ffffff"
    TEXT_BRIGHT = "#f1f5f9"
    TEXT_MAIN   = "#cbd5e1"
    TEXT_MED    = "#94a3b8"
    TEXT_DIM    = "#64748b"
    TEXT_DARK   = "#334155"
    
    # Specialty
    BAR_TRACK   = "#0b1522"


def qcol(h: str, a: int = 255) -> QColor:
    if h.startswith("rgba"):
        parts = h.replace("rgba(", "").replace(")", "").split(",")
        if len(parts) == 4:
            r = int(parts[0].strip())
            g = int(parts[1].strip())
            b = int(parts[2].strip())
            alpha = float(parts[3].strip())
            return QColor(r, g, b, int(alpha * 255))
    c = QColor(h)
    c.setAlpha(a)
    return c


_DANCE_PALETTE = [C.PRI, C.VIOLET, C.PINK, C.AMBER, C.GREEN]


class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0
        self.gpu  = -1.0
        self.tmp  = -1.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()
        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()


# ---------------------------------------------------------------------------
# Vector face & HUD System ("Mila Core")
# ---------------------------------------------------------------------------
FACE_REF_W, FACE_REF_H = 220.0, 150.0
FACE_CX, FACE_CY       = FACE_REF_W / 2, FACE_REF_H / 2
EYE_RX, EYE_RY         = 28.0, 32.0
EYE_SEP                = 54.0
EYE_Y                  = FACE_CY - 2.0
MOUTH_BASE_Y           = FACE_CY + 40.0
MOUTH_TALK_Y           = MOUTH_BASE_Y + 12.0

_FACE_FIELDS = [
    "eye_scale_y", "eye_scale_x", "eye_dx_l", "eye_dx_r", "eye_dy_l", "eye_dy_r",
    "eye_rot_l", "eye_rot_r", "heart", "blush",
    "mouth_width", "mouth_depth", "mouth_asym", "mouth_tilt", "mouth_y_off", "mouth_accent",
    "rot_bias", "dy_bias",
    "rot_osc_amp", "rot_osc_freq", "dy_osc_amp", "dy_osc_freq", "scale_osc_amp", "scale_osc_freq",
]

_FACE_DEFAULTS = {
    "eye_scale_y": 1.0, "eye_scale_x": 1.0, "eye_dx_l": 0.0, "eye_dx_r": 0.0,
    "eye_dy_l": 0.0, "eye_dy_r": 0.0, "eye_rot_l": 0.0, "eye_rot_r": 0.0, "heart": 0.0, "blush": 0.0,
    "mouth_width": 86.0, "mouth_depth": 16.0, "mouth_asym": 0.0, "mouth_tilt": 0.0,
    "mouth_y_off": 0.0, "mouth_accent": 0.0,
    "rot_bias": 0.0, "dy_bias": 0.0,
    "rot_osc_amp": 0.0, "rot_osc_freq": 1.0, "dy_osc_amp": 0.0, "dy_osc_freq": 1.0,
    "scale_osc_amp": 0.0, "scale_osc_freq": 1.0,
}


def _face_profile(**overrides) -> dict:
    d = dict(_FACE_DEFAULTS)
    d.update(overrides)
    return d


FACE_EMOTIONS = {
    "neutral": _face_profile(),
    "happy": _face_profile(
        eye_scale_y=0.6, eye_dy_l=8, eye_dy_r=8,
        blush=0.9,
        mouth_width=108, mouth_depth=28,
        dy_osc_amp=4.5, dy_osc_freq=2.0,
    ),
    "thinking": _face_profile(
        eye_dx_r=8, eye_dy_r=-6, eye_rot_r=8,
        mouth_width=68, mouth_depth=4,
        rot_bias=-5.5,
        rot_osc_amp=2.0, rot_osc_freq=1.2,
    ),
    "confused": _face_profile(
        eye_dx_l=6, eye_dy_l=8, eye_rot_l=15, eye_rot_r=-6,
        mouth_width=76, mouth_depth=12, mouth_asym=12, mouth_tilt=5,
        rot_osc_amp=3.5, rot_osc_freq=3.8,
    ),
    "surprised": _face_profile(
        eye_scale_y=1.22, eye_scale_x=1.22,
        mouth_width=44, mouth_depth=4, mouth_y_off=4,
        dy_bias=-4,
    ),
    "sleepy": _face_profile(
        eye_scale_y=0.15, eye_dy_l=14, eye_dy_r=14,
        mouth_width=56, mouth_depth=-4, mouth_y_off=6,
        rot_bias=3.5, dy_bias=8,
        dy_osc_amp=2, dy_osc_freq=0.5,
    ),
    "love": _face_profile(
        heart=1.0, blush=1.0, mouth_width=96, mouth_depth=24,
        scale_osc_amp=0.04, scale_osc_freq=2.4,
    ),
    "angry": _face_profile(
        eye_scale_y=0.52, eye_dx_l=8, eye_dx_r=-8, eye_dy_l=5, eye_dy_r=5,
        eye_rot_l=16, eye_rot_r=-16,
        mouth_width=68, mouth_depth=-8, mouth_accent=1.0,
        rot_osc_amp=5, rot_osc_freq=8,
    ),
    "dancing": _face_profile(
        eye_scale_y=0.72, eye_dy_l=4, eye_dy_r=4,
        blush=0.8,
        mouth_width=104, mouth_depth=26,
        dy_bias=-4,
        rot_osc_amp=11, rot_osc_freq=2.6,
        dy_osc_amp=16, dy_osc_freq=5.0,
        scale_osc_amp=0.07, scale_osc_freq=2.6,
    ),
}

_VALID_EMOTIONS = set(FACE_EMOTIONS.keys())


def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red()   + (c2.red()   - c1.red())   * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue()  + (c2.blue()  - c1.blue())  * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


def _heart_path(rx: float, ry: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(0, ry * 0.65)
    path.cubicTo(-rx * 1.35, -ry * 0.20, -rx * 0.55, -ry * 1.05, 0, -ry * 0.30)
    path.cubicTo(rx * 0.55, -ry * 1.05, rx * 1.35, -ry * 0.20, 0, ry * 0.65)
    return path


class VideoLoopPlayer:
    """
    Reproductor de video en bucle de alto rendimiento basado en OpenCV.
    Decodifica exclusivamente fotogramas de video ignorando por completo cualquier
    pista de audio para evitar conflictos con el subsistema de audio de Gemini Live.
    """
    def __init__(self, video_path: str | Path, fps: float = 24.0):
        self.video_path = str(video_path)
        self.fps = fps
        self._interval = 1.0 / max(1.0, fps)
        self._last_t = 0.0
        self._cached_pix: QPixmap | None = None
        self.cap: cv2.VideoCapture | None = None
        if os.path.exists(self.video_path):
            try:
                self.cap = cv2.VideoCapture(self.video_path)
            except Exception:
                self.cap = None

    def rewind(self):
        if self.cap and self.cap.isOpened():
            try:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._last_t = 0.0
            except Exception:
                pass

    def get_frame(self, now: float) -> QPixmap | None:
        if not self.cap or not self.cap.isOpened():
            return None
        if self._cached_pix is None or (now - self._last_t >= self._interval):
            try:
                ret, frame = self.cap.read()
                if not ret:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                if ret and frame is not None:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb.shape
                    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                    self._cached_pix = QPixmap.fromImage(qimg)
            except Exception:
                pass
            self._last_t = now
        return self._cached_pix

    def release(self):
        if self.cap and self.cap.isOpened():
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None


class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(280, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "LISTENING"

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 65.0
        self._tgt_halo   = 65.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 60.0, 120.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list] = []

        # Vector face state
        self.emotion         = "neutral"
        self._emo_target     = "neutral"
        self._emo_cur        = dict(FACE_EMOTIONS["neutral"])
        self._emo_tgt        = dict(FACE_EMOTIONS["neutral"])
        self._pop_impulse    = 0.0
        self._gesture_t      = 0.0

        self.dancing         = False
        self._dance_token    = 0
        self._dance_hue_idx  = 0

        self._eye_blinking   = False
        self._eye_blink_t0   = 0.0
        self._eye_blink_amt  = 1.0
        self._next_eye_blink = time.time() + random.uniform(3, 6)

        self._mouth_jit       = (0.0, 0.0, 0.0)
        self._mouth_jit_tgt   = (0.0, 0.0, 0.0)
        self._next_mouth_jit  = time.time() + random.uniform(1.5, 3.0)

        self._talk_w, self._talk_h         = 24.0, 8.0
        self._talk_tgt_w, self._talk_tgt_h = 24.0, 8.0
        self._next_talk_pick               = 0.0
        self._audio_level                  = 0.0
        self._audio_level_t                = 0.0
        
        # Audio visualizer spectrum bars (smoothed)
        self._spectrum_bars = [5.0] * 36
        self._spectrum_tgt  = [5.0] * 36

        # Modern Mila animated character & branding assets (Video MP4 principal con fallback a GIF)
        self.face_path = face_path
        self._video_idle: VideoLoopPlayer | None = None
        self._video_speaking: VideoLoopPlayer | None = None
        self._movie_idle: QMovie | None = None
        self._movie_speaking: QMovie | None = None
        self._avatar_pixmap: QPixmap | None = None
        self._logo_pixmap: QPixmap | None = None
        self._subtitle_text: str = ""
        self._subtitle_timer: float = 0.0
        self._load_assets()

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def _load_assets(self):
        # 1. Cargar videos oficiales HD de MILA (Sin audio, decodificación por fotogramas)
        idle_video_path = BASE_DIR / "assets" / "mila_idle.mp4"
        speak_video_path = BASE_DIR / "assets" / "mila_speaking.mp4"

        if idle_video_path.exists():
            self._video_idle = VideoLoopPlayer(idle_video_path, fps=24.0)
        if speak_video_path.exists():
            self._video_speaking = VideoLoopPlayer(speak_video_path, fps=24.0)

        # 2. Respaldo por si fallara la decodificación de video: GIFs oficiales
        idle_path = BASE_DIR / "assets" / "mila_idle.gif"
        speak_path = BASE_DIR / "assets" / "mila_speaking.gif"

        if idle_path.exists():
            self._movie_idle = QMovie(str(idle_path))
            self._movie_idle.frameChanged.connect(self.update)
            self._movie_idle.start()

        if speak_path.exists():
            self._movie_speaking = QMovie(str(speak_path))
            self._movie_speaking.frameChanged.connect(self.update)
            self._movie_speaking.start()

        # Respaldo estático
        candidates = [
            Path(self.face_path) if self.face_path else None,
            BASE_DIR / "assets" / "mila_avatar.png",
            BASE_DIR / "face.png",
        ]
        for p in candidates:
            if p and Path(p).is_file():
                pm = QPixmap(str(p))
                if not pm.isNull():
                    self._avatar_pixmap = pm
                    break

        # Logo de respaldo
        logo_candidates = [
            BASE_DIR / "assets" / "mila_logo_cyan.png",
            BASE_DIR / "assets" / "mila_logo_white.png",
            BASE_DIR / "assets" / "mila_logo.png",
            BASE_DIR / "logo.png",
        ]
        for lp in logo_candidates:
            if lp and Path(lp).is_file():
                pm = QPixmap(str(lp))
                if not pm.isNull():
                    self._logo_pixmap = pm
                    break

    def set_subtitle(self, text: str):
        cleaned = text.strip()
        if not cleaned:
            return
        if cleaned.startswith("SYS:") or cleaned.startswith("FILE:") or cleaned.startswith("ERR:"):
            return
        self._subtitle_text = cleaned
        self._subtitle_timer = time.time()
        self.update()

    def set_state(self, state: str):
        was_speaking = self.speaking
        self.state = state
        self.speaking = (state == "SPEAKING")
        if not was_speaking and self.speaking:
            if self._video_speaking:
                self._video_speaking.rewind()
        elif was_speaking and not self.speaking:
            if self._video_idle:
                self._video_idle.rewind()
        self.update()

    def set_emotion(self, emotion: str):
        pass  # Emociones desactivadas temporalmente a petición del usuario
        self.emotion      = emotion
        self._emo_tgt     = dict(FACE_EMOTIONS[emotion])
        if emotion == "surprised":
            self._pop_impulse = 0.08
        elif emotion == "angry":
            self._pop_impulse = -0.05

    def set_dancing(self, on: bool, duration: float = 20.0):
        self._dance_token += 1
        token = self._dance_token
        self.dancing = on
        if on and duration:
            QTimer.singleShot(int(duration * 1000), lambda: self._dance_timeout(token))

    def _dance_timeout(self, token: int):
        if token == self._dance_token:
            self.dancing = False

    def set_mouth_level(self, level: float):
        self._audio_level   = max(0.0, min(1.0, level))
        self._audio_level_t = time.time()

    def _step(self):
        self._tick += 1
        now = time.time()
        energetic = self.speaking or self.dancing

        if now - self._last_t > (0.10 if energetic else 0.45):
            if energetic:
                self._tgt_scale = random.uniform(1.05, 1.13)
                self._tgt_halo  = random.uniform(160, 210)
            elif self.muted:
                self._tgt_scale = random.uniform(0.995, 1.005)
                self._tgt_halo  = random.uniform(20, 35)
            else:
                self._tgt_scale = random.uniform(1.002, 1.012)
                self._tgt_halo  = random.uniform(55, 80)
            self._last_t = now

        sp = 0.35 if energetic else 0.14
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        speeds = [2.4, -1.8, 3.6] if self.dancing else [1.2, -0.8, 1.8] if self.speaking else [0.45, -0.30, 0.70]
        for i, speed in enumerate(speeds):
            self._rings[i] = (self._rings[i] + speed) % 360

        self._scan  = (self._scan  + (3.2 if energetic else 1.2)) % 360
        self._scan2 = (self._scan2 + (-2.2 if energetic else -0.7)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.76
        spd = 4.0 if energetic else 1.8
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        pulse_chance = 0.12 if self.dancing else 0.08 if self.speaking else 0.02
        if len(self._pulses) < 3 and random.random() < pulse_chance:
            self._pulses.append(0.0)

        # Particles
        particle_chance = 0.50 if self.dancing else 0.25 if self.speaking else 0.04
        if random.random() < particle_chance:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.26
            if self.dancing:
                self._dance_hue_idx = (self._dance_hue_idx + 1) % len(_DANCE_PALETTE)
                col = _DANCE_PALETTE[self._dance_hue_idx]
                speed_mul = 1.8
            elif self.speaking:
                col = C.PRI if random.random() > 0.3 else C.VIOLET
                speed_mul = 1.2
            else:
                col = C.PRI
                speed_mul = 0.6

            self._particles.append([
                cx + math.cos(ang) * r_s,
                cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.8, 2.2) * speed_mul,
                math.sin(ang) * random.uniform(0.8, 2.2) * speed_mul - 0.3,
                1.0,  # alpha
                col,
                random.uniform(2.0, 4.0), # size
            ])

        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.024, p[5], p[6]]
            for p in self._particles if p[4] > 0
        ]

        # Audio spectrum bars simulation (alive breathing wave in idle, energetic spectrum in speech)
        fresh_audio = (now - self._audio_level_t) < 0.25
        lvl = self._audio_level if fresh_audio else (0.75 if self.speaking else 0.0)
        
        for i in range(len(self._spectrum_bars)):
            dist_from_center = abs(i - len(self._spectrum_bars) / 2) / (len(self._spectrum_bars) / 2)
            wave = math.sin(self._tick * 0.10 + i * 0.38) * 0.5 + 0.5
            wave2 = math.cos(self._tick * 0.06 - i * 0.25) * 0.5 + 0.5
            
            if self.muted:
                tgt = 2.0
            elif self.speaking:
                tgt = 6.0 + (1.0 - dist_from_center * 0.35) * (wave * 18.0 + lvl * 26.0 + random.uniform(0, 8.0))
            elif self.dancing:
                tgt = 8.0 + (wave * 22.0 + wave2 * 10.0)
            else:
                # Idle ambient breathing wave
                tgt = 4.0 + (1.0 - dist_from_center * 0.5) * (wave * 7.0 + wave2 * 4.0)
            
            self._spectrum_tgt[i] = tgt
            self._spectrum_bars[i] += (self._spectrum_tgt[i] - self._spectrum_bars[i]) * 0.35

        self._blink_tick += 1
        if self._blink_tick >= 32:
            self._blink = not self._blink
            self._blink_tick = 0

        self._step_face(now)
        self.update()

    def _step_face(self, now: float):
        self._gesture_t += 1.0 / 60.0

        target = FACE_EMOTIONS["dancing"] if self.dancing else self._emo_tgt
        for k in _FACE_FIELDS:
            self._emo_cur[k] += (target[k] - self._emo_cur[k]) * 0.14
        self._pop_impulse *= 0.82

        if self._eye_blinking:
            el = now - self._eye_blink_t0
            dur = 0.14
            if el >= dur:
                self._eye_blinking = False
                self._next_eye_blink = now + random.uniform(3, 7)
                self._eye_blink_amt = 1.0
            else:
                tri = 1.0 - abs((el / dur) * 2 - 1)
                self._eye_blink_amt = 1.0 - tri * 0.95
        elif now >= self._next_eye_blink:
            self._eye_blinking = True
            self._eye_blink_t0 = now

        if now >= self._next_mouth_jit:
            self._mouth_jit_tgt = (
                random.uniform(-5, 5), random.uniform(-3, 3), random.uniform(-2, 2),
            )
            self._next_mouth_jit = now + random.uniform(1.5, 3.0)
        self._mouth_jit = tuple(
            c + (t - c) * 0.06 for c, t in zip(self._mouth_jit, self._mouth_jit_tgt)
        )

        if self.speaking:
            fresh_audio = (now - self._audio_level_t) < 0.25
            if fresh_audio:
                lvl = self._audio_level
                self._talk_tgt_h = 7 + lvl * 26
                self._talk_tgt_w = 24 + lvl * 12
            elif now >= self._next_talk_pick:
                self._talk_tgt_h = random.uniform(5, 28)
                self._talk_tgt_w = random.uniform(22, 34)
                self._next_talk_pick = now + 0.09
            self._talk_h += (self._talk_tgt_h - self._talk_h) * 0.5
            self._talk_w += (self._talk_tgt_w - self._talk_w) * 0.5

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W, H = self.width(), self.height()
        cx, cy = W / 2.0, H / 2.0

        # 1. Fondo de Lujo Noir / Obsidiana profunda (negro puro para fusión perfecta del GIF)
        p.fillRect(self.rect(), qcol("#000000"))

        # 2. Obtener fotograma activo (MP4 nativo de alta fluidez -> GIF -> Pixmap estático)
        now = time.time()
        active_video = self._video_speaking if self.speaking else self._video_idle
        pix = active_video.get_frame(now) if active_video else None

        if not pix or pix.isNull():
            active_movie = self._movie_speaking if self.speaking else self._movie_idle
            if active_movie and active_movie.isValid():
                pix = active_movie.currentPixmap()
            elif self._avatar_pixmap and not self._avatar_pixmap.isNull():
                pix = self._avatar_pixmap

        if not pix or pix.isNull():
            self._draw_vector_face(p, cx, cy, min(W, H))
            return

        # 3. Dimensionamiento y centrado elegante de Mila (aspecto nativo 16:9 - 1280x720)
        ar = 16.0 / 9.0
        avail_h = max(90.0, H - 48.0)
        target_h = max(100.0, min(avail_h, 560.0))
        target_w = target_h * ar
        if target_w > W * 0.94:
            target_w = W * 0.94
            target_h = target_w / ar

        avatar_x = cx - target_w / 2.0
        avatar_y = max(4.0, (H - 46.0 - target_h) / 2.0)
        avatar_rect = QRectF(avatar_x, avatar_y, target_w, target_h)

        # 4. Resplandor sutil respirando detrás de Mila (halo noir con cyan/violeta)
        halo_r = target_h * 0.55
        accent_col = QColor(C.PRI if self.speaking else (C.AMBER if self.state == "THINKING" else C.BORDER_HI))
        glow_grad = QRadialGradient(cx, avatar_y + target_h * 0.48, halo_r)
        glow_grad.setColorAt(0.0, qcol(accent_col.name(), 45 if self.speaking else 22))
        glow_grad.setColorAt(0.65, qcol(accent_col.name(), 12 if self.speaking else 3))
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow_grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, avatar_y + target_h * 0.48), halo_r, halo_r)

        # 5. Dibujar a Mila animada (fondo negro puro del MP4 se fusiona 100% con la ventana)
        p.drawPixmap(avatar_rect.toRect(), pix)

        # 6. Píldora de estado minimalista (debajo de Mila)
        sy = avatar_rect.bottom() + 4
        pill_w, pill_h = 160, 24
        pill_rect = QRectF(cx - pill_w / 2, sy, pill_w, pill_h)

        st = self.state.upper()
        if self.muted:
            txt, col_st, bg_st = "SILENCIADO", qcol(C.MUTED_C), qcol(C.RED_BG, 220)
            icon = "⊘"
        elif self.speaking or st == "SPEAKING":
            txt, col_st, bg_st = "HABLANDO", qcol(C.PRI), qcol(C.BG_CARD, 230)
            icon = "⚡"
        elif st == "THINKING":
            txt, col_st, bg_st = "PENSANDO", qcol(C.AMBER), qcol(C.BG_CARD, 230)
            icon = "◈"
        elif st == "PROCESSING":
            txt, col_st, bg_st = "PROCESANDO", qcol(C.ORANGE), qcol(C.BG_CARD, 230)
            icon = "▶"
        else:
            txt, col_st, bg_st = "ESCUCHANDO", qcol(C.GREEN), qcol(C.GREEN_BG, 220)
            icon = "●"

        p.setBrush(QBrush(bg_st))
        p.setPen(QPen(col_st, 1.2))
        p.drawRoundedRect(pill_rect, pill_h / 2, pill_h / 2)

        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QPen(col_st, 1))
        p.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, f"{icon}  {txt}")

        # 7. Visualizador simétrico de ondas de sonido de alta fidelidad
        wy = sy + pill_h + 3
        N = len(self._spectrum_bars)
        bw = 4.0
        gap = 3.0
        total_w = N * (bw + gap) - gap
        wx0 = (W - total_w) / 2

        for i in range(N):
            hgt = self._spectrum_bars[i]
            bx = wx0 + i * (bw + gap)
            by = wy + 14 - hgt

            bar_grad = QLinearGradient(bx, by, bx, wy + 14)
            if self.muted:
                bar_grad.setColorAt(0.0, qcol(C.RED, 220))
                bar_grad.setColorAt(1.0, qcol(C.RED, 40))
            elif self.speaking:
                bar_grad.setColorAt(0.0, qcol(C.PRI, 240))
                bar_grad.setColorAt(0.5, qcol(C.VIOLET, 200))
                bar_grad.setColorAt(1.0, qcol(C.PRI_DARK, 60))
            else:
                bar_grad.setColorAt(0.0, qcol(C.PRI, 180))
                bar_grad.setColorAt(0.6, qcol(C.PRI_DARK, 100))
                bar_grad.setColorAt(1.0, qcol(C.BORDER_HI, 30))

            p.setBrush(QBrush(bar_grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(bx, by, bw, hgt), bw / 2, bw / 2)

        # 8. Subtítulos dinámicos de voz en tiempo real
        if self._subtitle_text and (time.time() - self._subtitle_timer < 14.0):
            p.setFont(QFont("Segoe UI", 10))
            sub_w = min(680.0, W * 0.88)
            sub_rect = QRectF(cx - sub_w / 2.0, wy + 26, sub_w, 48)
            bg_rect = sub_rect.adjusted(-12, -4, 12, 4)
            p.setBrush(QBrush(QColor(10, 14, 22, 190)))
            p.setPen(QPen(QColor(0, 240, 255, 60), 1))
            p.drawRoundedRect(bg_rect, 8, 8)
            p.setPen(QPen(qcol(C.WHITE, 235)))
            p.drawText(sub_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, self._subtitle_text)

    def _draw_vector_face(self, p: QPainter, cx: float, cy: float, fw: float):
        c = self._emo_cur
        t = self._gesture_t

        rot = c["rot_bias"] + c["rot_osc_amp"] * math.sin(2 * math.pi * c["rot_osc_freq"] * t)
        dy  = c["dy_bias"]  + c["dy_osc_amp"]  * math.sin(2 * math.pi * c["dy_osc_freq"]  * t)
        scl = 1.0 + c["scale_osc_amp"] * math.sin(2 * math.pi * c["scale_osc_freq"] * t) + self._pop_impulse

        face_scale = (fw * 0.60 * self._scale * scl) / FACE_REF_W

        p.save()
        p.translate(cx, cy + dy * face_scale)
        p.rotate(rot)
        p.scale(face_scale, face_scale)
        p.translate(-FACE_CX, -FACE_CY)

        # Rosy Cheeks / Blush
        if c["blush"] > 0.05:
            blush_col = qcol(C.PINK, int(150 * c["blush"]))
            p.setBrush(QBrush(blush_col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(FACE_CX - EYE_SEP - 18, EYE_Y + 28), 16, 8)
            p.drawEllipse(QPointF(FACE_CX + EYE_SEP + 18, EYE_Y + 28), 16, 8)

        # Eyes
        eye_col = qcol(C.WHITE)
        self._draw_eye(p, FACE_CX - EYE_SEP + c["eye_dx_l"], EYE_Y + c["eye_dy_l"],
                       c["eye_scale_x"], c["eye_scale_y"], c["eye_rot_l"], c["heart"], eye_col)
        self._draw_eye(p, FACE_CX + EYE_SEP + c["eye_dx_r"], EYE_Y + c["eye_dy_r"],
                       c["eye_scale_x"], c["eye_scale_y"], c["eye_rot_r"], c["heart"], eye_col)

        # Mouth
        jit_w, jit_d, jit_y = self._mouth_jit
        mouth_col = _lerp_color(QColor(C.WHITE), QColor(C.RED), c["mouth_accent"])

        if self.speaking:
            # Speaking mouth with glowing gradient
            p.save()
            mouth_grad = QRadialGradient(FACE_CX, MOUTH_TALK_Y + c["mouth_y_off"], self._talk_w)
            mouth_grad.setColorAt(0.0, qcol(C.WHITE, 255))
            mouth_grad.setColorAt(0.7, qcol(C.PRI, 220))
            mouth_grad.setColorAt(1.0, qcol(C.VIOLET, 180))
            p.setBrush(QBrush(mouth_grad))
            p.setPen(QPen(qcol(C.WHITE), 1.5))
            p.drawEllipse(QPointF(FACE_CX, MOUTH_TALK_Y + c["mouth_y_off"]),
                          self._talk_w / 2, self._talk_h / 2)
            p.restore()
        else:
            self._draw_mouth_w(
                p, FACE_CX, MOUTH_BASE_Y + c["mouth_y_off"] + jit_y,
                max(10.0, c["mouth_width"] + jit_w),
                c["mouth_depth"] + jit_d,
                c["mouth_asym"], c["mouth_tilt"], mouth_col,
            )

        p.restore()

    def _draw_eye(self, p: QPainter, ex: float, ey: float,
                  scale_x: float, scale_y: float, rot_deg: float,
                  heart_t: float, color: QColor):
        p.save()
        p.translate(ex, ey)
        p.rotate(rot_deg)
        rx = EYE_RX * scale_x
        ry = EYE_RY * scale_y * self._eye_blink_amt
        p.setPen(Qt.PenStyle.NoPen)

        # Heart eyes for "love"
        if heart_t > 0.01:
            p.save()
            hc = QColor(C.PINK)
            hc.setAlpha(int(255 * heart_t))
            p.setBrush(QBrush(hc))
            p.drawPath(_heart_path(rx * 1.1, ry * 1.1))
            p.restore()

        # Regular solid white eyes (pure white, no blue/cyan dot)
        if heart_t < 0.99:
            ec = QColor(color)
            ec.setAlpha(int(255 * (1.0 - heart_t)))
            p.setBrush(QBrush(ec))
            p.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))

        p.restore()

    def _draw_mouth_w(self, p: QPainter, mx: float, my: float,
                       width: float, depth: float, asym: float, tilt: float,
                       color: QColor):
        p.save()
        p.translate(mx, my)
        p.rotate(tilt)
        half = width / 2
        left_depth  = depth + asym
        right_depth = depth - asym
        path = QPainterPath()
        path.moveTo(-half, 0)
        path.quadTo(-half * 0.5, left_depth, 0, 0)
        path.quadTo(half * 0.5, right_depth, half, 0)
        pen = QPen(color, 7.5, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.restore()


# ---------------------------------------------------------------------------
# Modern Telemetry Metric Card
# ---------------------------------------------------------------------------
class MetricCard(QWidget):
    def __init__(self, icon: str, label: str, grad_colors: tuple[str, str] = (C.PRI, C.VIOLET), parent=None):
        super().__init__(parent)
        self._icon   = icon
        self._label  = label
        self._grad   = grad_colors
        self._value  = 0.0
        self._text   = "--"
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        # Card container background
        card_rect = QRectF(1, 1, W - 2, H - 2)
        p.setBrush(QBrush(qcol(C.BG_CARD)))
        p.setPen(QPen(qcol(C.BORDER_DIM), 1))
        p.drawRoundedRect(card_rect, 6, 6)

        # Top label & icon
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.drawText(QRectF(8, 6, 80, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{self._icon} {self._label}")

        # Value readout
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        val_col = qcol(C.RED if self._value > 85 else (C.AMBER if self._value > 65 else C.WHITE))
        p.setPen(QPen(val_col, 1))
        p.drawText(QRectF(0, 6, W - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        # Progress bar track
        bar_h = 5
        bar_y = H - bar_h - 7
        bar_w = W - 16
        bar_x = 8
        fill_w = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_TRACK)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), bar_h / 2, bar_h / 2)

        # Filled progress with smooth gradient
        if fill_w > 0:
            fill_grad = QLinearGradient(bar_x, bar_y, bar_x + fill_w, bar_y)
            if self._value > 85:
                fill_grad.setColorAt(0.0, qcol(C.ORANGE))
                fill_grad.setColorAt(1.0, qcol(C.RED))
            else:
                fill_grad.setColorAt(0.0, qcol(self._grad[0]))
                fill_grad.setColorAt(1.0, qcol(self._grad[1]))

            p.setBrush(QBrush(fill_grad))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), bar_h / 2, bar_h / 2)


# ---------------------------------------------------------------------------
# Modern Styled Chat / Activity Log Stream
# ---------------------------------------------------------------------------
class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Segoe UI", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG_CARD};
                color: {C.TEXT_MAIN};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
                padding: 10px;
                line-height: 1.4;
                selection-background-color: {C.BORDER_HI};
            }}
            QScrollBar:vertical {{
                background: {C.BG_DARK};
                width: 6px;
                border: none;
                border-radius: 3px;
                margin: 4px 2px 4px 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_HI};
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.PRI_DARK};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none; background: none;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:") or tl.startswith("tú:"): self._tag = "you"
        elif tl.startswith("mila:"):                        self._tag = "ai"
        elif tl.startswith("file:") or tl.startswith("archivo:"): self._tag = "file"
        elif "err" in tl or "[error]" in tl:               self._tag = "err"
        else:                                               self._tag = "sys"
        self._tmr.start(5)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            
            # Rich modern styling for chat messages
            if self._tag == "you":
                fmt.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold if self._pos < 4 else QFont.Weight.Normal))
                fmt.setForeground(QBrush(qcol(C.WHITE)))
            elif self._tag == "ai":
                fmt.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold if self._pos < 5 else QFont.Weight.Normal))
                fmt.setForeground(QBrush(qcol(C.PRI if self._pos < 5 else C.TEXT_BRIGHT)))
            elif self._tag == "err":
                fmt.setForeground(QBrush(qcol(C.RED)))
            elif self._tag == "file":
                fmt.setForeground(QBrush(qcol(C.GREEN)))
            else: # sys
                fmt.setFont(QFont("Segoe UI", 8))
                fmt.setForeground(QBrush(qcol(C.AMBER if self._pos < 4 else C.TEXT_MED)))
            
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(15, self._next)


# ---------------------------------------------------------------------------
# Modern Hermes-Style Integrated Chat Stream
# ---------------------------------------------------------------------------
class HermesChatStream(QTextBrowser):
    """
    Flujo de conversación integrado estilo Hermes Desktop.
    Muestra los mensajes del usuario, respuestas de Mila y llamadas a herramientas
    en tarjetas limpias, redondeadas y translúcidas, integradas directamente
    en la pantalla central ("ahí mismo").
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setStyleSheet(f"""
            QTextBrowser {{
                background: {C.BG};
                color: {C.TEXT_MAIN};
                border: 1px solid {C.BORDER_DIM};
                border-radius: 12px;
                padding: 10px;
                selection-background-color: {C.BORDER_HI};
            }}
            QScrollBar:vertical {{
                background: {C.BG_DARK};
                width: 6px;
                border: none;
                border-radius: 3px;
                margin: 4px 2px 4px 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_HI};
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.PRI_DARK};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none; background: none;
            }}
        """)
        self._html_history = ""
        self._set_initial_welcome()

    def _set_initial_welcome(self):
        welcome = f"""
        <div style="text-align: center; margin: 16px 20px 20px 20px;">
            <div style="font-size: 13px; font-weight: bold; color: {C.PRI}; letter-spacing: 2px; margin-bottom: 6px;">
                ◈ MILA DESKTOP · MODO CONVERSACIÓN ACTIVA
            </div>
            <div style="font-size: 11px; color: {C.TEXT_MED}; line-height: 1.5;">
                Voz nativa de baja latencia conectada. Habla directamente a tu micrófono o envía mensajes abajo.
            </div>
        </div>
        """
        self._html_history = welcome
        self.setHtml(self._html_history)

    def clear_chat(self):
        self._set_initial_welcome()

    def append_chat(self, role: str, text: str):
        safe_text = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
        )
        if role.lower() in ("you", "tú", "user"):
            card = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 6px 0;">
                <tr>
                    <td style="padding: 12px 16px; background-color: #111a28; border: 1px solid #22344d; border-radius: 10px;">
                        <div style="color: #94a3b8; font-size: 10px; font-weight: bold; letter-spacing: 1.5px; margin-bottom: 4px;">👤 TÚ</div>
                        <div style="color: #ffffff; font-size: 13px; line-height: 1.45;">{safe_text}</div>
                    </td>
                </tr>
            </table>
            """
        elif role.lower() in ("mila", "assistant"):
            card = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 6px 0;">
                <tr>
                    <td style="padding: 14px 18px; background-color: #091522; border: 1px solid #00607a; border-radius: 10px;">
                        <div style="color: {C.PRI}; font-size: 10px; font-weight: bold; letter-spacing: 1.5px; margin-bottom: 4px;">◈ MILA</div>
                        <div style="color: {C.TEXT_MAIN}; font-size: 13px; line-height: 1.5;">{safe_text}</div>
                    </td>
                </tr>
            </table>
            """
        elif role.lower() in ("tool", "file", "archivo"):
            card = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 4px 0;">
                <tr>
                    <td style="padding: 6px 12px; background-color: #171026; border: 1px solid #3c1e5c; border-radius: 6px; color: #c084fc; font-size: 11px;">
                        ⚡ <b>Herramienta / Archivo:</b> {safe_text}
                    </td>
                </tr>
            </table>
            """
        elif role.lower() == "err":
            card = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 4px 0;">
                <tr>
                    <td style="padding: 6px 12px; background-color: #260a12; border: 1px solid #5c1828; border-radius: 6px; color: #fb7185; font-size: 11px;">
                        ⚠️ <b>Error:</b> {safe_text}
                    </td>
                </tr>
            </table>
            """
        else: # sys
            card = f"""
            <div style="margin: 4px 8px; padding: 4px 8px; color: {C.TEXT_MED}; font-size: 10.5px;">
                ● <i>{safe_text}</i>
            </div>
            """
        self._html_history += card
        self.setHtml(self._html_history)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


# ---------------------------------------------------------------------------
# File Drop Zone & Cards
# ---------------------------------------------------------------------------
_FILE_ICONS = {
    "image":   ("IMG",  "#00f0ff"), "video":   ("VID",  "#f97316"),
    "audio":   ("AUD",  "#a855f7"), "pdf":     ("PDF",  "#f43f5e"),
    "word":    ("DOC",  "#3b82f6"), "excel":   ("XLS",  "#10b981"),
    "code":    ("DEV",  "#eab308"), "archive": ("ZIP",  "#fb923c"),
    "pptx":    ("PPT",  "#ea580c"), "text":    ("TXT",  "#94a3b8"),
    "data":    ("DAT",  "#38bdf8"), "unknown": ("FILE", "#64748b"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(88)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.6) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True
            self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False
        self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True
        self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False
        self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None
        self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo para MILA", str(Path.home()),
            "Todos los Archivos (*.*);;"
            "Imágenes (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documentos (*.pdf *.docx *.txt *.md *.pptx);;"
            "Datos (*.csv *.xlsx *.json *.xml);;"
            "Código (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archivos Comprimidos (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 3
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        # Background
        bg_col = qcol("#0a202d" if z._drag_over else (C.BG_HOVER if z._hovering else C.BG_CARD))
        p.setBrush(QBrush(bg_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 8, 8)

        # Border
        if z._current_file:   border_col = qcol(C.GREEN, 220)
        elif z._drag_over:    border_col = qcol(C.PRI, 240)
        elif z._hovering:     border_col = qcol(C.BORDER_HI, 220)
        else:                 border_col = qcol(C.BORDER, 180)

        pen = QPen(border_col, 1.4, Qt.PenStyle.DashLine if not z._current_file else Qt.PenStyle.SolidLine)
        if not z._current_file:
            pen.setDashOffset(z._dash_offset)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 8, 8)

        if z._current_file:
            self._paint_file(p, W, H)
        elif z._drag_over:
            self._paint_drag_over(p, W, H)
        else:
            self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI if hover else C.PRI_DARK)
        
        # Sleek vector upload icon
        p.setPen(QPen(col, 2))
        p.drawLine(QPointF(cx, cy - 18), QPointF(cx, cy - 4))
        p.drawLine(QPointF(cx - 6, cy - 12), QPointF(cx, cy - 18))
        p.drawLine(QPointF(cx + 6, cy - 12), QPointF(cx, cy - 18))
        p.drawLine(QPointF(cx - 10, cy - 1), QPointF(cx + 10, cy - 1))

        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE if hover else C.TEXT_MAIN), 1))
        p.drawText(QRectF(0, cy + 4, W, 16), Qt.AlignmentFlag.AlignCenter, "Subir archivo")

        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, cy + 20, W, 14), Qt.AlignmentFlag.AlignCenter, "Arrastra un archivo aquí o haz clic para buscar")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 20, W, 24), Qt.AlignmentFlag.AlignCenter, "↓ Suelta el archivo")
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QPen(qcol(C.WHITE), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter, "MILA lo procesará al instante")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 12, 44
        badge_rect = QRectF(block_x, (H - 34) / 2, block_w, 34)
        p.setBrush(QBrush(qcol(icon_col, 35)))
        p.setPen(QPen(qcol(icon_col, 160), 1))
        p.drawRoundedRect(badge_rect, 5, 5)

        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 36

        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 30 else path.name[:27] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 15),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QPen(qcol(C.GREEN), 1))
        p.drawText(QRectF(tx, H * 0.18 + 33, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "✓ Listo para consultar")

        # Close / remove button
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 200), 1))
        p.drawText(QRectF(W - 32, 0, 26, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


# ---------------------------------------------------------------------------
# Initial Setup Dialog
# ---------------------------------------------------------------------------
class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(7, 11, 18, 0.95);
                border: 1px solid {C.BORDER_HI};
                border-radius: 12px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(10)

        def _lbl(txt, font_size=10, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Segoe UI", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  MILA — CONFIGURACIÓN INICIAL", 14, True, C.WHITE))
        layout.addWidget(_lbl("Configura tu API Key de Gemini para activar tu asistente con voz.", 9, color=C.TEXT_MED))
        layout.addSpacing(6)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};")
        layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, bold=True, color=C.TEXT_MED, align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Pega tu clave AIza…")
        self._key_input.setFont(QFont("Segoe UI", 10))
        self._key_input.setFixedHeight(36)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.BG_CARD}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 6px; padding: 4px 10px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; background: {C.BG_CARD_ALT}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(8)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};")
        layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("SISTEMA OPERATIVO", 8, bold=True, color=C.TEXT_MED, align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Detectado automáticamente: {det_name}", 8, color=C.AMBER, align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout()
        os_row.setSpacing(8)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞ Windows"),("mac","◈ macOS"),("linux","◆ Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            btn.setFixedHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(14)

        init_btn = QPushButton("▸  INICIAR MILA")
        init_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(40)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C.PRI}, stop:1 {C.VIOLET});
                color: #04070c;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4df6ff, stop:1 #c084fc);
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        for k, btn in self._os_btns.items():
            if k == key:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.PRI}; color: #04070c;
                        border: none; border-radius: 6px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.BG_CARD}; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 6px;
                    }}
                    QPushButton:hover {{ color: {C.WHITE}; border: 1px solid {C.BORDER_HI}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


# ---------------------------------------------------------------------------
# Main Window & Modern Layout
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    _log_sig     = pyqtSignal(str)
    _state_sig   = pyqtSignal(str)
    _emotion_sig = pyqtSignal(str)
    _mouth_sig   = pyqtSignal(float)
    _dance_sig   = pyqtSignal(bool)

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("M.I.L.A — Tu Asistente de IA Personal")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        icon_path = BASE_DIR / "assets" / "mila_logo_cyan.png"
        if not icon_path.exists():
            icon_path = BASE_DIR / "assets" / "mila_logo.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command  = None
        self._muted           = False
        self._current_file: str | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(8)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        # Contenedor central de MILA con modo Chat integrado estilo Hermes Desktop
        center_container = QWidget()
        center_lay = QVBoxLayout(center_container)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(6)

        # 1. Escenario animado de Mila (Video loop HD)
        self.hud = HudCanvas(face_path)
        self.hud.setFixedHeight(250)
        center_lay.addWidget(self.hud, stretch=0)

        # 2. Flujo de chat estilo Hermes Desktop ("modo chat ahí mismo")
        self.chat_stream = HermesChatStream()
        center_lay.addWidget(self.chat_stream, stretch=1)

        # 3. Barra de entrada flotante estilo Hermes Desktop
        self._floating_bar = self._build_floating_prompt_bar()
        center_lay.addWidget(self._floating_bar, stretch=0)

        body.addWidget(center_container, stretch=1)

        self._right_panel = self._build_right_panel()
        self._right_panel.setVisible(False)  # Oculto por defecto para diseño limpio
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        self._view_mode = "split"
        self._set_view_mode("split")

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(1800)
        self._update_metrics()

        self._log_sig.connect(self._on_log_received)
        self._state_sig.connect(self._apply_state)
        self._emotion_sig.connect(self._apply_emotion)
        self._mouth_sig.connect(self.hud.set_mouth_level)
        self._dance_sig.connect(self.hud.set_dancing)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_panel = QShortcut(QKeySequence("F2"), self)
        sc_panel.activated.connect(self._toggle_right_panel)
        sc_tab = QShortcut(QKeySequence("Tab"), self)
        sc_tab.activated.connect(self._toggle_right_panel)

    def _set_view_mode(self, mode: str):
        self._view_mode = mode
        if mode == "split":
            self.hud.setVisible(True)
            self.hud.setMaximumHeight(260)
            self.hud.setMinimumHeight(180)
            self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.chat_stream.setVisible(True)
        elif mode == "mila":
            self.hud.setVisible(True)
            self.hud.setMaximumHeight(16777215)
            self.hud.setMinimumHeight(320)
            self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.chat_stream.setVisible(False)
        elif mode == "chat":
            self.hud.setVisible(False)
            self.chat_stream.setVisible(True)

        for k, btn in getattr(self, "_mode_btns", {}).items():
            if k == mode:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.PRI_DARK}; color: #ffffff;
                        border: 1px solid {C.PRI}; border-radius: 6px; padding: 0 10px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.BG_CARD}; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 6px; padding: 0 10px;
                    }}
                    QPushButton:hover {{
                        background: {C.BG_HOVER}; color: {C.WHITE}; border: 1px solid {C.BORDER_HI};
                    }}
                """)

    def _on_log_received(self, text: str):
        tl = text.lower()
        if tl.startswith("you:") or tl.startswith("tú:") or tl.startswith("tu:") or tl.startswith("user:"):
            msg = text.split(":", 1)[1].strip()
            self.chat_stream.append_chat("you", msg)
        elif tl.startswith("mila:"):
            msg = text.split(":", 1)[1].strip()
            self.chat_stream.append_chat("mila", msg)
            self.hud.set_subtitle(msg)
        elif tl.startswith("file:") or tl.startswith("archivo:"):
            self.chat_stream.append_chat("tool", text)
        elif tl.startswith("err:") or "[error]" in tl:
            self.chat_stream.append_chat("err", text)
        elif tl.startswith("sys:"):
            self.chat_stream.append_chat("sys", text[4:].strip())
        else:
            self.chat_stream.append_chat("mila", text)
            self.hud.set_subtitle(text)

        self._log.append_log(text)

    def _apply_emotion(self, emotion: str):
        self.hud.set_emotion(emotion)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 480, 410
            cw = self.centralWidget()
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()

        cpu = snap["cpu"]
        self._card_cpu.set_value(cpu, f"{cpu:.0f}%")

        mem = snap["mem"]
        self._card_mem.set_value(mem, f"{mem:.0f}%")

        net = snap["net"]
        net_str = f"{net*1024:.0f} KB/s" if net < 1.0 else f"{net:.1f} MB/s"
        net_pct = min(100, net * 10)
        self._card_net.set_value(net_pct, net_str)

        gpu = snap["gpu"]
        if gpu >= 0:
            self._card_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._card_gpu.set_value(0, "N/A")

        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._card_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._card_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"◷ Activo: {h:02d}h {m:02d}m")
        except Exception:
            self._uptime_lbl.setText("◷ Activo: --")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"⎇ Procesos: {proc_count}")
        except Exception:
            self._proc_lbl.setText("⎇ Procesos: --")

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(56)
        w.setStyleSheet(f"""
            QWidget {{
                background: {C.BG_DARK};
                border-bottom: 1px solid {C.BORDER};
            }}
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(18, 0, 18, 0)

        # Left: Brand Logo & Pill
        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)

        logo_path = BASE_DIR / "assets" / "mila_logo_cyan.png"
        if not logo_path.exists():
            logo_path = BASE_DIR / "assets" / "mila_logo.png"

        ai_icon = QLabel()
        if logo_path.exists():
            pm = QPixmap(str(logo_path)).scaled(
                36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            ai_icon.setPixmap(pm)
        else:
            ai_icon.setText("◈")
            ai_icon.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            ai_icon.setStyleSheet(f"color: {C.PRI};")
        ai_icon.setStyleSheet("background: transparent; border: none;")
        brand_row.addWidget(ai_icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("M.I.L.A")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none; letter-spacing: 2px;")
        title_col.addWidget(title)

        sub = QLabel("Mi Inteligencia de Lenguaje Avanzada")
        sub.setFont(QFont("Segoe UI", 7))
        sub.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        title_col.addWidget(sub)
        brand_row.addLayout(title_col)

        status_badge = QLabel("●  ACTIVA")
        status_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        status_badge.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(0, 255, 136, 0.08);
            border: 1px solid rgba(0, 255, 136, 0.25);
            border-radius: 4px;
            padding: 3px 8px;
            margin-left: 8px;
        """)
        brand_row.addWidget(status_badge)

        lay.addLayout(brand_row)
        lay.addStretch()

        # Selector de vista interactivo (estilo Hermes Desktop)
        self._mode_btns: dict[str, QPushButton] = {}
        mode_lay = QHBoxLayout()
        mode_lay.setSpacing(4)
        for key, label in [("split", "⊞ Dividido"), ("mila", "▣ Solo Mila"), ("chat", "≡ Solo Chat")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Segoe UI", 8))
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._set_view_mode(k))
            mode_lay.addWidget(btn)
            self._mode_btns[key] = btn
        lay.addLayout(mode_lay)
        lay.addSpacing(14)

        # Side panel quick toggle in header
        self._panel_btn = QPushButton("≡  Consola && Archivos")
        self._panel_btn.setFont(QFont("Segoe UI", 8))
        self._panel_btn.setFixedHeight(28)
        self._panel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._panel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.BG_CARD};
                color: {C.TEXT_MED};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
                padding: 0 10px;
                margin-right: 14px;
            }}
            QPushButton:hover {{
                background: {C.BG_HOVER};
                color: {C.PRI};
                border: 1px solid {C.PRI_DARK};
            }}
        """)
        self._panel_btn.clicked.connect(self._toggle_right_panel)
        lay.addWidget(self._panel_btn)

        # Right: Clock & Date Card
        right_col = QVBoxLayout()
        right_col.setSpacing(1)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent; border: none;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)

        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Segoe UI", 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)

        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"""
            QWidget {{
                background: {C.BG_DARK};
                border: 1px solid {C.BORDER};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        # Header Title
        hdr = QLabel("◈  TELEMETRÍA")
        hdr.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none; padding-bottom: 2px;")
        lay.addWidget(hdr)

        # Metric Cards
        self._card_cpu = MetricCard("⎈", "CPU", (C.PRI, C.VIOLET))
        self._card_mem = MetricCard("≡", "RAM", ("#38bdf8", C.GREEN))
        self._card_net = MetricCard("⇋", "RED", (C.GREEN, "#22c55e"))
        self._card_gpu = MetricCard("◈", "GPU", (C.VIOLET, C.PINK))
        self._card_tmp = MetricCard("℃", "TEMP", (C.AMBER, C.RED))

        for card in [self._card_cpu, self._card_mem, self._card_net,
                     self._card_gpu, self._card_tmp]:
            lay.addWidget(card)

        # System Summary Card
        info_panel = QWidget()
        info_panel.setStyleSheet(f"""
            background: {C.BG_CARD};
            border: 1px solid {C.BORDER_DIM};
            border-radius: 6px;
        """)
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(8, 6, 8, 6)
        ip_lay.setSpacing(3)

        self._uptime_lbl = QLabel("◷ Activo: --")
        self._uptime_lbl.setFont(QFont("Segoe UI", 7))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("⎇ Procesos: --")
        self._proc_lbl.setFont(QFont("Segoe UI", 7))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "Windows 11", "Darwin": "macOS", "Linux": "Linux"}.get(_OS, _OS)
        os_lbl = QLabel(f"◈ OS: {os_name}")
        os_lbl.setFont(QFont("Segoe UI", 7))
        os_lbl.setStyleSheet(f"color: {C.AMBER}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)

        # Document Drop Zone
        lay.addSpacing(8)
        dh = QLabel("⎘  DOCUMENTOS")
        dh.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        dh.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        lay.addWidget(dh)

        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("Arrastra archivos o usa 📎")
        self._file_hint.setFont(QFont("Segoe UI", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        lay.addStretch()

        return w

    def _build_floating_prompt_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"""
            QWidget {{
                background: {C.BG_DARK};
                border: 1px solid {C.BORDER};
                border-radius: 24px;
            }}
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(8)

        # Quick Mic Toggle Button
        self._mic_quick_btn = QPushButton("🎙️ Escuchando")
        self._mic_quick_btn.setFixedHeight(34)
        self._mic_quick_btn.setFixedWidth(130)
        self._mic_quick_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._mic_quick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mic_quick_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.GREEN_BG}; color: {C.GREEN};
                border: 1px solid {C.GREEN}; border-radius: 17px;
            }}
            QPushButton:hover {{ background: #0a3a2c; }}
        """)
        self._mic_quick_btn.clicked.connect(self._toggle_mute)
        lay.addWidget(self._mic_quick_btn)

        # Attach Document / File Button (Paperclip)
        self._clip_btn = QPushButton("📎")
        self._clip_btn.setFixedSize(34, 34)
        self._clip_btn.setFont(QFont("Segoe UI", 12))
        self._clip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clip_btn.setToolTip("Subir o adjuntar documento o imagen para MILA")
        self._clip_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.BG_CARD}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER_DIM}; border-radius: 17px;
            }}
            QPushButton:hover {{
                background: {C.BG_HOVER}; color: {C.PRI}; border: 1px solid {C.PRI_DARK};
            }}
        """)
        self._clip_btn.clicked.connect(lambda: self._drop_zone._browse())
        lay.addWidget(self._clip_btn)

        # Quick Text Input (Hermes Desktop style)
        self._quick_input = QLineEdit()
        self._quick_input.setPlaceholderText("+ Escribe una instrucción o pregunta a Mila...")
        self._quick_input.setFont(QFont("Segoe UI", 9))
        self._quick_input.setFixedHeight(34)
        self._quick_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.BG_CARD}; color: {C.WHITE};
                border: 1px solid {C.BORDER_DIM}; border-radius: 17px; padding: 4px 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRI};
                background: {C.BG_CARD_ALT};
            }}
        """)
        self._quick_input.returnPressed.connect(self._send_quick)
        lay.addWidget(self._quick_input)

        # Quick Send Button
        send_btn = QPushButton("➤")
        send_btn.setFixedSize(34, 34)
        send_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: #04070c;
                border: none; border-radius: 17px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #4df6ff; }}
        """)
        send_btn.clicked.connect(self._send_quick)
        lay.addWidget(send_btn)

        return bar

    def _send_quick(self):
        txt = self._quick_input.text().strip()
        if not txt:
            return
        self._quick_input.clear()
        self._on_log_received(f"Tú: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _toggle_right_panel(self):
        vis = not self._right_panel.isVisible()
        self._right_panel.setVisible(vis)
        accent_style = f"""
            QPushButton {{
                background: {C.PRI_DARK}; color: {C.WHITE};
                border: 1px solid {C.PRI}; border-radius: 17px; padding: 0 14px;
            }}
        """
        normal_style = f"""
            QPushButton {{
                background: {C.BG_CARD}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 17px; padding: 0 14px;
            }}
            QPushButton:hover {{
                background: {C.BG_HOVER}; color: {C.WHITE}; border: 1px solid {C.PRI};
            }}
        """
        if hasattr(self, "_toggle_side_btn"):
            self._toggle_side_btn.setStyleSheet(accent_style if vis else normal_style)
        if hasattr(self, "_panel_btn"):
            self._panel_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PRI_DARK if vis else C.BG_CARD};
                    color: {C.WHITE if vis else C.TEXT_MED};
                    border: 1px solid {C.PRI if vis else C.BORDER};
                    border-radius: 6px;
                    padding: 0 10px;
                    margin-right: 14px;
                }}
            """)

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"""
            QWidget {{
                background: {C.BG_DARK};
                border: 1px solid {C.BORDER};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Header for Log with Clear button
        log_hdr = QHBoxLayout()
        log_title = QLabel("≡  REGISTRO DE ACTIVIDAD")
        log_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        log_title.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        log_hdr.addWidget(log_title)
        log_hdr.addStretch()

        clear_btn = QPushButton("✕ Limpiar")
        clear_btn.setFont(QFont("Segoe UI", 7))
        clear_btn.setFixedHeight(20)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.BG_CARD}; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER_DIM}; border-radius: 3px; padding: 0 6px;
            }}
            QPushButton:hover {{
                color: {C.WHITE}; border: 1px solid {C.BORDER}; background: {C.BG_HOVER};
            }}
        """)
        clear_btn.clicked.connect(lambda: self._log.clear())
        log_hdr.addWidget(clear_btn)
        lay.addLayout(log_hdr)

        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        # Consola de desarrollador y comandos adicionales

        # Command Input Field
        input_hdr = QHBoxLayout()
        input_title = QLabel("›  COMANDO POR TEXTO")
        input_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        input_title.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        input_hdr.addWidget(input_title)
        input_hdr.addStretch()
        lay.addLayout(input_hdr)

        lay.addLayout(self._build_input_row())

        # Main Microphone Button
        self._mute_btn = QPushButton("●  MICRÓFONO ACTIVO")
        self._mute_btn.setFixedHeight(36)
        self._mute_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        # Fullscreen Shortcut Action
        fs_btn = QPushButton("⛶  Pantalla Completa  [F11]")
        fs_btn.setFixedHeight(28)
        fs_btn.setFont(QFont("Segoe UI", 8))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.BG_CARD}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {C.BG_HOVER}; color: {C.PRI}; border: 1px solid {C.BORDER_HI};
            }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        return w

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Escribe una instrucción o pregunta a Mila…")
        self._input.setFont(QFont("Segoe UI", 9))
        self._input.setFixedHeight(34)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.BG_CARD}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 6px; padding: 4px 10px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRI};
                background: {C.BG_CARD_ALT};
            }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("➤")
        send.setFixedSize(34, 34)
        send.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: #04070c;
                border: none; border-radius: 6px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: #4df6ff;
            }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(26)
        w.setStyleSheet(f"background: {C.BG_DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont("Segoe UI", 7))
            l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            return l

        lay.addWidget(_fl("[F4] Silenciar  ·  [F11] Pantalla Completa  ·  [F2 / ≡] Consola & Archivos"))
        lay.addStretch()
        lay.addWidget(_fl("MILA — Asistente de IA Personal con Audio Nativo"))
        lay.addStretch()
        lay.addWidget(_fl("© MILA", C.PRI_DARK))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"[{icon}]  {p.name} ({size}) — Pregúntale a MILA sobre este archivo")
        self.chat_stream.append_chat("tool", f"Archivo seleccionado: {p.name} ({size})")
        self._log.append_log(f"FILE: {p.name} ({size}) cargado exitosamente")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Micrófono silenciado.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Micrófono activo.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("⊘  MICRÓFONO SILENCIADO")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.RED_BG}; color: {C.RED};
                    border: 1px solid {C.RED}; border-radius: 6px;
                }}
                QPushButton:hover {{ background: #3d0c16; }}
            """)
            if hasattr(self, "_mic_quick_btn"):
                self._mic_quick_btn.setText("⊘ Silenciado")
                self._mic_quick_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.RED_BG}; color: {C.RED};
                        border: 1px solid {C.RED}; border-radius: 17px;
                    }}
                    QPushButton:hover {{ background: #3d0c16; }}
                """)
        else:
            self._mute_btn.setText("●  MICRÓFONO ACTIVO")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.GREEN_BG}; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 6px;
                }}
                QPushButton:hover {{ background: #0a3a2c; }}
            """)
            if hasattr(self, "_mic_quick_btn"):
                self._mic_quick_btn.setText("🎙️ Escuchando")
                self._mic_quick_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.GREEN_BG}; color: {C.GREEN};
                        border: 1px solid {C.GREEN}; border-radius: 17px;
                    }}
                    QPushButton:hover {{ background: #0a3a2c; }}
                """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt:
            return
        self._input.clear()
        self._on_log_received(f"Tú: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.set_state(state)

    def _check_config(self) -> bool:
        if not API_FILE.exists():
            return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 480, 410
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._log.append_log(f"SYS: MILA inicializada. SO={os_name.upper()}. MILA en línea.")


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class MilaUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def set_emotion(self, emotion: str):
        self._win._emotion_sig.emit(emotion)

    def set_dancing(self, on: bool):
        self._win._dance_sig.emit(on)

    def set_mouth_level(self, level: float):
        self._win._mouth_sig.emit(level)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")
