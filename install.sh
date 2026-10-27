#!/usr/bin/env bash
# ==============================================================================
# IISER Bhopal Captive Portal Auto-login & Manager - Automated Installer
# Works seamlessly on Ubuntu, Debian, Fedora, Arch Linux, openSUSE, etc.
# Fully PEP 668 compliant with isolated application virtual environment.
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BLUE}${BOLD}======================================================${NC}"
echo -e "${BLUE}${BOLD}   IISER Bhopal Captive Portal Manager Installer      ${NC}"
echo -e "${BLUE}${BOLD}======================================================${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"
COMPLETIONS_DIR="$SCRIPT_DIR/completions"

# 1. Check Python 3
echo -e "${YELLOW}🔍 Step 1: Checking Python & system dependencies...${NC}"
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ Python 3 is not installed. Please install Python 3 first.${NC}"
    exit 1
fi
PYTHON_BIN="$(which python3)"
echo -e "   Found Python at: ${GREEN}$PYTHON_BIN${NC}"

# Detect package manager
PKG_MANAGER=""
if command -v dnf5 &>/dev/null; then
    PKG_MANAGER="dnf5"
elif command -v dnf &>/dev/null; then
    PKG_MANAGER="dnf"
elif command -v apt-get &>/dev/null; then
    PKG_MANAGER="apt"
elif command -v pacman &>/dev/null; then
    PKG_MANAGER="pacman"
elif command -v zypper &>/dev/null; then
    PKG_MANAGER="zypper"
fi

# Check tkinter
if ! "$PYTHON_BIN" -c "import tkinter" &>/dev/null; then
    echo -e "${YELLOW}⚠️  Python Tkinter not found. Attempting to install...${NC}"
    if [ "$PKG_MANAGER" = "apt" ]; then
        sudo apt-get update && sudo apt-get install -y python3-tk
    elif [ "$PKG_MANAGER" = "dnf" ] || [ "$PKG_MANAGER" = "dnf5" ]; then
        sudo $PKG_MANAGER install -y python3-tkinter
    elif [ "$PKG_MANAGER" = "pacman" ]; then
        sudo pacman -S --noconfirm tk
    elif [ "$PKG_MANAGER" = "zypper" ]; then
        sudo zypper install -y python3-tk
    else
        echo -e "${RED}❌ Please install python3-tk / python3-tkinter for your distribution.${NC}"
        exit 1
    fi
fi
echo -e "   ${GREEN}✔ Tkinter GUI toolkit is available.${NC}"

# Check curl
if ! command -v curl &>/dev/null; then
    echo -e "${YELLOW}⚠️  curl not found. Installing curl...${NC}"
    if [ "$PKG_MANAGER" = "apt" ]; then
        sudo apt-get install -y curl
    elif [ "$PKG_MANAGER" = "dnf" ] || [ "$PKG_MANAGER" = "dnf5" ]; then
        sudo $PKG_MANAGER install -y curl
    elif [ "$PKG_MANAGER" = "pacman" ]; then
        sudo pacman -S --noconfirm curl
    fi
fi
echo -e "   ${GREEN}✔ curl is available.${NC}"

# Check python3-venv
if ! "$PYTHON_BIN" -m venv --help &>/dev/null; then
    echo -e "${YELLOW}⚠️  python3-venv not found. Installing...${NC}"
    if [ "$PKG_MANAGER" = "apt" ]; then
        sudo apt-get install -y python3-venv
    elif [ "$PKG_MANAGER" = "dnf" ] || [ "$PKG_MANAGER" = "dnf5" ]; then
        sudo $PKG_MANAGER install -y python3-virtualenv
    fi
fi

# 2. Setup Application Destination and Permissions
echo ""
echo -e "${YELLOW}📂 Step 2: Preparing secure directories...${NC}"
INSTALL_DIR="$HOME/.local/share/iiserb-login-app"
VENV_DIR="$INSTALL_DIR/venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/Desktop"
APPS_DIR="$HOME/.local/share/applications"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
CONFIG_DIR="$HOME/.config/iiserb_login"
STATE_DIR="$HOME/.local/state/iiserb_login"

# Secure private directories (mode 700)
mkdir -p -m 700 "$CONFIG_DIR"
mkdir -p -m 700 "$STATE_DIR"
mkdir -p -m 755 "$INSTALL_DIR"
mkdir -p -m 755 "$BIN_DIR"
mkdir -p -m 755 "$APPS_DIR"

# 3. Create PEP 668 Compliant Isolated Virtual Environment
echo ""
echo -e "${YELLOW}📦 Step 3: Setting up isolated application environment (PEP 668 compliant)...${NC}"
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/python3" ]; then
    echo -e "   Creating virtual environment at $VENV_DIR..."
    "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"

echo -e "   Installing required packages into isolated venv..."
"$VENV_PIP" install --quiet --upgrade pip setuptools 2>/dev/null || true
"$VENV_PIP" install --quiet customtkinter pillow pystray 2>/dev/null || {
    echo -e "${YELLOW}⚠️  Failed to install pystray; continuing with core customtkinter...${NC}"
    "$VENV_PIP" install --quiet customtkinter pillow 2>/dev/null || true
}
echo -e "   ${GREEN}✔ Isolated environment ready.${NC}"

# 4. Copy Application Source Files
echo ""
echo -e "${YELLOW}🚚 Step 4: Installing application files...${NC}"
cp "$SRC_DIR/app.py" "$INSTALL_DIR/app.py"
cp "$SRC_DIR/backend.py" "$INSTALL_DIR/backend.py"
cp "$SRC_DIR/cli.py" "$INSTALL_DIR/cli.py"
cp "$SRC_DIR/login.sh" "$INSTALL_DIR/login.sh"
cp "$SRC_DIR/icon.png" "$INSTALL_DIR/icon.png"

# Strictly restrict permissions
chmod 700 "$INSTALL_DIR/app.py"
chmod 700 "$INSTALL_DIR/login.sh"
chmod 600 "$INSTALL_DIR/backend.py"
chmod 600 "$INSTALL_DIR/cli.py"
echo -e "   ${GREEN}✔ Copied files with secured permissions (mode 0700/0600).${NC}"

# 5. Create Executable Launcher in ~/.local/bin
cat << EOF > "$BIN_DIR/iiserb-login-app"
#!/bin/bash
exec "$VENV_PYTHON" "$INSTALL_DIR/app.py" "\$@"
EOF
chmod 755 "$BIN_DIR/iiserb-login-app"
echo -e "   ${GREEN}✔ Launcher created at $BIN_DIR/iiserb-login-app${NC}"

# 6. Install Shell Completions
echo ""
echo -e "${YELLOW}🐚 Step 5: Installing shell tab completions...${NC}"
# Bash completion
if [ -d "$COMPLETIONS_DIR" ]; then
    BASH_COMP_DIR="$HOME/.local/share/bash-completion/completions"
    mkdir -p "$BASH_COMP_DIR"
    cp "$COMPLETIONS_DIR/iiserb-login-app.bash" "$BASH_COMP_DIR/iiserb-login-app" 2>/dev/null || true

    # Zsh completion
    ZSH_COMP_DIR="$HOME/.local/share/zsh/site-functions"
    mkdir -p "$ZSH_COMP_DIR"
    cp "$COMPLETIONS_DIR/_iiserb-login-app" "$ZSH_COMP_DIR/_iiserb-login-app" 2>/dev/null || true

    # Fish completion
    FISH_COMP_DIR="$HOME/.config/fish/completions"
    mkdir -p "$FISH_COMP_DIR"
    cp "$COMPLETIONS_DIR/iiserb-login-app.fish" "$FISH_COMP_DIR/iiserb-login-app.fish" 2>/dev/null || true
    echo -e "   ${GREEN}✔ Shell tab completions installed (Bash, Zsh, Fish).${NC}"
fi

# 7. Configure Background Service / Autostart
echo ""
echo -e "${YELLOW}⚙️  Step 6: Configuring keepalive background service...${NC}"
HAS_SYSTEMD=false
if command -v systemctl &>/dev/null && systemctl --user list-units &>/dev/null; then
    HAS_SYSTEMD=true
fi

if [ "$HAS_SYSTEMD" = true ]; then
    mkdir -p "$SYSTEMD_USER_DIR"
    cat << EOF > "$SYSTEMD_USER_DIR/portal-autologin.service"
[Unit]
Description=IISERB Captive Portal Keepalive Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/bin/bash %h/.local/share/iiserb-login-app/login.sh
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable portal-autologin.service 2>/dev/null || true
    echo -e "   ${GREEN}✔ Systemd keepalive service installed and enabled.${NC}"
else
    # Fallback to XDG Autostart for non-systemd distros / containers
    AUTOSTART_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"
    cat << EOF > "$AUTOSTART_DIR/iiserb-portal-autologin.desktop"
[Desktop Entry]
Type=Application
Name=IISERB Autologin Daemon
Exec=/bin/bash $INSTALL_DIR/login.sh
Terminal=false
Hidden=false
EOF
    echo -e "   ${GREEN}✔ XDG Autostart configured (non-systemd environment).${NC}"
fi

# 8. Create Desktop Application Shortcuts
echo ""
echo -e "${YELLOW}🖥️  Step 7: Creating desktop application shortcuts...${NC}"
DESKTOP_FILE_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=IISERB Login
GenericName=Captive Portal Auto-login
Comment=IISER Bhopal Captive Portal Manager & Auto-login
Exec=$VENV_PYTHON $INSTALL_DIR/app.py
Icon=$INSTALL_DIR/icon.png
Terminal=false
Categories=Network;
Keywords=internet;wifi;portal;login;iiserb;
StartupNotify=true"

# Install into Application Menu
echo "$DESKTOP_FILE_CONTENT" > "$APPS_DIR/iiserb-portal-login.desktop"
chmod +x "$APPS_DIR/iiserb-portal-login.desktop"
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi

# Install onto Desktop if folder exists
if [ -d "$DESKTOP_DIR" ]; then
    echo "$DESKTOP_FILE_CONTENT" > "$DESKTOP_DIR/IISERB_Portal_Login.desktop"
    chmod +x "$DESKTOP_DIR/IISERB_Portal_Login.desktop"
    if command -v gio &>/dev/null; then
        gio set "$DESKTOP_DIR/IISERB_Portal_Login.desktop" metadata::trusted true 2>/dev/null || true
    fi
    echo -e "   ${GREEN}✔ Shortcut added to Desktop.${NC}"
fi
echo -e "   ${GREEN}✔ Shortcut added to Applications Menu.${NC}"

# Ensure ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo -e "${YELLOW}💡 Tip: Add ~/.local/bin to your PATH in ~/.bashrc or ~/.zshrc:${NC}"
    echo -e "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
fi

echo ""
echo -e "${GREEN}${BOLD}======================================================${NC}"
echo -e "${GREEN}${BOLD}   Installation Complete! 🎉                         ${NC}"
echo -e "${GREEN}${BOLD}======================================================${NC}"
echo ""
echo -e "Launch the app via:"
echo -e "  1. Desktop shortcut: ${BOLD}IISERB Login${NC}"
echo -e "  2. Terminal command: ${BOLD}iiserb-login-app${NC} (or 'iiserb-login-app --help')"
echo ""
echo -e "To configure your credentials in the terminal:"
echo -e "  ${BOLD}iiserb-login-app config -u <ldap_username>${NC}"
echo ""
