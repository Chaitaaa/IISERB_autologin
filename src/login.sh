#!/bin/bash

# Default Configuration
USERNAME=""
PASSWORD=""
PROBE_URL="http://connectivity-check.ubuntu.com/"
GATEWAY="https://gateway.iiserb.ac.in:1003"
PING_TARGET="1.1.1.1"
CHECK_INTERVAL=60
KEEPALIVE_INTERVAL=10
COOKIE_JAR="/tmp/fgt_cookies.txt"
LOG_FILE="/tmp/iiserb_autologin.log"

CONFIG_FILE="$HOME/.config/iiserb_login/config.json"

load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        eval "$(python3 -c "
import json, os
try:
    with open(os.path.expanduser('~/.config/iiserb_login/config.json')) as f:
        c = json.load(f)
        for k in ['USERNAME', 'PASSWORD', 'PROBE_URL', 'GATEWAY', 'PING_TARGET', 'CHECK_INTERVAL', 'KEEPALIVE_INTERVAL', 'COOKIE_JAR', 'LOG_FILE']:
            if k in c and c[k] is not None:
                val = str(c[k]).replace('\'', '\'\\\'\'')
                print(f\"{k}='{val}'\")
except Exception:
    pass
" 2>/dev/null)"
    fi
}

load_config

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== IISERB Autologin started (PID $$) ==="

while true; do
    load_config

    if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
        log "Credentials not configured yet. Please open IISERB Login app to set credentials."
        sleep 30
        continue
    fi

    # --- Online check ---
    if ping -c 1 -W 2 "$PING_TARGET" > /dev/null 2>&1; then
        sleep "${CHECK_INTERVAL:-60}"
        continue
    fi

    log "Offline detected. Attempting login for $USERNAME..."

    # Clear old cookies before a fresh attempt
    rm -f "$COOKIE_JAR"

    # Fetch probe URL including headers (-i) to catch 302 Location redirect
    HEADERS_AND_BODY=$(curl -k -s -i --connect-timeout 8 "$PROBE_URL" 2>/dev/null)

    # Try to extract magic token from: Location header OR page body
    MAGIC=$(echo "$HEADERS_AND_BODY" | grep -oE 'fgtauth\?[a-f0-9]{16,32}' | head -1 | cut -d'?' -f2)

    if [ -z "$MAGIC" ]; then
        log "No magic token found in probe response. Retrying in 15s..."
        sleep 15
        continue
    fi

    log "Magic token: $MAGIC"

    # Step 1: Hit the fgtauth URL to initialise session and save cookies
    curl -k -s -c "$COOKIE_JAR" --connect-timeout 8 "$GATEWAY/fgtauth?$MAGIC" > /dev/null

    # Step 2: POST credentials
    RESPONSE=$(curl -k -s -L --connect-timeout 10 -X POST "$GATEWAY/" \
        -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
        -H "Origin: $GATEWAY" \
        -H "Referer: $GATEWAY/fgtauth?$MAGIC" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        --data-urlencode "4Tredir=$PROBE_URL" \
        --data-urlencode "magic=$MAGIC" \
        --data-urlencode "username=$USERNAME" \
        --data-urlencode "password=$PASSWORD" 2>/dev/null)

    log "Gateway POST done."

    # Extract keepalive token from response (FortiGate sends /keepalive?<token>)
    KEEPALIVE_TOKEN=$(echo "$RESPONSE" | grep -oE 'keepalive\?[a-f0-9]{16,32}' | head -1 | cut -d'?' -f2)

    sleep 5

    # Step 3: Verify
    if ping -c 1 -W 2 "$PING_TARGET" > /dev/null 2>&1; then
        log "Login SUCCESS for $USERNAME."

        # Step 4: Keepalive loop — ping every CHECK_INTERVAL, send keepalive every KEEPALIVE_INTERVAL
        KEEPALIVE_COUNTER=0
        while true; do
            load_config
            sleep "${CHECK_INTERVAL:-60}"

            if ! ping -c 1 -W 2 "$PING_TARGET" > /dev/null 2>&1; then
                log "Connection lost during keepalive. Re-authenticating..."
                break
            fi

            KEEPALIVE_COUNTER=$((KEEPALIVE_COUNTER + 1))

            INTERVAL_MINUTES=${KEEPALIVE_INTERVAL:-10}
            INTERVAL_CHECKS=$(( INTERVAL_MINUTES * 60 / ${CHECK_INTERVAL:-60} ))
            if [ "$INTERVAL_CHECKS" -le 0 ]; then
                INTERVAL_CHECKS=10
            fi

            if [ -n "$KEEPALIVE_TOKEN" ] && [ $((KEEPALIVE_COUNTER % INTERVAL_CHECKS)) -eq 0 ]; then
                curl -k -s --connect-timeout 5 \
                    -b "$COOKIE_JAR" \
                    "$GATEWAY/keepalive?$KEEPALIVE_TOKEN" > /dev/null 2>&1
                log "Keepalive ping sent."
            fi
        done
    else
        log "Login FAILED. Retrying in 20s..."
        sleep 20
    fi
done
