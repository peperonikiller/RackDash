#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "[RackDash] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "[RackDash] Installing Python dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [[ ! -f config.env ]]; then
  cp config.env.example config.env
  chmod 600 config.env
  echo "[RackDash] Created config.env from config.env.example"
fi

echo
echo "RackDash is installed."
echo "Edit: $ROOT/config.env"
echo "Run:  $ROOT/venv/bin/python $ROOT/app.py"
