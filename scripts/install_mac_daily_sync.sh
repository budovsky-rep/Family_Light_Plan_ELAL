#!/usr/bin/env bash
# Installs and starts the persistent macOS LaunchAgent (`com.breezyflights.elal-sync`)
# on your Mac for automatic 2-shards/day El Al bonus sync + 60s polling for the
# Admin Panel "Run Now" button on https://breezyflights.com.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_URL="${1:-https://breezyflights.com}"
SHARDS_PER_DAY="${2:-2}"

python3 "${REPO_DIR}/scripts/sync_elal_to_server.py" \
  --install-mac-agent \
  --server "${SERVER_URL}" \
  --shards-per-day "${SHARDS_PER_DAY}"
