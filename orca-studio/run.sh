#!/usr/bin/env bash
# Start ORCA Studio in the foreground (Ctrl+C stops the web app; running ORCA jobs keep going).
cd "$(dirname "$0")"
PY="${ORCA_STUDIO_PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
fi
exec "$PY" -m orca_studio "$@"
