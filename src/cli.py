#!/usr/bin/env python3
"""
CLI Handler for IISER Bhopal Captive Portal Manager.
Allows full terminal automation, headless execution, status bar integration (Polybar/Waybar),
and secure credential management.
"""

import sys
import os
import argparse
import subprocess
import time
import json
import getpass
from typing import List, Dict, Any

# Ensure backend can be imported
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import backend

# POSIX Standardized Exit Codes
EXIT_SUCCESS = 0
EXIT_CAPTIVE = 2          # Captive portal challenge detected (offline)
EXIT_CONFIG_MISSING = 3   # Credentials or configuration missing
EXIT_NET_DOWN = 4         # Network interface or route unreachable
EXIT_AUTH_FAILED = 5      # Gateway rejected credentials
EXIT_TIMEOUT = 6          # Gateway or probe timeout

# ANSI Colors
CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"

# Disable colors if stdout is not a TTY or NO_COLOR is set
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    CYAN = GREEN = RED = YELLOW = BOLD = DIM = NC = ""


def cmd_login(args) -> int:
    """Trigger captive portal login immediately."""
    cfg = backend.load_config()
    username = cfg.get("USERNAME", "").strip()
    password = cfg.get("PASSWORD", "").strip()

    if not username or not password:
        if getattr(args, "json", False):
            print(json.dumps({"success": False, "code": EXIT_CONFIG_MISSING, "error": "Username or password not configured"}))
        elif not getattr(args, "quiet", False):
            print(f"{RED}❌ Credentials not configured.{NC}")
            print("Run: iiserb-login-app config -u <ldap_username> (you will be prompted securely for password)")
        return EXIT_CONFIG_MISSING

    if not getattr(args, "quiet", False) and not getattr(args, "json", False):
        print(f"{CYAN}🌐 Attempting captive portal login for {BOLD}{username}{NC}...")

    ok, msg = backend.perform_login(auto_bounce=True)

    if getattr(args, "json", False):
        print(json.dumps({"success": ok, "message": msg, "username": username}))
    elif not getattr(args, "quiet", False):
        if ok:
            print(f"{GREEN}✔ {msg}{NC}")
        else:
            print(f"{RED}❌ {msg}{NC}")

    if ok:
        return EXIT_SUCCESS
    return EXIT_AUTH_FAILED if "verification failed" in msg.lower() else EXIT_TIMEOUT


def cmd_logout(args) -> int:
    """Send logout request to FortiGate gateway."""
    if not getattr(args, "quiet", False) and not getattr(args, "json", False):
        print(f"{CYAN}🚪 Sending logout request to gateway...{NC}")
    ok, msg = backend.perform_logout()
    if getattr(args, "json", False):
        print(json.dumps({"success": ok, "message": msg}))
    elif not getattr(args, "quiet", False):
        if ok:
            print(f"{GREEN}✔ {msg}{NC}")
        else:
            print(f"{RED}❌ {msg}{NC}")
    return EXIT_SUCCESS if ok else EXIT_TIMEOUT


def cmd_status(args) -> int:
    """Check network connectivity, IP info, and background service status."""
    cfg = backend.load_config()
    target = cfg.get("PING_TARGET", "1.1.1.1")
    is_online, latency = backend.check_internet(target)
    net = backend.get_network_info()
    svc = backend.get_service_status()

    # JSON output for programmatic use / status bars
    if getattr(args, "json", False):
        out = {
            "online": is_online,
            "latency_ms": round(latency, 1) if is_online else None,
            "status": "online" if is_online else "offline",
            "interface": net.get("interface", "Unknown"),
            "ip": net.get("ip", "Unknown"),
            "gateway": net.get("gateway", "Unknown"),
            "service_active": svc.get("active", False),
            "service_enabled": svc.get("enabled", False),
            "service_pid": svc.get("pid"),
            "username": cfg.get("USERNAME", "")
        }
        print(json.dumps(out))
        return EXIT_SUCCESS if is_online else EXIT_CAPTIVE

    # Short output (single line, ideal for Polybar/Waybar/tmux)
    if getattr(args, "short", False):
        if is_online:
            print(f"ONLINE {latency:.1f}ms")
            return EXIT_SUCCESS
        else:
            print("OFFLINE (Captive)")
            return EXIT_CAPTIVE

    # Quiet mode (exit code only)
    if getattr(args, "quiet", False):
        return EXIT_SUCCESS if is_online else EXIT_CAPTIVE

    # Full terminal dashboard
    print(f"{BOLD}======================================================{NC}")
    print(f"{BOLD}   IISER Bhopal Captive Portal - Status               {NC}")
    print(f"{BOLD}======================================================{NC}")

    if is_online:
        print(f"  Internet Status:   {GREEN}🟢 ONLINE (Connected){NC}")
        print(f"  Ping Latency:      {GREEN}{latency:.1f} ms{NC} (target: {target})")
    else:
        print(f"  Internet Status:   {RED}🔴 OFFLINE (Captive Portal Challenge){NC}")
        print(f"  Ping Latency:      {RED}Interrupted / Captive Blocked{NC}")

    print(f"  Local IP Address:  {net.get('ip', 'Unknown')}")
    print(f"  Network Interface: {net.get('interface', 'Unknown')}")
    print(f"  Default Gateway:   {net.get('gateway', 'Unknown')}")

    # Service info
    if svc.get("active"):
        pid_txt = f" (PID {svc['pid']})" if svc.get("pid") else ""
        print(f"  Background Daemon: {GREEN}🟢 Active (Running){pid_txt}{NC}")
    else:
        print(f"  Background Daemon: {DIM}⚪ Inactive (Stopped){NC}")

    autostart_txt = f"{GREEN}Enabled{NC}" if svc.get("enabled") else f"{DIM}Disabled{NC}"
    print(f"  Autostart on Boot: {autostart_txt}")
    print(f"  Configured User:   {cfg.get('USERNAME', '(not set)')}")
    print(f"{BOLD}======================================================{NC}")

    return EXIT_SUCCESS if is_online else EXIT_CAPTIVE


def cmd_reconnect(args) -> int:
    """Non-destructive network link refresh."""
    net = backend.get_network_info()
    iface = net.get("interface", "Unknown")
    if not getattr(args, "quiet", False):
        print(f"{CYAN}🔄 Refreshing network link on interface ({iface})...{NC}")
    ok, msg = backend.bounce_interface(iface)

    if ok:
        if not getattr(args, "quiet", False):
            print(f"{GREEN}✔ {msg}{NC}")
        time.sleep(2)
        is_on, lat = backend.check_internet()
        if is_on:
            if not getattr(args, "quiet", False):
                print(f"{GREEN}✔ Internet is reachable ({lat:.1f} ms).{NC}")
            return EXIT_SUCCESS
        else:
            if not getattr(args, "quiet", False):
                print(f"{YELLOW}⚠️  Link refreshed. Run 'iiserb-login-app login' to authenticate.{NC}")
            return EXIT_CAPTIVE
    else:
        if not getattr(args, "quiet", False):
            print(f"{RED}❌ {msg}{NC}")
        return EXIT_NET_DOWN


def cmd_service(args) -> int:
    """Manage background keepalive service."""
    action = args.action.lower()
    if action == "status":
        svc = backend.get_service_status()
        status_color = GREEN if svc["active"] else RED
        print(f"Service status: {status_color}{svc['status_text']}{NC}")
        print(f"Autostart enabled: {'Yes' if svc['enabled'] else 'No'}")
        if svc.get("pid"):
            print(f"Main PID: {svc['pid']}")
        return EXIT_SUCCESS if svc["active"] else 1

    print(f"{CYAN}⚙️  Executing: systemctl --user {action} portal-autologin.service...{NC}")
    ok, msg = backend.control_service(action)
    if ok:
        print(f"{GREEN}✔ {msg}{NC}")
        return EXIT_SUCCESS
    else:
        print(f"{RED}❌ {msg}{NC}")
        return 1


def cmd_logs(args) -> int:
    """Display activity logs."""
    cfg = backend.load_config()
    log_file = cfg.get("LOG_FILE", os.path.join(backend.STATE_DIR, "autologin.log"))

    if args.follow:
        if not os.path.exists(log_file):
            print(f"{YELLOW}Log file {log_file} does not exist yet. Waiting...{NC}")
        print(f"{CYAN}Following {log_file} (Press Ctrl+C to exit)...{NC}")
        try:
            subprocess.run(["tail", "-f", "-n", str(args.lines), log_file])
        except KeyboardInterrupt:
            print("")
        return EXIT_SUCCESS
    else:
        logs = backend.read_logs(max_lines=args.lines)
        print(logs)
        return EXIT_SUCCESS


def cmd_diag(args) -> int:
    """Run diagnostic suite."""
    print(f"{BOLD}=== Starting Network Diagnostics ==={NC}\n")
    cfg = backend.load_config()
    target = cfg.get("PING_TARGET", "1.1.1.1")
    gateway = cfg.get("GATEWAY", "https://gateway.iiserb.ac.in:1003")
    probe = cfg.get("PROBE_URL", "http://connectivity-check.ubuntu.com/")

    # 1. Network Info
    net = backend.get_network_info()
    print(f"[1] Local Network:")
    print(f"    Interface: {net['interface']}")
    print(f"    IP:        {net['ip']}")
    print(f"    Gateway:   {net['gateway']}\n")

    # 2. DNS
    print(f"[2] DNS Resolution Test:")
    for host in ["gateway.iiserb.ac.in", "connectivity-check.ubuntu.com", "detectportal.firefox.com"]:
        try:
            ip = socket.gethostbyname(host)
            print(f"    {GREEN}✔{NC} {host} -> {ip}")
        except Exception as e:
            print(f"    {RED}❌{NC} {host} -> Resolution failed: {e}")
    print("")

    # 3. Ping
    print(f"[3] Ping Test ({target}):")
    try:
        res = subprocess.run(["ping", "-c", "2", "-W", "2", target], stdout=subprocess.PIPE, text=True, timeout=5)
        for line in res.stdout.strip().split("\n"):
            print(f"    {line}")
    except Exception as e:
        print(f"    {RED}❌ Ping failed: {e}{NC}")
    print("")

    # 4. Probe
    print(f"[4] Captive Portal HTTP Probe ({probe}):")
    try:
        res = subprocess.run(["curl", "-4", "-k", "-s", "-i", "--connect-timeout", "4", probe], stdout=subprocess.PIPE, text=True, timeout=6)
        headers = [line for line in res.stdout.split("\r\n") if line.strip()][:5]
        for h in headers:
            print(f"    {h}")
    except Exception as e:
        print(f"    {RED}❌ Probe failed: {e}{NC}")
    print("")

    # 5. Gateway
    print(f"[5] Gateway SSL Reachability ({gateway}):")
    try:
        res = subprocess.run(["curl", "-4", "-k", "-s", "-i", "--connect-timeout", "4", f"{gateway}/"], stdout=subprocess.PIPE, text=True, timeout=6)
        first_lines = res.stdout.strip().split("\n")[:4]
        if first_lines and first_lines[0]:
            for l in first_lines:
                print(f"    {l}")
        else:
            print(f"    {GREEN}✔ Gateway connected (HTTP closed cleanly){NC}")
    except Exception as e:
        print(f"    {RED}❌ Gateway connection: {e}{NC}")

    print(f"\n{BOLD}=== Diagnostics Complete ==={NC}")
    return EXIT_SUCCESS


def cmd_config(args) -> int:
    """View or update configuration safely."""
    cfg = backend.load_config()
    updated = False

    if args.username:
        cfg["USERNAME"] = args.username.strip()
        updated = True

    # Password handling: from stdin, CLI arg, or secure interactive prompt
    if args.password_stdin:
        pw = sys.stdin.read().strip()
        if pw:
            cfg["PASSWORD"] = pw
            updated = True
    elif args.password is not None:
        if args.password == "":
            cfg["PASSWORD"] = getpass.getpass("Enter IISERB LDAP Password: ")
        else:
            cfg["PASSWORD"] = args.password
        updated = True
    elif args.username and not cfg.get("PASSWORD"):
        # Prompt if username given but no password exists
        try:
            cfg["PASSWORD"] = getpass.getpass(f"Enter IISERB LDAP Password for '{cfg['USERNAME']}': ")
            updated = True
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 1

    if args.gateway:
        cfg["GATEWAY"] = args.gateway.strip()
        updated = True
    if args.probe:
        cfg["PROBE_URL"] = args.probe.strip()
        updated = True
    if args.ping_target:
        cfg["PING_TARGET"] = args.ping_target.strip()
        updated = True
    if args.check_interval:
        cfg["CHECK_INTERVAL"] = int(args.check_interval)
        updated = True
    if args.keepalive_interval:
        cfg["KEEPALIVE_INTERVAL"] = int(args.keepalive_interval)
        updated = True

    if updated:
        ok, msg = backend.save_config(cfg)
        if ok:
            print(f"{GREEN}✔ Configuration saved securely (mode 0600) to {backend.CONFIG_PATH}{NC}")
            svc = backend.get_service_status()
            if svc["active"]:
                backend.control_service("restart")
                print(f"{GREEN}✔ Background keepalive service restarted with updated settings.{NC}")
            return EXIT_SUCCESS
        else:
            print(f"{RED}❌ {msg}{NC}")
            return 1

    # Otherwise show current config with password hidden
    print(f"{BOLD}Current Configuration ({backend.CONFIG_PATH}):{NC}")
    for k in ["USERNAME", "PING_TARGET", "CHECK_INTERVAL", "KEEPALIVE_INTERVAL", "GATEWAY", "PROBE_URL", "COOKIE_JAR", "LOG_FILE"]:
        v = cfg.get(k, "")
        print(f"  {k:22}: {v}")
    has_pass = "Set (hidden)" if cfg.get("PASSWORD") else "Not set"
    print(f"  {'PASSWORD':22}: {has_pass}")
    return EXIT_SUCCESS


def handle_cli(args_list: List[str]) -> int:
    """Parse and execute CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="iiserb-login-app",
        description="IISER Bhopal Captive Portal Auto-login & Manager (CLI & GUI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  iiserb-login-app login                # Immediately authenticate captive portal
  iiserb-login-app status               # Show connection & service status
  iiserb-login-app status --json        # Machine-readable JSON output (Waybar/Polybar)
  iiserb-login-app status --short       # Concise single-line status
  iiserb-login-app reconnect            # Non-destructive network link refresh
  iiserb-login-app logout               # Log out from gateway
  iiserb-login-app logs -f              # Follow live daemon logs
  iiserb-login-app service restart      # Restart background keepalive service
  iiserb-login-app config -u john       # Set LDAP username (prompts securely for password)
  iiserb-login-app                      # Launch desktop graphical interface
        """
    )

    # Global options
    parser.add_argument("--gui", "-g", action="store_true", help="Launch Graphical User Interface")
    parser.add_argument("-j", "--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode (exit code only)")
    parser.add_argument("--short", action="store_true", help="Single-line concise status")

    parser.add_argument("-l", "--login", dest="flag_login", action="store_true", help="Alias for 'login' command")
    parser.add_argument("-s", "--status", dest="flag_status", action="store_true", help="Alias for 'status' command")
    parser.add_argument("-r", "--reconnect", dest="flag_reconnect", action="store_true", help="Alias for 'reconnect' command")
    parser.add_argument("--logout", dest="flag_logout", action="store_true", help="Alias for 'logout' command")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: login
    p_login = subparsers.add_parser("login", help="Authenticate with captive portal")
    p_login.add_argument("-j", "--json", action="store_true", help="JSON output")
    p_login.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")
    p_login.set_defaults(func=cmd_login)

    # Command: logout
    p_logout = subparsers.add_parser("logout", help="Log out from gateway")
    p_logout.add_argument("-j", "--json", action="store_true", help="JSON output")
    p_logout.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")
    p_logout.set_defaults(func=cmd_logout)

    # Command: status
    p_status = subparsers.add_parser("status", help="Show connection and service status")
    p_status.add_argument("-j", "--json", action="store_true", help="Output in JSON format")
    p_status.add_argument("-q", "--quiet", action="store_true", help="Quiet mode (exit code only)")
    p_status.add_argument("--short", action="store_true", help="Single line concise output")
    p_status.set_defaults(func=cmd_status)

    # Command: reconnect / bounce
    p_reconn = subparsers.add_parser("reconnect", aliases=["bounce"], help="Refresh network link (non-destructive ARP sync)")
    p_reconn.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")
    p_reconn.set_defaults(func=cmd_reconnect)

    # Command: service
    p_svc = subparsers.add_parser("service", help="Manage background service")
    p_svc.add_argument("action", choices=["start", "stop", "restart", "status", "enable", "disable"],
                       help="Action to perform on portal-autologin.service")
    p_svc.set_defaults(func=cmd_service)

    # Command: logs
    p_logs = subparsers.add_parser("logs", help="View daemon logs")
    p_logs.add_argument("-n", "--lines", type=int, default=30, help="Number of lines to show (default: 30)")
    p_logs.add_argument("-f", "--follow", action="store_true", help="Follow log output in real time")
    p_logs.set_defaults(func=cmd_logs)

    # Command: diag
    p_diag = subparsers.add_parser("diag", help="Run network diagnostics")
    p_diag.set_defaults(func=cmd_diag)

    # Command: config
    p_cfg = subparsers.add_parser("config", help="View or update credentials and settings")
    p_cfg.add_argument("-u", "--username", help="LDAP Username")
    p_cfg.add_argument("-p", "--password", nargs="?", const="", help="LDAP Password (prompts interactively if empty)")
    p_cfg.add_argument("--password-stdin", action="store_true", help="Read password from standard input")
    p_cfg.add_argument("--gateway", help="Gateway URL")
    p_cfg.add_argument("--probe", help="Probe URL")
    p_cfg.add_argument("--ping-target", help="Ping target IP")
    p_cfg.add_argument("--check-interval", help="Check interval in seconds")
    p_cfg.add_argument("--keepalive-interval", help="Keepalive interval in minutes")
    p_cfg.set_defaults(func=cmd_config)

    args = parser.parse_args(args_list)

    # Propagate global flags to subcommands
    if args.json:
        setattr(args, "json", True)
    if args.quiet:
        setattr(args, "quiet", True)
    if args.short:
        setattr(args, "short", True)

    # Handle flag aliases
    if args.flag_login:
        return cmd_login(args)
    if args.flag_logout:
        return cmd_logout(args)
    if args.flag_status:
        return cmd_status(args)
    if args.flag_reconnect:
        return cmd_reconnect(args)

    if hasattr(args, "func"):
        return args.func(args)

    parser.print_help()
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(handle_cli(sys.argv[1:]))

