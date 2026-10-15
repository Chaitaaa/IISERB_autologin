#!/usr/bin/env bash
# Uninstaller for IISER Bhopal Captive Portal Manager

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${YELLOW}${BOLD}Uninstalling IISERB Captive Portal Manager...${NC}"

# Stop and disable service
systemctl --user stop portal-autologin.service 2>/dev/null || true
systemctl --user disable portal-autologin.service 2>/dev/null || true

# Remove files
rm -rf "$HOME/.local/share/iiserb-login-app"
rm -f "$HOME/.local/bin/iiserb-login-app"
rm -f "$HOME/.config/systemd/user/portal-autologin.service"
rm -f "$HOME/Desktop/IISERB_Portal_Login.desktop"
rm -f "$HOME/.local/share/applications/iiserb-portal-login.desktop"

systemctl --user daemon-reload 2>/dev/null || true

echo -e "${GREEN}✔ Application uninstalled successfully.${NC}"
read -p "Do you also want to delete saved credentials/settings (~/.config/iiserb_login)? (y/N): " choice
if [[ "$choice" =~ ^[Yy]$ ]]; then
    rm -rf "$HOME/.config/iiserb_login"
    echo -e "${GREEN}✔ Config removed.${NC}"
fi

echo -e "${GREEN}${BOLD}Uninstallation complete.${NC}"
