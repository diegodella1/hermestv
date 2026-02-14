FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps: Liquidsoap, FFmpeg, espeak-ng, Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    liquidsoap \
    ffmpeg \
    espeak-ng \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Piper TTS (aarch64 pre-built binary)
ARG PIPER_VERSION=2023.11.14-2
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then PIPER_ARCH="aarch64"; else PIPER_ARCH="$ARCH"; fi && \
    curl -L -o /tmp/piper.tar.gz \
      "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PIPER_ARCH}.tar.gz" && \
    mkdir -p /usr/local/lib/piper && \
    tar xzf /tmp/piper.tar.gz -C /usr/local/lib/piper --strip-components=1 && \
    ln -sf /usr/local/lib/piper/piper /usr/local/bin/piper && \
    rm /tmp/piper.tar.gz

# Piper voice models
RUN mkdir -p /opt/hermes/models && \
    curl -L -o /opt/hermes/models/en_US-lessac-high.onnx \
      "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx" && \
    curl -L -o /opt/hermes/models/en_US-lessac-high.onnx.json \
      "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx.json" && \
    curl -L -o /opt/hermes/models/en_US-ryan-high.onnx \
      "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx" && \
    curl -L -o /opt/hermes/models/en_US-ryan-high.onnx.json \
      "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx.json"

# Create directories
RUN mkdir -p /opt/hermes/data/{logs,breaks,stings} /opt/hermes/music /tmp/hls

WORKDIR /opt/hermes

# Python deps
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt supervisor

# Copy app code
COPY . .

# Make scripts executable
RUN chmod +x scripts/*.sh scripts/*.py

# Env defaults (overridable via Coolify env vars)
ENV HERMES_DATA_DIR=/opt/hermes/data
ENV HERMES_MUSIC_DIR=/opt/hermes/music
ENV HERMES_MODELS_DIR=/opt/hermes/models
ENV HERMES_HLS_DIR=/tmp/hls
ENV HERMES_DB_PATH=/opt/hermes/data/hermes.db
ENV LIQUIDSOAP_SOCKET=/tmp/liquidsoap.sock
ENV HERMES_HOST=0.0.0.0
ENV HERMES_PORT=8100
ENV PIPER_BIN=/usr/local/bin/piper
ENV HERMES_API_KEY=changeme

EXPOSE 8100

ENTRYPOINT ["/opt/hermes/scripts/entrypoint.sh"]
CMD ["supervisord", "-n", "-c", "/opt/hermes/supervisord.conf"]
