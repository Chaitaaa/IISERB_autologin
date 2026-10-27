#!/bin/bash
# ==============================================================================
# IISER Bhopal Captive Portal Keepalive Daemon
# Hardened against credential leakage, ICMP pass-through false-positives,
# and link drops.
# ==============================================================================

# Default Settings
USERNAME=""
PASSWORD=""
PROBE_URL="http://connectivity-check.ubuntu.com/"
GATEWAY="https://gateway.iiserb.ac.in:1003"
PING_TARGET="1.1.1.1"
CHECK_INTERVAL=60
KEEPALIVE_INTERVAL=3
NOTIFICATIONS_ENABLED=1

RUNTIME_BASE="${XDG_RUNTIME_DIR:-/tmp/iiserb-$UID}"
COOKIE_JAR="$RUNTIME_BASE/iiserb_login/fgt_cookies.txt"
STATE_DIR="$HOME/.local/state/iiserb_login"
LOG_FILE="$STATE_DIR/autologin.log"
CONFIG_FILE="$HOME/.config/iiserb_login/config.json"

# Ensure secure directories
mkdir -p -m 700 "$(dirname "$COOKIE_JAR")" 2>/dev/null || true
mkdir -p -m 700 "$STATE_DIR" 2>/dev/null || true

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

notify() {
    local title="$1"
    local message="$2"
    local urgency="${3:-normal}"
    if [ "$NOTIFICATIONS_ENABLED" = "1" ] && command -v notify-send >/dev/null 2>&1; then
        notify-send -a "IISERB Login" -u "$urgency" "$title" "$message" 2>/dev/null || true
    fi
}

load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        # Enforce 0600 permissions
        chmod 600 "$CONFIG_FILE" 2>/dev/null || true
        # Safe delimited parser without eval
        while IFS='=' read -r key val; do
            case "$key" in
                USERNAME) USERNAME="$val" ;;
                PASSWORD) PASSWORD="$val" ;;
                PROBE_URL) PROBE_URL="$val" ;;
                GATEWAY) GATEWAY="$val" ;;
                PING_TARGET) PING_TARGET="$val" ;;
                CHECK_INTERVAL) CHECK_INTERVAL="$val" ;;
                KEEPALIVE_INTERVAL) KEEPALIVE_INTERVAL="$val" ;;
                COOKIE_JAR) COOKIE_JAR="$val" ;;
                LOG_FILE) LOG_FILE="$val" ;;
                NOTIFICATIONS_ENABLED) NOTIFICATIONS_ENABLED="$val" ;;
            esac
        done < <(python3 -c "
import json, os
try:
    p = os.path.expanduser('~/.config/iiserb_login/config.json')
    if os.path.exists(p):
        with open(p, 'r') as f:
            c = json.load(f)
            for k, v in c.items():
                if v is not None:
                    print(f'{k}={v}')
except Exception:
    pass
" 2>/dev/null)
    fi
}

get_active_interface() {
    local iface
    iface=$(ip route show default 2>/dev/null | awk '{print $5}' | head -n 1)
    if [ -z "$iface" ]; then
        iface=$(ls -1 /sys/class/net 2>/dev/null | grep -vE '^(lo|docker|veth|tailscale|tun|tap|wg|br-)' | head -n 1)
    fi
    echo "$iface"
}

# Two-Tier online check: ICMP Ping + HTTP 204 Probe
is_online() {
    # Tier 1: Ping
    if ! ping -c 1 -W 2 "${PING_TARGET:-1.1.1.1}" > /dev/null 2>&1; then
        return 1
    fi
    # Tier 2: Captive portal HTTP check (returns 204 if unintercepted)
    local code
    code=$(curl -4 -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "${PROBE_URL:-http://connectivity-check.ubuntu.com/}" 2>/dev/null)
    if [ "$code" = "204" ]; then
        return 0
    fi
    return 1
}

# Non-destructive network link refresh
bounce_link() {
    local iface
    iface=$(get_active_interface)
    if [ -n "$iface" ]; then
        log "Refreshing network link on $iface (non-destructive ARP sync)..."
        ip neigh flush dev "$iface" 2>/dev/null || true
        if command -v nmcli >/dev/null 2>&1; then
            nmcli dev reapply "$iface" 2>/dev/null || true
        fi
    fi
}

load_config

case "$1" in
    --status|-s)
        if is_online; then
            echo "Status: ONLINE (Connected)"
            exit 0
        else
            echo "Status: OFFLINE (Captive Portal Challenge)"
            exit 2
        fi
        ;;
    --bounce|-r)
        bounce_link
        exit 0
        ;;
    --help|-h)
        echo "Usage: login.sh [options]"
        echo "Options:"
        echo "  (no args)       Run continuous keepalive daemon loop"
        echo "  --once, -1      Run single login attempt and exit"
        echo "  --status, -s    Check if currently online (Tier 1 ping + Tier 2 probe)"
        echo "  --bounce, -r    Non-destructive network link refresh"
        echo "  --help, -h      Show this help message"
        exit 0
        ;;
    --once|-1)
        ONCE_MODE=1
        ;;
esac

log "=== IISERB Autologin started (PID $$) ==="

while true; do
    load_config

    # --- Online check ---
    if is_online; then
        if [ "$ONCE_MODE" = "1" ]; then
            log "Already online. Exiting."
            exit 0
        fi
        sleep "${CHECK_INTERVAL:-60}"
        continue
    fi

    log "Offline detected. Attempting login for ${USERNAME:-unknown}..."

    # Clear old cookies
    rm -f "$COOKIE_JAR"

    # Step 0: Extract challenge token across probe endpoints
    MAGIC=""
    for PROBE in "$PROBE_URL" "http://connectivity-check.ubuntu.com/" "http://detectportal.firefox.com/success.txt" "http://neverssl.com" "http://1.1.1.1"; do
        HEADERS_AND_BODY=$(curl -4 -k -s -i --connect-timeout 4 "$PROBE" 2>/dev/null)
        MAGIC=$(echo "$HEADERS_AND_BODY" | grep -oiE 'fgtauth\?[a-z0-9]{16,64}' | head -1 | cut -d'?' -f2)
        if [ -z "$MAGIC" ]; then
            MAGIC=$(echo "$HEADERS_AND_BODY" | grep -oiE 'name=["'\''"]magic["'\''"][^>]*value=["'\''"][a-z0-9]{16,64}["'\''"]' | grep -oiE 'value=["'\''"][a-z0-9]{16,64}["'\''"]' | cut -d'"' -f2 | cut -d"'" -f2)
        fi
        if [ -n "$MAGIC" ]; then
            break
        fi
    done

    # If magic token not found, gently refresh ARP/DHCP link to prompt FortiGate
    if [ -z "$MAGIC" ]; then
        bounce_link
        sleep 2
        for PROBE in "$PROBE_URL" "http://connectivity-check.ubuntu.com/"; do
            HEADERS_AND_BODY=$(curl -4 -k -s -i --connect-timeout 4 "$PROBE" 2>/dev/null)
            MAGIC=$(echo "$HEADERS_AND_BODY" | grep -oiE 'fgtauth\?[a-z0-9]{16,64}' | head -1 | cut -d'?' -f2)
            if [ -n "$MAGIC" ]; then
                break
            fi
        done
    fi

    if [ -z "$MAGIC" ]; then
        log "No captive challenge token found. Retrying in 15s..."
        sleep 15
        continue
    fi

    log "Obtained challenge token: ${MAGIC:0:16}..."

    # Step 1: Hit fgtauth tracking link and save cookies
    curl -4 -k -s -c "$COOKIE_JAR" --connect-timeout 8 "$GATEWAY/fgtauth?$MAGIC" > /dev/null 2>&1

    # Step 2: POST credentials safely via STDIN to hide password from /proc and ps aux
    POST_DATA=$(python3 -c "
import urllib.parse, sys
u, p, m, pr = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
print(urllib.parse.urlencode({'4Tredir': pr, 'magic': m, 'username': u, 'password': p}))
" "$USERNAME" "$PASSWORD" "$MAGIC" "$PROBE_URL" 2>/dev/null)

    RESPONSE=$(printf "%s" "$POST_DATA" | curl -4 -k -s -L --connect-timeout 10 -X POST "$GATEWAY/" \
        -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
        -H "Origin: $GATEWAY" \
        -H "Referer: $GATEWAY/fgtauth?$MAGIC" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        --data-binary @- 2>/dev/null)

    log "Credentials POST submitted to gateway."

    # Extract keepalive token if present
    KEEPALIVE_TOKEN=$(echo "$RESPONSE" | grep -oiE 'keepalive\?[a-z0-9]{16,64}' | head -1 | cut -d'?' -f2)

    sleep 3

    # Step 3: Verify internet access
    if is_online; then
        log "Login SUCCESS for $USERNAME."
        notify "IISERB Login: Connected" "Successfully authenticated as $USERNAME."
        if [ "$ONCE_MODE" = "1" ]; then
            exit 0
        fi

        # Step 4: Keepalive pulse loop
        KEEPALIVE_COUNTER=0
        while true; do
            load_config
            sleep "${CHECK_INTERVAL:-60}"

            if ! is_online; then
                log "Connection lost or captive challenge active. Re-authenticating..."
                notify "IISERB Login: Reconnecting" "Connection dropped, re-authenticating..." "low"
                break
            fi

            KEEPALIVE_COUNTER=$((KEEPALIVE_COUNTER + 1))

            INTERVAL_MINUTES=${KEEPALIVE_INTERVAL:-3}
            INTERVAL_CHECKS=$(( INTERVAL_MINUTES * 60 / ${CHECK_INTERVAL:-60} ))
            if [ "$INTERVAL_CHECKS" -le 0 ]; then
                INTERVAL_CHECKS=3
            fi

            if [ -n "$KEEPALIVE_TOKEN" ] && [ $((KEEPALIVE_COUNTER % INTERVAL_CHECKS)) -eq 0 ]; then
                curl -k -s --connect-timeout 5 \
                    -b "$COOKIE_JAR" \
                    "$GATEWAY/keepalive?$KEEPALIVE_TOKEN" > /dev/null 2>&1
                log "Keepalive heartbeat sent."
            fi
        done
    else
        log "Login verification failed. Gateway rejected credentials or link issue. Retrying in 20s..."
        notify "IISERB Login: Authentication Failed" "Gateway did not grant internet. Check credentials." "critical"
        sleep 20
    fi
done
