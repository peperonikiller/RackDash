#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="${SUDO_USER:-$USER}"
UNIT="/etc/systemd/system/rackdash.service"

if [[ ! -x "$ROOT/venv/bin/python" ]]; then
  echo "RackDash venv is missing. Run ./install.sh first."
  exit 1
fi

sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=RackDash rackmount dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$ROOT
ExecStart=$ROOT/venv/bin/python $ROOT/app.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now rackdash.service
systemctl --no-pager --full status rackdash.service
