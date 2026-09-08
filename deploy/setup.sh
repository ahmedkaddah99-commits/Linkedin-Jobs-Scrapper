#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/runr"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

sudo mkdir -p "$INSTALL_DIR"

if [ "$PROJECT_DIR" != "$INSTALL_DIR" ]; then
  echo "This setup script expects the repository to live at $INSTALL_DIR."
  echo "Current repository path: $PROJECT_DIR"
  echo "Clone or move the repo to $INSTALL_DIR, then re-run deploy/setup.sh."
  exit 1
fi

cd "$PROJECT_DIR"

sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-deu

if [ ! -d "$INSTALL_DIR/.venv" ]; then
  python3 -m venv "$INSTALL_DIR/.venv"
fi

"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements-linux.txt"
npm --prefix "$INSTALL_DIR/frontend" install

sudo cp "$INSTALL_DIR/deploy/systemd/runr-api.service" /etc/systemd/system/runr-api.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr-worker.service" /etc/systemd/system/runr-worker.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr-frontend.service" /etc/systemd/system/runr-frontend.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr.target" /etc/systemd/system/runr.target

sudo systemctl daemon-reload
sudo systemctl enable runr.target

cat <<'EOF'
Next steps:
1. Copy your production environment file to /opt/runr/.env
2. Set VITE_API_BASE_URL and BACKEND_ALLOWED_ORIGINS in /opt/runr/.env
3. Run /opt/runr/deploy/deploy.sh
EOF
