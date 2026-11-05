#!/usr/bin/env bash
# Install ORCA Studio as a systemd *user* service that starts at boot and keeps running
# when you log out. Run it once as the normal user (not with sudo):   ./install_service.sh
set -euo pipefail
cd "$(dirname "$0")"
APP_DIR="$(pwd)"
SERVICE=orca-studio

echo "== ORCA Studio installer =="
if ! command -v python3 >/dev/null; then echo "python3 not found"; exit 1; fi
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 3.10+ needed (found $PYV)"; exit 1; }

if [ ! -x .venv/bin/python ]; then
  echo "-- creating a private Python environment in $APP_DIR/.venv"
  if ! python3 -m venv .venv; then
    echo "Could not create the environment. On Ubuntu run:  sudo apt install python3-venv   and run this script again."
    exit 1
  fi
fi
echo "-- installing Python packages"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/$SERVICE.service" <<UNIT
[Unit]
Description=ORCA Studio (web app for ORCA batches)
After=network-online.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m orca_studio
Restart=on-failure
RestartSec=5
# Only stop the web app on 'systemctl stop': running ORCA jobs keep going and are
# picked up again when the service starts.
KillMode=process
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable "$SERVICE" >/dev/null
systemctl --user restart "$SERVICE"

# Keep user services (and jobs) running without a logged-in session.
if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
  if ! loginctl enable-linger "$USER" 2>/dev/null; then
    echo "!! Could not enable lingering automatically. Run once:  sudo loginctl enable-linger $USER"
  fi
fi

sleep 2
PORT=$(.venv/bin/python - <<'PY'
from orca_studio import config
print(config.load_settings()["access"]["port"])
PY
)
if systemctl --user is-active --quiet "$SERVICE"; then
  echo "== ORCA Studio is running. Open http://localhost:$PORT in your browser. =="
else
  echo "!! The service did not start. Show the log with:  journalctl --user -u $SERVICE -n 50"
  exit 1
fi
