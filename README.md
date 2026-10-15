# IISER Bhopal Captive Portal Auto-login & Manager

A modern desktop application and background service for Linux to automatically log into the IISER Bhopal FortiGate network captive portal and keep your connection alive without annoying session drops.

---

## 🚀 Quick Install (1 Step)

Open a terminal inside this folder and run:
```bash
bash install.sh
```

The installer will:
1. Ensure Python 3, Tkinter, and `customtkinter` are installed.
2. Install the application files into `~/.local/share/iiserb-login-app/`.
3. Set up a systemd background user service to auto-login and keep your connection alive.
4. Add shortcuts to your **Desktop** and **Application Menu**.

---

## 💻 How to Use

1. Launch **IISERB Login** from your Desktop or Applications menu (or type `iiserb-login-app` in the terminal).
2. Go to the **⚙️ Settings** tab.
3. Enter your LDAP **Username** and **Password**.
4. Click **💾 Save Settings & Apply**.
5. That's it! The background service will automatically detect network disconnections, log you in immediately, and maintain regular keepalive pulses so you never get logged out.

---

## ✨ Features

- **Automatic Auto-login**: Logs in within seconds whenever the network disconnects.
- **Firewall Keepalive Pulse**: Sends periodic FortiGate keepalive pulses to avoid idle timeout.
- **Modern Desktop App**: Built with CustomTkinter (supports Dark/Light mode).
- **Service Controls**: Start, Stop, or Restart the background daemon directly from the UI.
- **Real-time Status**: Live latency meter, local IP, interface name, and connectivity indicator.
- **Live Logs**: Watch the keepalive background service activity in real time.
- **Diagnostics**: Built-in test suite for DNS, Gateway ping, and HTTP captive portal probes.

---

## 🗑️ Uninstallation

If you ever want to remove it, simply run:
```bash
bash uninstall.sh
```
