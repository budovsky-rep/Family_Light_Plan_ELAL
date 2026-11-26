#!/usr/bin/env bash
# Installs and enables the always-on Cloudtop systemd --user sync watchdog agent:
# - Runs 2 polite shards per day automatically (~every 11.5h, catching up immediately after any reboot/downtime)
# - Listens every 60s for 1-click "הפעל סנכרון עכשיו" requests from the breezyflights.com Admin Panel
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
SERVER_URL="${1:-https://breezyflights.com}"
SHARDS_PER_DAY="${2:-2}"

mkdir -p "${UNIT_DIR}"

# Stop legacy daily timer if previously installed so only the smart watchdog daemon manages runs
systemctl --user disable --now fvp-elal-sync.timer 2>/dev/null || true

cat > "${UNIT_DIR}/fvp-elal-sync-agent.service" <<EOF
[Unit]
Description=BreezyFlights — Cloudtop 2x/Day El Al Bonus Sync Watchdog & Admin Remote Trigger Agent
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
ExecStart=/usr/bin/python3 -u ${REPO_DIR}/scripts/sync_elal_to_server.py --daemon --no-local --server ${SERVER_URL} --shards-per-day ${SHARDS_PER_DAY}
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now fvp-elal-sync-agent.service
loginctl enable-linger "${USER}" 2>/dev/null || true

echo "Installed and started Cloudtop sync watchdog daemon (fvp-elal-sync-agent.service)."
echo "Schedule: ${SHARDS_PER_DAY} polite shards/day + live 60s polling for Admin Panel manual triggers."
echo "Linger status: $(loginctl show-user "${USER}" -p Linger 2>/dev/null || echo 'unknown')"
systemctl --user status fvp-elal-sync-agent.service --no-pager -n 12
