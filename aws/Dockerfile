# ==============================================================================
# Dockerfile para MILA en AWS (EC2 / ECS / Container Runner)
# Soporte para Python 3.11, PortAudio, Xvfb (Virtual Display) y Playwright
# ==============================================================================

FROM python:3.11-slim

# Evitar prompts interactivos durante apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Instalar dependencias de sistema: audio, virtual display, librerías gráficas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    ffmpeg \
    libasound2 \
    libasound2-dev \
    libasound2-plugins \
    alsa-utils \
    portaudio19-dev \
    pulseaudio \
    pulseaudio-utils \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    xvfb \
    x11-utils \
    libpq-dev \
    default-libmysqlclient-dev \
    pkg-config \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements e instalar dependencias Python
COPY requirements.txt .

# Instalar dependencias Python (excluyendo bibliotecas exclusivas de Windows como pywinauto, comtypes, pycaw, winsdk, win10toast)
RUN grep -v -E "win10toast|winsdk|pycaw|comtypes|pywinauto" requirements.txt > requirements.linux.txt && \
    pip install --no-cache-dir -r requirements.linux.txt && \
    pip install --no-cache-dir boto3

# Instalar navegadores para Playwright (Chromium)
RUN playwright install chromium && \
    playwright install-deps chromium || true

# Copiar el código fuente del proyecto
COPY . /app

# Asegurar directorios de memoria y configuración
RUN mkdir -p /app/memory /app/config /app/assets /app/training

# Configuración de variables de entorno predeterminadas
ENV DISPLAY=:99
ENV OS_SYSTEM=linux

# Script de arranque para iniciar Xvfb (virtual display para headless UI/Screen) y MILA
RUN echo '#!/bin/bash\n\
Xvfb :99 -screen 0 1920x1080x24 &\n\
sleep 1\n\
python main.py\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
