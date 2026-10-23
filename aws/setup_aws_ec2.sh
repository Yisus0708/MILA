#!/bin/bash
# ==============================================================================
# Script de aprovisionamiento de AWS EC2 (Ubuntu 22.04 / 24.04 LTS) para MILA
# ==============================================================================

set -e

echo "=========================================================="
echo "🚀 Configurando entorno de AWS EC2 para MILA..."
echo "=========================================================="

# 1. Actualizar repositorios
sudo apt-get update && sudo apt-get upgrade -y

# 2. Instalar paquetes esenciales
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    ffmpeg \
    libasound2 \
    libasound2-dev \
    portaudio19-dev \
    pulseaudio \
    xvfb \
    x11-utils \
    curl \
    ca-certificates

# 3. Instalar Docker y Docker Compose
if ! command -v docker &> /dev/null; then
    echo "📦 Instalando Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
fi

if ! command -v docker-compose &> /dev/null; then
    echo "📦 Instalando Docker Compose..."
    sudo apt-get install -y docker-compose-plugin
fi

# 4. Crear dummy sound device con ALSA/PulseAudio para emulación de audio en servidor headless
sudo modprobe snd-dummy || true

echo "=========================================================="
echo "✅ Servidor listo. Siguientes pasos:"
echo "1. Configura tus variables en .env (GEMINI_API_KEY, AWS_S3_BUCKET_NAME)"
echo "2. Ejecuta con Docker: cd aws && docker compose up -d --build"
echo "=========================================================="
