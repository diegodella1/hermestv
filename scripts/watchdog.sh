#!/bin/bash
# Hermes Radio — Watchdog
# Monitors services + HLS freshness, restarts if needed.

LOGFILE="/opt/hermes/data/logs/watchdog.log"
CHECK_INTERVAL=15
MAX_HLS_AGE=30
FAIL_THRESHOLD=3
HLS_FILE="/tmp/hls/radio.m3u8"

declare -A fail_count
fail_count[playout]=0
fail_count[core]=0
fail_count[caddy]=0
fail_count[hls]=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOGFILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

check_service() {
    local name=$1
    local service=$2
    if systemctl is-active --quiet "$service"; then
        fail_count[$name]=0
        return 0
    else
        fail_count[$name]=$(( ${fail_count[$name]} + 1 ))
        log "WARN: $service not active (fail ${fail_count[$name]}/$FAIL_THRESHOLD)"
        if [ ${fail_count[$name]} -ge $FAIL_THRESHOLD ]; then
            log "ERROR: $service failed $FAIL_THRESHOLD times. Restarting..."
            sudo systemctl restart "$service"
            fail_count[$name]=0
            sleep 5
        fi
        return 1
    fi
}

check_hls_freshness() {
    if [ ! -f "$HLS_FILE" ]; then
        fail_count[hls]=$(( ${fail_count[hls]} + 1 ))
        log "WARN: $HLS_FILE not found (fail ${fail_count[hls]}/$FAIL_THRESHOLD)"
    else
        local age=$(( $(date +%s) - $(stat -c %Y "$HLS_FILE") ))
        if [ $age -gt $MAX_HLS_AGE ]; then
            fail_count[hls]=$(( ${fail_count[hls]} + 1 ))
            log "WARN: $HLS_FILE is ${age}s old (fail ${fail_count[hls]}/$FAIL_THRESHOLD)"
        else
            fail_count[hls]=0
            return 0
        fi
    fi
    if [ ${fail_count[hls]} -ge $FAIL_THRESHOLD ]; then
        log "ERROR: HLS stale/missing. Restarting playout..."
        sudo systemctl restart hermes-playout
        fail_count[hls]=0
        sleep 10
    fi
    return 1
}

housekeeping() {
    # Clean old break audio (>24h)
    find /opt/hermes/data/breaks/ -name "*.mp3" -mmin +1440 -delete 2>/dev/null
    find /opt/hermes/data/breaks/ -name "*.wav" -mmin +1440 -delete 2>/dev/null
    # Rotate large logs
    for f in /opt/hermes/data/logs/*.log; do
        if [ -f "$f" ] && [ $(stat -c %s "$f" 2>/dev/null || echo 0) -gt 52428800 ]; then
            mv "$f" "${f}.old"
            log "Rotated $f"
        fi
    done
}

log "Watchdog started"
cycle=0

while true; do
    check_service "playout" "hermes-playout"
    check_service "core" "hermes-core"
    check_service "caddy" "hermes-caddy"
    check_hls_freshness

    cycle=$(( cycle + 1 ))
    if [ $((cycle % 100)) -eq 0 ]; then
        housekeeping
    fi

    sleep $CHECK_INTERVAL
done
