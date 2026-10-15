#!/usr/bin/env python3
"""
Backend module for IISER Bhopal Captive Portal Manager.
Handles network status checks, authentication, systemd service management,
and configuration persistence.
"""

import os
import json
import subprocess
import socket
import re
import time
from typing import Dict, Any, Tuple, Optional

DEFAULT_CONFIG: Dict[str, Any] = {
    "USERNAME": "",
    "PASSWORD": "",
    "PROBE_URL": "http://connectivity-check.ubuntu.com/",
    "GATEWAY": "https://gateway.iiserb.ac.in:1003",
    "PING_TARGET": "1.1.1.1",
    "CHECK_INTERVAL": 60,
    "KEEPALIVE_INTERVAL": 10,
    "COOKIE_JAR": "/tmp/fgt_cookies.txt",
    "LOG_FILE": "/tmp/iiserb_autologin.log"
}

CONFIG_DIR = os.path.expanduser("~/.config/iiserb_login")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
SERVICE_NAME = "portal-autologin.service"


def load_config() -> Dict[str, Any]:
    """Load configuration from ~/.config/iiserb_login/config.json or defaults."""
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    cfg.update(saved)
        except Exception as e:
            print(f"Error loading config: {e}")
    return cfg


def save_config(new_config: Dict[str, Any]) -> Tuple[bool, str]:
    """Save configuration to ~/.config/iiserb_login/config.json."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        cfg = load_config()
        cfg.update(new_config)
        cfg["CHECK_INTERVAL"] = int(cfg.get("CHECK_INTERVAL", 60))
        cfg["KEEPALIVE_INTERVAL"] = int(cfg.get("KEEPALIVE_INTERVAL", 10))
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True, "Settings saved successfully."
    except Exception as e:
        return False, f"Failed to save settings: {e}"


def check_internet(target: Optional[str] = None) -> Tuple[bool, float]:
    """
    Check if internet is reachable by pinging target.
    Returns (is_online, latency_ms).
    """
    if not target:
        target = load_config().get("PING_TARGET", "1.1.1.1")
    try:
        cmd = ["ping", "-c", "1", "-W", "2", str(target)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        if res.returncode == 0:
            match = re.search(r"time=([\d\.]+)\s*ms", res.stdout)
            latency = float(match.group(1)) if match else 0.0
            return True, latency
        return False, 0.0
    except Exception:
        return False, 0.0


def get_network_info() -> Dict[str, str]:
    """Retrieve primary IP address and default interface."""
    info = {"ip": "Unknown", "interface": "Unknown", "gateway": "Unknown"}
    try:
        res = subprocess.run(["ip", "route", "show", "default"], stdout=subprocess.PIPE, text=True, timeout=2)
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
    return info


def get_service_status() -> Dict[str, Any]:
    """Check systemd user service status."""
    status = {"active": False, "enabled": False, "status_text": "Stopped", "pid": None}
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2
        )
        is_active = res.stdout.strip() == "active"
        status["active"] = is_active
        status["status_text"] = "Active (Running)" if is_active else "Inactive (Stopped)"

        res_en = subprocess.run(
            ["systemctl", "--user", "is-enabled", SERVICE_NAME],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2
        )
        status["enabled"] = (res_en.stdout.strip() == "enabled")

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


def perform_login() -> Tuple[bool, str]:
    """
    Perform manual captive portal login sequence.
    Returns (success, message).
    """
    cfg = load_config()
    username = cfg.get("USERNAME", "").strip()
    password = cfg.get("PASSWORD", "")
    probe_url = cfg["PROBE_URL"]
    gateway = cfg["GATEWAY"]
    cookie_jar = cfg["COOKIE_JAR"]

    if not username or not password:
        return False, "Please enter your LDAP Username and Password in Settings first."

    if os.path.exists(cookie_jar):
        try:
            os.remove(cookie_jar)
        except Exception:
            pass

    try:
        probe_cmd = ["curl", "-k", "-s", "-i", "--connect-timeout", "8", probe_url]
        res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        output = res.stdout

        magic_match = re.search(r"fgtauth\?([a-f0-9]{16,32})", output)
        if not magic_match:
            is_on, lat = check_internet(cfg.get("PING_TARGET", "1.1.1.1"))
            if is_on:
                return True, f"Already online ({lat:.1f}ms latency). No captive portal challenge found."
            return False, "Could not find captive portal magic token. Network might be down or unreachable."

        magic = magic_match.group(1)

        init_cmd = ["curl", "-k", "-s", "-c", cookie_jar, "--connect-timeout", "8", f"{gateway}/fgtauth?{magic}"]
        subprocess.run(init_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

        post_cmd = [
            "curl", "-k", "-s", "-L", "--connect-timeout", "10", "-X", "POST", f"{gateway}/",
            "-b", cookie_jar, "-c", cookie_jar,
            "-H", f"Origin: {gateway}",
            "-H", f"Referer: {gateway}/fgtauth?{magic}",
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "--data-urlencode", f"4Tredir={probe_url}",
            "--data-urlencode", f"magic={magic}",
            "--data-urlencode", f"username={username}",
            "--data-urlencode", f"password={password}"
        ]
        post_res = subprocess.run(post_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)

        keepalive_match = re.search(r"keepalive\?([a-f0-9]{16,32})", post_res.stdout)
        keepalive_token = keepalive_match.group(1) if keepalive_match else None

        time.sleep(3)

        online, latency = check_internet(cfg.get("PING_TARGET", "1.1.1.1"))
        if online:
            msg = f"Login successful for {username}! Connection verified ({latency:.1f}ms latency)."
            if keepalive_token:
                msg += f" Keepalive token active."
            return True, msg
        else:
            return False, "Login submitted, but verification failed. Please double check credentials."
    except Exception as e:
        return False, f"Login error: {e}"


def perform_logout() -> Tuple[bool, str]:
    """Perform captive portal logout."""
    cfg = load_config()
    gateway = cfg["GATEWAY"]
    cookie_jar = cfg["COOKIE_JAR"]
    try:
        cmd = ["curl", "-k", "-s", "--connect-timeout", "5", "-b", cookie_jar, f"{gateway}/logout"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=6)
        return True, "Logout request sent to gateway."
    except Exception as e:
        return False, f"Logout error: {e}"


def read_logs(max_lines: int = 150) -> str:
    """Read recent lines from the log file."""
    cfg = load_config()
    log_file = cfg.get("LOG_FILE", "/tmp/iiserb_autologin.log")
    if not os.path.exists(log_file):
        return "(No logs yet. Logs will appear here once the service or login runs.)"
    try:
        res = subprocess.run(["tail", "-n", str(max_lines), log_file], stdout=subprocess.PIPE, text=True, timeout=2)
        return res.stdout if res.stdout else "(Log file is empty)"
    except Exception as e:
        return f"Error reading log file: {e}"


def clear_logs() -> bool:
    """Clear log file."""
    cfg = load_config()
    log_file = cfg.get("LOG_FILE", "/tmp/iiserb_autologin.log")
    try:
        with open(log_file, "w") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Log file cleared.\n")
        return True
    except Exception:
        return False
