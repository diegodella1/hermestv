#!/bin/bash
# Hermes TV — System Setup Script
# Run as root: sudo bash scripts/setup.sh

set -euo pipefail

echo "=== Hermes TV Setup ==="

# 1. Create hermes user
if ! id hermes &>/dev/null; then
    echo "[+] Creating user hermes..."
    useradd -r -m -s /bin/bash hermes
else
    echo "[=] User hermes already exists"
fi

# 2. Install system packages
echo "[+] Installing system packages..."
apt-get update
apt-get install -y espeak-ng ffmpeg curl

# 3. Install Piper TTS
PIPER_VERSION="2023.11.14-2"
PIPER_DIR="/usr/local/lib/piper"
if [ ! -f /usr/local/bin/piper ]; then
    echo "[+] Installing Piper TTS..."
    mkdir -p "$PIPER_DIR"
    cd /tmp
    curl -L -o piper.tar.gz "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_aarch64.tar.gz"
    tar xzf piper.tar.gz -C "$PIPER_DIR" --strip-components=1
    ln -sf "$PIPER_DIR/piper" /usr/local/bin/piper
    rm piper.tar.gz
else
    echo "[=] Piper already installed"
fi

# 4. Download Piper models
MODELS_DIR="/opt/hermes/models"
mkdir -p "$MODELS_DIR"
for model in en_US-lessac-high en_US-ryan-high; do
    if [ ! -f "$MODELS_DIR/${model}.onnx" ]; then
        echo "[+] Downloading Piper model: $model..."
        curl -L -o "$MODELS_DIR/${model}.onnx" \
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/${model}/en_US-${model#en_US-}.onnx"
        curl -L -o "$MODELS_DIR/${model}.onnx.json" \
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/${model}/en_US-${model#en_US-}.onnx.json"
    else
        echo "[=] Model $model already exists"
    fi
done

# 5. Create directory structure
echo "[+] Creating directories..."
mkdir -p /opt/hermes/{data/{logs,breaks,stings},models}
mkdir -p /tmp/hls_video

# 6. Python venv
if [ ! -d /opt/hermes/venv ]; then
    echo "[+] Creating Python venv..."
    python3 -m venv /opt/hermes/venv
    /opt/hermes/venv/bin/pip install --upgrade pip
    /opt/hermes/venv/bin/pip install -r /opt/hermes/requirements.txt
else
    echo "[=] Python venv already exists"
fi

# 7. Set ownership
echo "[+] Setting ownership..."
chown -R hermes:hermes /opt/hermes
chown -R hermes:hermes /tmp/hls_video

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to /opt/hermes/.env and fill in API keys"
echo "  2. Run: scripts/deploy.sh"
echo "  3. Run: sudo systemctl start hermes.target"
echo ""
echo "Verify:"
echo "  piper --help"
echo "  ffmpeg -version"
echo "  ls /opt/hermes/models/"
