#!/bin/bash
# Hermes TV — Watchdog
# Monitors core service, restarts if needed.

LOGFILE="/opt/hermes/data/logs/watchdog.log"
CHECK_INTERVAL=15
FAIL_THRESHOLD=3

declare -A fail_count
fail_count[core]=0

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

housekeeping() {
    # Clean old break audio/video (>24h)
    find /opt/hermes/data/breaks/ -name "*.mp3" -mmin +1440 -delete 2>/dev/null
    find /opt/hermes/data/breaks/ -name "*.wav" -mmin +1440 -delete 2>/dev/null
    find /opt/hermes/data/breaks/ -name "*.mp4" -mmin +1440 -delete 2>/dev/null
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
    check_service "core" "hermes-core"

    cycle=$(( cycle + 1 ))
    if [ $((cycle % 100)) -eq 0 ]; then
        housekeeping
    fi

    sleep $CHECK_INTERVAL
done
