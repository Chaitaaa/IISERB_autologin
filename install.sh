#!/usr/bin/env bash
# ==============================================================================
# IISER Bhopal Captive Portal Auto-login & Manager - Automated Installer
# Works on Ubuntu, Debian, Fedora, Arch Linux, Linux Mint, Pop!_OS, etc.
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

# 1. Check Python 3
echo -e "${YELLOW}🔍 Step 1: Checking Python environment...${NC}"
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
    else
        echo -e "${RED}❌ Please install python3-tk / python3-tkinter manually for your distribution.${NC}"
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

# Check pip
if ! "$PYTHON_BIN" -m pip --version &>/dev/null; then
    echo -e "${YELLOW}⚠️  Python pip not found. Installing python3-pip...${NC}"
    if [ "$PKG_MANAGER" = "apt" ]; then
        sudo apt-get install -y python3-pip
    elif [ "$PKG_MANAGER" = "dnf" ] || [ "$PKG_MANAGER" = "dnf5" ]; then
        sudo $PKG_MANAGER install -y python3-pip
    elif [ "$PKG_MANAGER" = "pacman" ]; then
        sudo pacman -S --noconfirm python-pip
    fi
fi

# 2. Install Python dependencies (customtkinter)
echo ""
echo -e "${YELLOW}📦 Step 2: Checking CustomTkinter library...${NC}"
if ! "$PYTHON_BIN" -c "import customtkinter" &>/dev/null; then
    echo -e "   Installing customtkinter via pip..."
    "$PYTHON_BIN" -m pip install customtkinter --break-system-packages --quiet 2>/dev/null || \
    "$PYTHON_BIN" -m pip install customtkinter --user --quiet 2>/dev/null || \
    "$PYTHON_BIN" -m pip install customtkinter --quiet 2>/dev/null || {
        echo -e "${RED}❌ Failed to install customtkinter via pip. Please run: pip3 install customtkinter${NC}"
        exit 1
    }
fi
echo -e "   ${GREEN}✔ CustomTkinter installed successfully.${NC}"

# 3. Create destination folders
echo ""
echo -e "${YELLOW}📂 Step 3: Installing application files...${NC}"
INSTALL_DIR="$HOME/.local/share/iiserb-login-app"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/Desktop"
APPS_DIR="$HOME/.local/share/applications"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$APPS_DIR"
mkdir -p "$SYSTEMD_USER_DIR"

# Copy source files
cp "$SRC_DIR/app.py" "$INSTALL_DIR/app.py"
cp "$SRC_DIR/backend.py" "$INSTALL_DIR/backend.py"
cp "$SRC_DIR/cli.py" "$INSTALL_DIR/cli.py"
cp "$SRC_DIR/login.sh" "$INSTALL_DIR/login.sh"
cp "$SRC_DIR/icon.png" "$INSTALL_DIR/icon.png"

chmod +x "$INSTALL_DIR/app.py"
chmod +x "$INSTALL_DIR/login.sh"
echo -e "   ${GREEN}✔ Copied application files to $INSTALL_DIR${NC}"

# 4. Create executable launcher in ~/.local/bin
cat << EOF > "$BIN_DIR/iiserb-login-app"
#!/bin/bash
exec "$PYTHON_BIN" "$INSTALL_DIR/app.py" "\$@"
EOF
chmod +x "$BIN_DIR/iiserb-login-app"
echo -e "   ${GREEN}✔ Created launcher at $BIN_DIR/iiserb-login-app${NC}"

# 5. Create Systemd User Service
echo ""
echo -e "${YELLOW}⚙️  Step 4: Configuring background systemd service...${NC}"
cat << EOF > "$SYSTEMD_USER_DIR/portal-autologin.service"
[Unit]
Description=IISERB Captive Portal Autologin
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

systemctl --user daemon-reload
systemctl --user enable portal-autologin.service >/dev/null 2>&1 || true
echo -e "   ${GREEN}✔ Systemd background service enabled.${NC}"

# 6. Create Desktop entries
echo ""
echo -e "${YELLOW}🖥️  Step 5: Creating desktop shortcuts...${NC}"
DESKTOP_FILE_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=IISERB Login
GenericName=Captive Portal Auto-login
Comment=IISER Bhopal Captive Portal Manager & Auto-login
Exec=$PYTHON_BIN $INSTALL_DIR/app.py
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

# Ensure ~/.local/bin is in PATH if not already
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
echo -e "You can launch the app by:"
echo -e "  1. Double clicking ${BOLD}IISERB Login${NC} on your Desktop"
echo -e "  2. Searching for ${BOLD}IISERB Login${NC} in your Application Menu"
echo -e "  3. Running ${BOLD}iiserb-login-app${NC} in the terminal"
echo ""
echo -e "Please open the app to enter your LDAP username and password in the Settings tab."
echo ""
