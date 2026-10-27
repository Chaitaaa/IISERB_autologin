# IISER Bhopal Captive Portal Auto-login & Manager

A modern desktop application and CLI tool for Linux to automatically log into the IISER Bhopal FortiGate network captive portal and keep your connection alive without annoying session drops.

Supports **Fedora**, **Ubuntu**, **Debian**, **Arch Linux**, **Linux Mint**, **Pop!_OS**, and any systemd-based Linux distribution.

---

## 🚀 Quick Install (1 Step)

Open a terminal inside this folder and run:
```bash
bash install.sh
```

The installer will:
1. Detect your distribution's package manager (`dnf5`, `dnf`, `apt`, `pacman`).
2. Ensure Python 3, Tkinter (`python3-tkinter` / `python3-tk`), and `customtkinter` are installed.
3. Install the application files into `~/.local/share/iiserb-login-app/`.
4. Create the global `iiserb-login-app` command in `~/.local/bin/`.
5. Set up a systemd background user service to auto-login and keep your connection alive.
6. Add shortcuts to your **Desktop** and **Application Menu**.

---

## ⌨️ Command-Line Interface (CLI Usage)

You can run everything directly from the terminal without opening the GUI — great for SSH sessions, terminal users, and scripts!

| Command | Description |
|---|---|
| `iiserb-login-app login` | Immediately authenticate with the captive portal |
| `iiserb-login-app status` | Check connection, ping latency, IP, and daemon status |
| `iiserb-login-app reconnect` | Reset/bounce network interface link (via `nmcli`) |
| `iiserb-login-app logout` | Log out from FortiGate gateway |
| `iiserb-login-app service restart` | Restart the background keepalive daemon |
| `iiserb-login-app service [start\|stop\|status]` | Manage the background service |
| `iiserb-login-app logs` | View recent background daemon logs |
| `iiserb-login-app logs -f` | Follow live daemon logs in real time (`tail -f`) |
| `iiserb-login-app diag` | Run network & gateway diagnostic test suite |
| `iiserb-login-app config -u <user> -p <pass>` | Set LDAP credentials from terminal |
| `iiserb-login-app config` | View current configuration |
| `iiserb-login-app --help` | Show full CLI help message |
| `iiserb-login-app` | Launch desktop graphical interface (GUI) |

---

## 🖥️ Graphical Interface (GUI Usage)

1. Launch **IISERB Login** from your Desktop, Applications menu, or run `iiserb-login-app` in the terminal.
2. Go to the **⚙️ Settings** tab.
3. Enter your LDAP **Username** and **Password**.
4. Click **💾 Save Settings & Apply**.
5. The background daemon will automatically detect network disconnections, re-authenticate immediately, and maintain keepalive pulses so you never get logged out.

---

## 🎩 Fedora Compatibility Notes

On Fedora:
- Works with both `dnf` and modern `dnf5` (Fedora 41+).
- Automatically installs `python3-tkinter` and `python3-pip`.
- Works on both Wayland and X11 sessions.
- Automatically handles PEP 668 environments for Python pip packages.

---

## ✨ Features

- **CLI & GUI Dual Support**: Run headlessly over SSH or with a modern graphical interface.
- **Automatic Auto-login**: Logs in within seconds whenever the network drops.
- **Firewall Keepalive Pulse**: Sends periodic FortiGate keepalive pulses to avoid idle timeout.
- **Auto Link Reset**: Automatically bounces the interface link if the gateway blackholes packets.
- **Modern Desktop App**: Built with CustomTkinter (supports Dark/Light mode).
- **Service Controls**: Start, Stop, or Restart the background daemon directly from CLI or UI.
- **Real-time Status**: Live latency meter, local IP, interface name, and connectivity indicator.
- **Live Logs**: Watch the keepalive background service activity in real time.
- **Diagnostics**: Built-in test suite for DNS, Gateway ping, and HTTP captive portal probes.

---

## 🗑️ Uninstallation

If you ever want to remove it, simply run:
```bash
bash uninstall.sh
```
