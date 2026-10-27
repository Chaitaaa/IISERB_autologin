#!/usr/bin/env python3
"""
Backend module for IISER Bhopal Captive Portal Manager.
Handles network status checks, authentication, systemd service management,
and configuration persistence with strict permissions and sandboxed paths.
"""

import os
import sys
import json
import subprocess
import socket
import re
import time
import urllib.request
import urllib.parse
from typing import Dict, Any, Tuple, Optional

# Base directories compliant with XDG Base Directory specification
CONFIG_DIR = os.path.expanduser("~/.config/iiserb_login")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

STATE_DIR = os.path.expanduser("~/.local/state/iiserb_login")
RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR", f"/tmp/iiserb-login-{os.getuid()}")
USER_RUNTIME_DIR = os.path.join(RUNTIME_DIR, "iiserb_login")

# Default Configuration
DEFAULT_CONFIG: Dict[str, Any] = {
    "USERNAME": "",
    "PASSWORD": "",
    "PROBE_URL": "http://connectivity-check.ubuntu.com/",
    "GATEWAY": "https://gateway.iiserb.ac.in:1003",
    "PING_TARGET": "1.1.1.1",
    "CHECK_INTERVAL": 60,
    "KEEPALIVE_INTERVAL": 3,
    "COOKIE_JAR": os.path.join(USER_RUNTIME_DIR, "fgt_cookies.txt"),
    "LOG_FILE": os.path.join(STATE_DIR, "autologin.log"),
    "NOTIFICATIONS_ENABLED": True
}

SERVICE_NAME = "portal-autologin.service"


def _ensure_secure_dirs():
    """Ensure state, runtime, and config directories exist with mode 0700."""
    for d in [CONFIG_DIR, STATE_DIR, USER_RUNTIME_DIR]:
        try:
            os.makedirs(d, mode=0o700, exist_ok=True)
            # Guarantee permission in case it pre-existed with lax permissions
            os.chmod(d, 0o700)
        except Exception:
            pass


_ensure_secure_dirs()


def load_config() -> Dict[str, Any]:
    """
    Load configuration from ~/.config/iiserb_login/config.json or defaults.
    Enforces atomic mode 0600 on config.json to protect LDAP credentials.
    """
    _ensure_secure_dirs()
    cfg = DEFAULT_CONFIG.copy()

    if os.path.exists(CONFIG_PATH):
        try:
            # Enforce 0600 permissions
            try:
                os.chmod(CONFIG_PATH, 0o600)
            except Exception:
                pass

            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    cfg.update(saved)
        except Exception as e:
            print(f"Error loading config: {e}", file=sys.stderr)

    # Migrate legacy /tmp paths if found in older configurations
    if cfg.get("COOKIE_JAR", "").startswith("/tmp/fgt_cookies"):
        cfg["COOKIE_JAR"] = os.path.join(USER_RUNTIME_DIR, "fgt_cookies.txt")
    if cfg.get("LOG_FILE", "").startswith("/tmp/iiserb_autologin"):
        cfg["LOG_FILE"] = os.path.join(STATE_DIR, "autologin.log")

    return cfg


def save_config(new_config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Save configuration to ~/.config/iiserb_login/config.json with mode 0600.
    Uses atomic write to prevent partial writes.
    """
    _ensure_secure_dirs()
    try:
        cfg = load_config()
        cfg.update(new_config)
        cfg["CHECK_INTERVAL"] = int(cfg.get("CHECK_INTERVAL", 60))
        cfg["KEEPALIVE_INTERVAL"] = int(cfg.get("KEEPALIVE_INTERVAL", 3))

        # Atomic write with 0600 permissions
        temp_path = f"{CONFIG_PATH}.tmp.{os.getpid()}"
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

        os.replace(temp_path, CONFIG_PATH)
        os.chmod(CONFIG_PATH, 0o600)
        return True, "Settings saved successfully."
    except Exception as e:
        return False, f"Failed to save settings: {e}"


def send_notification(title: str, message: str, urgency: str = "normal") -> bool:
    """Send a native desktop notification via notify-send if enabled and available."""
    cfg = load_config()
    if not cfg.get("NOTIFICATIONS_ENABLED", True):
        return False
    try:
        if subprocess.run(["which", "notify-send"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            subprocess.run(
                ["notify-send", "-a", "IISERB Login", "-u", urgency, title, message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3
            )
            return True
    except Exception:
        pass
    return False


def get_default_interface() -> Optional[str]:
    """Dynamically determine the active non-virtual network interface."""
    # Method 1: Default route interface
    try:
        res = subprocess.run(
            ["ip", "route", "show", "default"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=2
        )
        if res.returncode == 0 and res.stdout:
            m = re.search(r"dev\s+(\S+)", res.stdout)
            if m:
                return m.group(1)
    except Exception:
        pass

    # Method 2: Inspect sysfs net devices excluding loopback and virtual adapters
    try:
        net_path = "/sys/class/net"
        if os.path.exists(net_path):
            candidates = []
            for dev in os.listdir(net_path):
                if dev.startswith(("lo", "docker", "veth", "tailscale", "tun", "tap", "wg", "br-")):
                    continue
                # Check operstate
                state_file = os.path.join(net_path, dev, "operstate")
                if os.path.exists(state_file):
                    with open(state_file, "r") as f:
                        if f.read().strip() == "up":
                            return dev
                candidates.append(dev)
            if candidates:
                return candidates[0]
    except Exception:
        pass

    return None


def get_network_info() -> Dict[str, str]:
    """Retrieve primary IP address, default interface, and default gateway."""
    info = {"ip": "Unknown", "interface": "Unknown", "gateway": "Unknown"}
    try:
        res = subprocess.run(
            ["ip", "route", "show", "default"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=2
        )
        if res.returncode == 0 and res.stdout:
            line = res.stdout.strip()
            gw_m = re.search(r"default via ([\d\.]+)", line)
            dev_m = re.search(r"dev (\S+)", line)
            src_m = re.search(r"src ([\d\.]+)", line)
            if gw_m:
                info["gateway"] = gw_m.group(1)
            if dev_m:
                info["interface"] = dev_m.group(1)
            if src_m:
                info["ip"] = src_m.group(1)
    except Exception:
        pass

    if info["interface"] == "Unknown":
        dev = get_default_interface()
        if dev:
            info["interface"] = dev

    return info


def check_internet(target: Optional[str] = None, probe_url: Optional[str] = None) -> Tuple[bool, float]:
    """
    Two-Tier Internet Health Check:
    Tier 1: ICMP Echo ping to target IP (1.1.1.1 or 8.8.8.8) to measure latency.
    Tier 2: HTTP 204 Probe to detect FortiGate captive portal interception.
            (FortiGate frequently allows ICMP while intercepting HTTP/HTTPS).
    Returns (is_online, latency_ms).
    """
    cfg = load_config()
    if not target:
        target = cfg.get("PING_TARGET", "1.1.1.1")
    if not probe_url:
        probe_url = cfg.get("PROBE_URL", "http://connectivity-check.ubuntu.com/")

    # Tier 1: Ping
    latency = 0.0
    ping_ok = False
    for ping_ip in [target, "8.8.8.8"]:
        try:
            cmd = ["ping", "-c", "1", "-W", "2", str(ping_ip)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
            if res.returncode == 0:
                match = re.search(r"time=([\d\.]+)\s*ms", res.stdout)
                latency = float(match.group(1)) if match else 1.0
                ping_ok = True
                break
        except Exception:
            continue

    if not ping_ok:
        return False, 0.0

    # Tier 2: HTTP Probe for Captive Portal Interception
    try:
        # Check HTTP status code using curl
        cmd = ["curl", "-4", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "3", probe_url]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=4)
        status_code = res.stdout.strip()
        # 204 No Content confirms real un-intercepted internet connection
        if status_code == "204":
            return True, latency
        # If redirected (302/303) or returning HTML login page (200), captive portal is active
        return False, latency
    except Exception:
        # Fallback probe via Python urllib
        try:
            req = urllib.request.Request(probe_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 204:
                    return True, latency
        except Exception:
            pass

    return False, latency


def bounce_interface(interface: Optional[str] = None) -> Tuple[bool, str]:
    """
    Non-destructive network link refresh.
    Flushes ARP neighbor cache and reapplies NetworkManager configuration without
    disconnecting the interface, preserving SSH sessions, VPNs, and virtual adapters.
    """
    if not interface or interface == "Unknown":
        interface = get_default_interface()
    if not interface or interface == "Unknown":
        return False, "Could not determine network interface."

    try:
        # 1. Non-destructive ARP neighbor flush
        subprocess.run(["ip", "neigh", "flush", "dev", interface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)

        # 2. Reapply NetworkManager device settings without link teardown
        if subprocess.run(["which", "nmcli"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            res = subprocess.run(["nmcli", "dev", "reapply", interface], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
            if res.returncode == 0:
                return True, f"Interface {interface} link refreshed (non-destructive ARP & DHCP sync)."

        # 3. Fallback: gentle arp probe
        return True, f"Flushed neighbor cache on interface {interface}."
    except Exception as e:
        return False, f"Link refresh error: {e}"


def get_service_status() -> Dict[str, Any]:
    """Check systemd user service status."""
    status = {"active": False, "enabled": False, "status_text": "Stopped", "pid": None}
    try:
        # Check active status
        res = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2
        )
        is_active = res.stdout.strip() == "active"
        status["active"] = is_active
        status["status_text"] = "Active (Running)" if is_active else "Inactive (Stopped)"

        # Check enabled status
        res_en = subprocess.run(
            ["systemctl", "--user", "is-enabled", SERVICE_NAME],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2
        )
        status["enabled"] = (res_en.stdout.strip() == "enabled")

        # Get PID if active
        if is_active:
            res_show = subprocess.run(
                ["systemctl", "--user", "show", "--property=MainPID", SERVICE_NAME],
                stdout=subprocess.PIPE, text=True, timeout=2
            )
            pid_m = re.search(r"MainPID=(\d+)", res_show.stdout)
            if pid_m and pid_m.group(1) != "0":
                status["pid"] = pid_m.group(1)
    except Exception as e:
        status["status_text"] = f"Error: {e}"
    return status


def control_service(action: str) -> Tuple[bool, str]:
    """Control service: 'start', 'stop', 'restart', 'enable', 'disable'."""
    allowed = ["start", "stop", "restart", "enable", "disable"]
    if action not in allowed:
        return False, f"Unknown action: {action}"
    try:
        res = subprocess.run(
            ["systemctl", "--user", action, SERVICE_NAME],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        if res.returncode == 0:
            return True, f"Service {action}ed successfully."
        return False, f"Error: {res.stderr.strip() or res.stdout.strip()}"
    except Exception as e:
        return False, f"Exception: {e}"


def get_magic_token(probe_url: str) -> Optional[str]:
    """
    Attempt to obtain captive portal challenge token from probe URL and common fallbacks.
    Supports case-insensitive 16 to 64 character hex tokens and HTML form fallback.
    """
    targets = [
        probe_url,
        "http://connectivity-check.ubuntu.com/",
        "http://detectportal.firefox.com/success.txt",
        "http://neverssl.com/",
        "http://1.1.1.1/"
    ]
    seen = set()
    for target in targets:
        if not target or target in seen:
            continue
        seen.add(target)
        try:
            cmd = ["curl", "-4", "-k", "-s", "-i", "--connect-timeout", "4", target]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5)
            # Match 16 to 64 hex token case-insensitive
            match = re.search(r"fgtauth\?([a-zA-Z0-9]{16,64})", res.stdout, re.IGNORECASE)
            if match:
                return match.group(1)
            # Form value match fallback
            match_form = re.search(r'name=["\']magic["\']\s+value=["\']([a-zA-Z0-9]{16,64})["\']', res.stdout, re.IGNORECASE)
            if match_form:
                return match_form.group(1)
        except Exception:
            continue
    return None


def perform_login(auto_bounce: bool = True) -> Tuple[bool, str]:
    """
    Perform captive portal login sequence securely without exposing credentials in process lists.
    If the challenge token is not detected initially while offline,
    automatically refreshes the interface link to prompt the FortiGate gateway.
    Returns (success, message).
    """
    cfg = load_config()
    username = cfg.get("USERNAME", "").strip()
    password = cfg.get("PASSWORD", "")
    probe_url = cfg.get("PROBE_URL", "http://connectivity-check.ubuntu.com/")
    gateway = cfg.get("GATEWAY", "https://gateway.iiserb.ac.in:1003")
    cookie_jar = cfg.get("COOKIE_JAR", os.path.join(USER_RUNTIME_DIR, "fgt_cookies.txt"))

    if not username or not password:
        return False, "LDAP username and password are required. Configure them in Settings or CLI."

    _ensure_secure_dirs()

    # 1. Clean cookie jar safely
    if os.path.exists(cookie_jar):
        try:
            os.remove(cookie_jar)
        except Exception:
            pass

    # 2. Extract magic token with IPv4 probe
    try:
        magic = get_magic_token(probe_url)

        # If magic token not found and offline, refresh network link once
        if not magic and auto_bounce:
            is_on, lat = check_internet(cfg.get("PING_TARGET", "1.1.1.1"))
            if is_on:
                return True, f"Already online ({lat:.1f}ms latency). No login needed."

            bounce_interface()
            time.sleep(2)
            magic = get_magic_token(probe_url)

        if not magic:
            is_on, lat = check_internet(cfg.get("PING_TARGET", "1.1.1.1"))
            if is_on:
                return True, f"Already online ({lat:.1f}ms latency). No captive portal challenge found."
            return False, "Could not obtain captive portal magic token. Gateway may be unreachable."

        # 3. Step 1: Hit fgtauth tracking link and save session cookie
        init_cmd = ["curl", "-4", "-k", "-s", "-c", cookie_jar, "--connect-timeout", "8", f"{gateway}/fgtauth?{magic}"]
        subprocess.run(init_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)

        # 4. Step 2: POST credentials via STDIN to prevent password leakage in /proc/<pid>/cmdline
        post_data = urllib.parse.urlencode({
            "4Tredir": probe_url,
            "magic": magic,
            "username": username,
            "password": password
        })

        post_cmd = [
            "curl", "-4", "-k", "-s", "-L", "--connect-timeout", "10", "-X", "POST", f"{gateway}/",
            "-b", cookie_jar, "-c", cookie_jar,
            "-H", f"Origin: {gateway}",
            "-H", f"Referer: {gateway}/fgtauth?{magic}",
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "--data-binary", "@-"
        ]

        post_res = subprocess.run(
            post_cmd, input=post_data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12
        )

        # Extract keepalive token if present
        keepalive_match = re.search(r"keepalive\?([a-zA-Z0-9]{16,64})", post_res.stdout, re.IGNORECASE)
        keepalive_token = keepalive_match.group(1) if keepalive_match else None

        time.sleep(2)

        # 5. Verify internet connectivity
        online, latency = check_internet(cfg.get("PING_TARGET", "1.1.1.1"))
        if online:
            msg = f"Login successful for {username}! Connection verified ({latency:.1f}ms latency)."
            if keepalive_token:
                msg += f" Keepalive token: {keepalive_token[:8]}..."
            send_notification("IISERB Login: Connected", f"Authenticated as {username} ({latency:.1f} ms)")
            return True, msg
        else:
            send_notification("IISERB Login: Authentication Failed", "Gateway did not grant internet access. Check credentials.", urgency="critical")
            return False, "Login POST submitted, but internet verification failed. Please verify credentials."
    except Exception as e:
        return False, f"Login error: {e}"


def perform_logout() -> Tuple[bool, str]:
    """Perform captive portal logout."""
    cfg = load_config()
    gateway = cfg.get("GATEWAY", "https://gateway.iiserb.ac.in:1003")
    cookie_jar = cfg.get("COOKIE_JAR", os.path.join(USER_RUNTIME_DIR, "fgt_cookies.txt"))
    try:
        cmd = ["curl", "-k", "-s", "--connect-timeout", "5", "-b", cookie_jar, f"{gateway}/logout"]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=6)
        send_notification("IISERB Login: Logged Out", "Session terminated with gateway.")
        return True, "Logout request sent to gateway."
    except Exception as e:
        return False, f"Logout error: {e}"


def read_logs(max_lines: int = 150) -> str:
    """Read recent lines from the secure log file."""
    cfg = load_config()
    log_file = cfg.get("LOG_FILE", os.path.join(STATE_DIR, "autologin.log"))
    if not os.path.exists(log_file):
        return "(No log file exists yet. Logs will appear here once the service or login runs.)"
    try:
        res = subprocess.run(["tail", "-n", str(max_lines), log_file], stdout=subprocess.PIPE, text=True, timeout=2)
        return res.stdout if res.stdout else "(Log file is empty)"
    except Exception as e:
        return f"Error reading log file: {e}"


def clear_logs() -> bool:
    """Clear log file."""
    cfg = load_config()
    log_file = cfg.get("LOG_FILE", os.path.join(STATE_DIR, "autologin.log"))
    try:
        os.makedirs(os.path.dirname(log_file), mode=0o700, exist_ok=True)
        with open(log_file, "w") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Log file cleared by user.\n")
        os.chmod(log_file, 0o600)
        return True
    except Exception:
        return False
