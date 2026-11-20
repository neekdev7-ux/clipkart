#!/usr/bin/env bash
# ClipNova GTA 6 Edition — one-command server setup (Ubuntu 22.04/24.04).
# Usage on a fresh VPS (as root or a sudo user):
#   curl -fsSL https://raw.githubusercontent.com/neekdev7-ux/clipkart/main/gta6/deploy.sh | bash
# Then edit ~/clipkart/gta6/.env and open http://YOUR-SERVER-IP:8000
set -euo pipefail

REPO_URL="https://github.com/neekdev7-ux/clipkart.git"
INSTALL_DIR="$HOME/clipkart"

echo "==> Installing Docker + git ..."
if command -v sudo >/dev/null 2>&1 && [ "$(id -u)" -ne 0 ]; then SUDO=sudo; else SUDO=""; fi
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq git docker.io docker-compose-plugin curl ufw > /dev/null
$SUDO systemctl enable --now docker > /dev/null 2>&1 || true

echo "==> Getting the code ..."
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  rm -rf "$INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR/gta6"
[ -f .env ] || cp .env.example .env

echo "==> Building + starting ClipNova GTA 6 (dry-run mode by default) ..."
$SUDO docker compose up -d --build

# Open the dashboard port if a firewall is active.
if $SUDO ufw status 2>/dev/null | grep -q "Status: active"; then
  $SUDO ufw allow 8000/tcp > /dev/null
fi

IP=$(curl -fsSL --max-time 8 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
echo ""
echo "ClipNova GTA 6 is running."
echo "Dashboard: http://$IP:8000"
echo ""
echo "Next steps:"
echo "  1. Open the dashboard and press Start monitor (works with no keys, dry-run)."
echo "  2. For YouTube uploads: fill YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET in"
echo "     $INSTALL_DIR/gta6/.env (see README.md OAuth steps), restart with:"
echo "     docker compose -f $INSTALL_DIR/gta6/docker-compose.yml up -d"
echo "  3. Logs: docker logs -f clipnova-gta6  |  Stop: docker compose -f $INSTALL_DIR/gta6/docker-compose.yml down"
