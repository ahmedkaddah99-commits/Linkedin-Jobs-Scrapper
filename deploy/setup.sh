#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/runr"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_PYTHON_VERSION="Python 3.12.7"
PYTHON_BIN="${RUNR_PYTHON_BIN:-python3.12}"

sudo mkdir -p "$INSTALL_DIR"

if [ "$PROJECT_DIR" != "$INSTALL_DIR" ]; then
  echo "This setup script expects the repository to live at $INSTALL_DIR."
  echo "Current repository path: $PROJECT_DIR"
  echo "Clone or move the repo to $INSTALL_DIR, then re-run deploy/setup.sh."
  exit 1
fi

cd "$PROJECT_DIR"

sudo apt-get update
sudo apt-get install -y chrony nodejs npm tesseract-ocr tesseract-ocr-deu python3.12-venv

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Missing required Python binary: $PYTHON_BIN" >&2
  exit 1
fi
actual_python_version="$($PYTHON_BIN --version 2>&1)"
if [ "$actual_python_version" != "$EXPECTED_PYTHON_VERSION" ]; then
  echo "Expected $EXPECTED_PYTHON_VERSION, got $actual_python_version from $PYTHON_BIN" >&2
  exit 1
fi

if [ ! -f "$PROJECT_DIR/.env" ] || [ ! -f "$PROJECT_DIR/.env.acquisition" ]; then
  echo "Create .env and .env.acquisition from deploy/acquisition.env.example before setup." >&2
  exit 1
fi

if ! id -u runr >/dev/null 2>&1; then
  sudo useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin runr
fi
if ! id -u runr-acquisition >/dev/null 2>&1; then
  sudo useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin runr-acquisition
fi

sudo install -d -o runr -g runr -m 0750 \
  /var/lib/runr/api-data \
  /var/lib/runr/customer-data \
  /var/log/runr \
  /var/log/runr/customer
sudo install -d -o runr-acquisition -g runr-acquisition -m 0750 \
  /var/lib/runr/acquisition-data \
  /srv/runr/state \
  /srv/runr/exports \
  /srv/runr/state/locks \
  /srv/runr/exports/receipts \
  /srv/runr/backups
sudo install -d -o runr-acquisition -g runr-acquisition -m 0750 /var/log/runr/acquisition
sudo install -d -o root -g runr-acquisition -m 0750 /srv/runr/shared/inputs
if [ "$PROJECT_DIR/.env" != "$INSTALL_DIR/.env" ]; then
  sudo install -o root -g runr -m 0640 "$PROJECT_DIR/.env" "$INSTALL_DIR/.env"
else
  sudo chown root:runr "$INSTALL_DIR/.env"
  sudo chmod 0640 "$INSTALL_DIR/.env"
fi
if [ "$PROJECT_DIR/.env.acquisition" != "$INSTALL_DIR/.env.acquisition" ]; then
  sudo install -o root -g runr-acquisition -m 0640 "$PROJECT_DIR/.env.acquisition" "$INSTALL_DIR/.env.acquisition"
else
  sudo chown root:runr-acquisition "$INSTALL_DIR/.env.acquisition"
  sudo chmod 0640 "$INSTALL_DIR/.env.acquisition"
fi

if [ ! -d "$INSTALL_DIR/.venv" ]; then
  sudo "$PYTHON_BIN" -m venv "$INSTALL_DIR/.venv"
fi

venv_version="$($INSTALL_DIR/.venv/bin/python --version 2>&1)"
if [ "$venv_version" != "$EXPECTED_PYTHON_VERSION" ]; then
  echo "Expected $EXPECTED_PYTHON_VERSION in $INSTALL_DIR/.venv, got $venv_version" >&2
  exit 1
fi
sudo "$INSTALL_DIR/.venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements-linux.txt"
sudo env PLAYWRIGHT_BROWSERS_PATH=/ms-playwright "$INSTALL_DIR/.venv/bin/python" -m playwright install --with-deps chromium
sudo chmod -R a+rX /ms-playwright
npm --prefix "$INSTALL_DIR/frontend" install

sudo cp "$INSTALL_DIR/deploy/systemd/runr-api.service" /etc/systemd/system/runr-api.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr-worker.service" /etc/systemd/system/runr-worker.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr-acquisition-worker.service" /etc/systemd/system/runr-acquisition-worker.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr-acquisition-cycle.service" /etc/systemd/system/runr-acquisition-cycle.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr-acquisition-cycle.timer" /etc/systemd/system/runr-acquisition-cycle.timer
sudo cp "$INSTALL_DIR/deploy/systemd/runr-acquisition-linkedin.service" /etc/systemd/system/runr-acquisition-linkedin.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr-acquisition-linkedin.timer" /etc/systemd/system/runr-acquisition-linkedin.timer
sudo cp "$INSTALL_DIR/deploy/systemd/runr-acquisition-employer.service" /etc/systemd/system/runr-acquisition-employer.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr-acquisition-employer.timer" /etc/systemd/system/runr-acquisition-employer.timer
sudo cp "$INSTALL_DIR/deploy/systemd/runr-acquisition-publisher.service" /etc/systemd/system/runr-acquisition-publisher.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr-acquisition-publisher.timer" /etc/systemd/system/runr-acquisition-publisher.timer
sudo cp "$INSTALL_DIR/deploy/systemd/runr-frontend.service" /etc/systemd/system/runr-frontend.service
sudo cp "$INSTALL_DIR/deploy/systemd/runr.target" /etc/systemd/system/runr.target
sudo install -D -m 0644 "$INSTALL_DIR/deploy/systemd/runr-journald.conf" /etc/systemd/journald.conf.d/runr.conf

sudo systemctl daemon-reload
sudo systemctl restart systemd-journald
# The legacy combined timer must not compete with the independent source
# timers. Keep its unit available for compatibility, but disable any old
# activation left by a previous release.
sudo systemctl disable --now runr-acquisition-cycle.timer 2>/dev/null || true
sudo systemctl enable runr.target

cat <<'EOF'
Next steps:
1. Keep /opt/runr/.env limited to the API/customer runtime and keep
   /opt/runr/.env.acquisition limited to acquisition credentials.
2. Set VITE_API_BASE_URL and BACKEND_ALLOWED_ORIGINS in /opt/runr/.env.
3. Review the selected release commit, provider limits, region and firewall
   policy before starting services.
4. Run /opt/runr/deploy/deploy.sh
EOF
