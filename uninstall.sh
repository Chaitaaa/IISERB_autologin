#!/usr/bin/env bash
# ==============================================================================
# Uninstaller for IISER Bhopal Captive Portal Manager
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${YELLOW}${BOLD}Uninstalling IISERB Captive Portal Manager...${NC}"

# Stop and disable systemd service / timers
systemctl --user stop portal-autologin.service 2>/dev/null || true
systemctl --user disable portal-autologin.service 2>/dev/null || true
systemctl --user stop portal-autologin.timer 2>/dev/null || true
systemctl --user disable portal-autologin.timer 2>/dev/null || true

# Remove binaries and application files
rm -rf "$HOME/.local/share/iiserb-login-app"
rm -f "$HOME/.local/bin/iiserb-login-app"
rm -f "$HOME/.config/systemd/user/portal-autologin.service"
rm -f "$HOME/.config/systemd/user/portal-autologin-oneshot.service"
rm -f "$HOME/.config/systemd/user/portal-autologin.timer"
rm -f "$HOME/.config/autostart/iiserb-portal-autologin.desktop"
rm -f "$HOME/Desktop/IISERB_Portal_Login.desktop"
rm -f "$HOME/.local/share/applications/iiserb-portal-login.desktop"

# Remove shell completions
rm -f "$HOME/.local/share/bash-completion/completions/iiserb-login-app"
rm -f "$HOME/.local/share/zsh/site-functions/_iiserb-login-app"
rm -f "$HOME/.config/fish/completions/iiserb-login-app.fish"

systemctl --user daemon-reload 2>/dev/null || true

echo -e "${GREEN}✔ Application binaries and services uninstalled successfully.${NC}"
read -p "Do you also want to remove saved credentials/settings (~/.config/iiserb_login) and logs? (y/N): " choice
if [[ "$choice" =~ ^[Yy]$ ]]; then
    rm -rf "$HOME/.config/iiserb_login"
    rm -rf "$HOME/.local/state/iiserb_login"
    echo -e "${GREEN}✔ Configuration and state removed.${NC}"
fi

echo -e "${GREEN}${BOLD}Uninstallation complete.${NC}"
