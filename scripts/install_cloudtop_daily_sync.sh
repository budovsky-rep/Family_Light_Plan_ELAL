#!/usr/bin/env bash
# Installs and enables the daily systemd --user timer on Cloudtop for the uniform 5-day El Al sync cycle.
# Includes a built-in cooldown guard (--not-before) so zero requests are sent before the cooldown date.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
NOT_BEFORE_DATE="${1:-2026-11-23}"

mkdir -p "${UNIT_DIR}"

cat > "${UNIT_DIR}/fvp-elal-sync.service" <<EOF
[Unit]
Description=Family Vacation Planner — Polite Daily 1/5 Sharded El Al Bonus Sync
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${REPO_DIR}
ExecStart=/usr/bin/python3 ${REPO_DIR}/scripts/sync_elal_to_server.py --shard-count 5 --shard-index auto --not-before ${NOT_BEFORE_DATE}
EOF

cat > "${UNIT_DIR}/fvp-elal-sync.timer" <<EOF
[Unit]
Description=Daily timer for Family Vacation Planner 5-day uniform El Al sync cycle

[Timer]
OnCalendar=*-*-* 09:30:00
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now fvp-elal-sync.timer
loginctl enable-linger "${USER}" 2>/dev/null || true

echo "Installed and enabled daily Cloudtop sync timer (fvp-elal-sync.timer)."
echo "Cooldown guard active: zero requests will be sent before ${NOT_BEFORE_DATE}."
echo "Linger status: $(loginctl show-user "${USER}" -p Linger 2>/dev/null || echo 'unknown')"
systemctl --user list-timers fvp-elal-sync.timer --no-pager
