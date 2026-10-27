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

case "$1" in
    --status|-s)
        if ping -c 1 -W 2 "$PING_TARGET" > /dev/null 2>&1; then
            echo "Status: ONLINE (Connected)"
            exit 0
        else
            echo "Status: OFFLINE (Captive Portal Challenge)"
            exit 2
        fi
        ;;
    --bounce|-r)
        IFACE=$(ip route show default 2>/dev/null | awk '{print $5}' | head -n 1)
        IFACE="${IFACE:-enp4s0}"
        echo "Resetting interface $IFACE..."
        nmcli dev disconnect "$IFACE" && sleep 1 && nmcli dev connect "$IFACE"
        exit $?
        ;;
    --help|-h)
        echo "Usage: login.sh [options]"
        echo "Options:"
        echo "  (no args)       Run continuous keepalive daemon loop"
        echo "  --once, -1      Run single login attempt and exit"
        echo "  --status, -s    Check if currently online"
        echo "  --bounce, -r    Reset/bounce network interface link"
        echo "  --help, -h      Show this help message"
        exit 0
        ;;
    --once|-1)
        ONCE_MODE=1
        ;;
esac

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== IISERB Autologin started (PID $$) ==="

while true; do
    load_config

    # --- Online check ---
    if ping -c 1 -W 2 "$PING_TARGET" > /dev/null 2>&1; then
        if [ "$ONCE_MODE" = "1" ]; then
            log "Already online. Exiting."
            exit 0
        fi
        sleep "${CHECK_INTERVAL:-60}"
        continue
    fi

    log "Offline detected. Attempting login for $USERNAME..."

    # Clear old cookies before a fresh attempt
    rm -f "$COOKIE_JAR"

    # Step 0: Obtain magic challenge token using forced IPv4 (-4) across multiple probe endpoints
    MAGIC=""
    for PROBE in "$PROBE_URL" "http://connectivity-check.ubuntu.com/" "http://detectportal.firefox.com/success.txt" "http://neverssl.com" "http://1.1.1.1"; do
        HEADERS_AND_BODY=$(curl -4 -k -s -i --connect-timeout 4 "$PROBE" 2>/dev/null)
        MAGIC=$(echo "$HEADERS_AND_BODY" | grep -oE 'fgtauth\?[a-f0-9]{16,32}' | head -1 | cut -d'?' -f2)
        if [ -n "$MAGIC" ]; then
            break
        fi
    done

    # If FortiGate dropped the session and is blackholing requests, bounce the interface link to prompt the gateway
    if [ -z "$MAGIC" ]; then
        IFACE=$(ip route show default 2>/dev/null | awk '{print $5}' | head -n 1)
        if [ -z "$IFACE" ]; then
            IFACE="enp4s0"
        fi
        log "No challenge token found. Refreshing network interface ($IFACE) to prompt gateway..."
        if command -v nmcli >/dev/null 2>&1; then
            nmcli dev disconnect "$IFACE" >/dev/null 2>&1
            sleep 1
            nmcli dev connect "$IFACE" >/dev/null 2>&1
            sleep 2
            # Re-probe immediately
            for PROBE in "$PROBE_URL" "http://connectivity-check.ubuntu.com/" "http://detectportal.firefox.com/success.txt"; do
                HEADERS_AND_BODY=$(curl -4 -k -s -i --connect-timeout 4 "$PROBE" 2>/dev/null)
                MAGIC=$(echo "$HEADERS_AND_BODY" | grep -oE 'fgtauth\?[a-f0-9]{16,32}' | head -1 | cut -d'?' -f2)
                if [ -n "$MAGIC" ]; then
                    break
                fi
            done
        fi
    fi

    if [ -z "$MAGIC" ]; then
        log "No magic token found in probe response. Retrying in 15s..."
        sleep 15
        continue
    fi

    log "Magic token: $MAGIC"

    # Step 1: Hit the fgtauth URL to initialise session and save cookies
    curl -4 -k -s -c "$COOKIE_JAR" --connect-timeout 8 "$GATEWAY/fgtauth?$MAGIC" > /dev/null

    # Step 2: POST credentials
    RESPONSE=$(curl -4 -k -s -L --connect-timeout 10 -X POST "$GATEWAY/" \
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
        if [ "$ONCE_MODE" = "1" ]; then
            exit 0
        fi

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

            # Send keepalive request to FortiGate periodically
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