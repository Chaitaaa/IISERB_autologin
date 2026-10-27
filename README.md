# IISER Bhopal Captive Portal Auto-login & Manager

A modern, robust Linux desktop application and CLI automation tool to automatically authenticate into the IISER Bhopal FortiGate captive portal and maintain keepalive pulses without session interruptions.

Fully compatible with **Ubuntu**, **Fedora** (dnf/dnf5), **Debian**, **Arch Linux**, **openSUSE**, and any modern Linux distribution.

---

## 🚀 Quick Install (1 Step)

Open a terminal inside this directory and run:
```bash
bash install.sh
```

### What the installer does:
1. Detects distribution package manager (`apt`, `dnf`, `dnf5`, `pacman`, `zypper`).
2. Creates an isolated application virtual environment in `~/.local/share/iiserb-login-app/venv` (**100% PEP 668 compliant**).
3. Installs dependencies (`customtkinter`, `pillow`, `pystray`) inside the isolated venv without modifying your system Python.
4. Enforces strict file permissions (`0700` directories, `0600` config and scripts) to protect your LDAP password from other users.
5. Installs global `iiserb-login-app` command in `~/.local/bin/`.
6. Installs shell tab completions for **Bash**, **Zsh**, and **Fish**.
7. Configures a user systemd keepalive service (`portal-autologin.service`).
8. Generates desktop application shortcuts for your Application Launcher and Desktop.

---

## ⌨️ Command-Line Interface (CLI Usage)

The CLI works seamlessly on headless servers, over SSH, and inside tmux without requiring an X11/Wayland display.

| Command | Description |
|---|---|
| `iiserb-login-app login` | Immediately authenticate with FortiGate captive portal |
| `iiserb-login-app status` | Full terminal status dashboard (latency, IP, service state) |
| `iiserb-login-app status --json` | Machine-readable JSON output (Waybar / Polybar / scripts) |
| `iiserb-login-app status --short` | Single-line status (e.g. `ONLINE 18.2ms` or `OFFLINE`) |
| `iiserb-login-app status --quiet` | Exit code only (`0` = Online, `2` = Captive Offline) |
| `iiserb-login-app reconnect` | Non-destructive network link refresh (ARP flush + nmcli reapply) |
| `iiserb-login-app logout` | Log out active session from gateway |
| `iiserb-login-app service restart` | Restart background keepalive daemon |
| `iiserb-login-app service [start\|stop\|status]` | Manage systemd service |
| `iiserb-login-app logs` | View recent background daemon logs |
| `iiserb-login-app logs -f` | Follow live daemon logs in real time (`tail -f`) |
| `iiserb-login-app diag` | Run network, DNS, ping, and gateway diagnostic suite |
| `iiserb-login-app config -u <user>` | Set LDAP username (prompts securely for password via `getpass`) |
| `iiserb-login-app config --password-stdin` | Pipe password from stdin (safe for scripts and password managers) |
| `iiserb-login-app config` | View current configuration (passwords are masked) |
| `iiserb-login-app --help` | Show full CLI manual |
| `iiserb-login-app` | Launch desktop graphical interface (GUI) |

### POSIX Exit Codes
- `0`: Success / Online
- `2`: Captive portal intercepted (offline)
- `3`: Configuration / credentials missing
- `4`: Network interface or route unreachable
- `5`: Gateway rejected credentials
- `6`: Gateway timeout or probe unreachable

### Waybar / Polybar Integration
For status bars, use `iiserb-login-app status --json`:
```json
{
  "online": true,
  "latency_ms": 17.6,
  "status": "online",
  "interface": "enp4s0",
  "ip": "172.28.151.152",
  "service_active": true
}
```

---

## 🖥️ Graphical Interface (GUI Usage)

1. Launch **IISERB Login** from your Desktop, Applications menu, or by running `iiserb-login-app`.
2. First-time users are greeted with a welcome banner directing them to **⚙️ Settings**.
3. Enter your LDAP **Username** and **Password** (press `Enter` or click `Save Settings & Apply`).
4. **System Tray Integration**: Closing the window minimizes the app to the system tray (`pystray`), keeping the daemon active in the background.
5. **Desktop Notifications**: Native desktop notifications appear on login success, session expiration, or network drops.
6. **Responsive Layout**: Adapts gracefully to all screen resolutions down to 1366×768 laptops.

### Keyboard Shortcuts
- `Ctrl + R` or `F5`: Refresh network status
- `Ctrl + L`: Force login attempt
- `Enter` (in password field): Save credentials & apply

---

## 🔒 Security & Privacy Architecture

- **Strict File Permissions**: Credentials in `~/.config/iiserb_login/config.json` are enforced with mode `0600` (`-rw-------`). Directories are restricted to mode `0700`.
- **Sandboxed Runtime Paths**: Cookies and runtime state are written to `$XDG_RUNTIME_DIR/iiserb_login/` (user-owned RAM tmpfs) instead of world-readable `/tmp`.
- **Process List Protection**: Passwords are supplied to `curl` via standard input (`--data-binary @-`) so they never appear in `/proc/<pid>/cmdline` or `ps aux`.

---

## 🌐 Network Protocol Resilience

- **Two-Tier Health Check**: Combines ICMP ping with HTTP 204 status probes (`http://connectivity-check.ubuntu.com/`). This avoids the "ICMP leak" bug where firewalls permit ping while blocking web traffic.
- **Non-Destructive Link Refresh**: Replaces destructive interface teardowns with ARP neighbor cache flushing (`ip neigh flush`) and gentle NetworkManager reapplies (`nmcli dev reapply`), preserving active SSH, VPN, and Tailscale connections.
- **Dynamic Interface Detection**: Dynamically queries the active default gateway adapter without hardcoded device names.
- **Keepalive Interval**: Defaults to a 3-minute heartbeat pulse to prevent FortiGate's 5-minute idle timeout.

---

## 🗑️ Uninstallation

To remove the application, run:
```bash
bash uninstall.sh
```
