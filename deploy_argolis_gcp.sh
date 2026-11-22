#!/usr/bin/env bash
# ==============================================================================
# Family Vacation Planner — Argolis / GCP Deployment Script
# Supports two deployment modes in your Argolis GCP Project:
#   1. Cloud Run (`./deploy_argolis_gcp.sh cloud-run <PROJECT_ID> [REGION]`)
#      -> Deploys a serverless HTTPS container with outbound internet access to
#         https://www.elal.com/rbddataclients/ and returns a live https:// URL.
#   2. Compute Engine VM (`./deploy_argolis_gcp.sh gce-vm <PROJECT_ID> [ZONE] [DOMAIN]`)
#      -> Creates a Debian 12 VM in Argolis with a static IP, opens ports 80/443,
#         installs the systemd service + Caddy reverse proxy (automatic HTTPS when
#         DOMAIN is provided), and prints the live URL.
# ==============================================================================
set -euo pipefail

MODE="${1:-help}"
PROJECT_ID="${2:-}"
LOCATION="${3:-}"
DOMAIN="${4:-${DOMAIN:-}}"

if [[ "$MODE" == "help" || -z "$PROJECT_ID" ]]; then
  cat <<'EOF'
Usage:
  1) Deploy to Google Cloud Run (Recommended — automatic HTTPS URL for mobile & desktop):
     ./deploy_argolis_gcp.sh cloud-run <YOUR_ARGOLIS_PROJECT_ID> [me-west1]

  2) Deploy to a Google Compute Engine VM in Argolis (with Caddy + optional HTTPS domain):
     ./deploy_argolis_gcp.sh gce-vm <YOUR_ARGOLIS_PROJECT_ID> [me-west1-a] [breezyflights.com]
EOF
  exit 0
fi

gcloud config set project "$PROJECT_ID"

if [[ "$MODE" == "cloud-run" ]]; then
  REGION="${LOCATION:-me-west1}"
  echo "Deploying Family Vacation Planner to Cloud Run in project=$PROJECT_ID region=$REGION..."
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project "$PROJECT_ID"
  gcloud run deploy family-vacation-planner \
    --source . \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars="ELAL_LIVE_FETCH_ENABLED=1" \
    --port 8080 \
    --memory 512Mi \
    --cpu 1
  echo "Done! Your live HTTPS URL is printed above."
  exit 0
fi

if [[ "$MODE" == "gce-vm" ]]; then
  ZONE="${LOCATION:-me-west1-a}"
  REGION="${ZONE%-*}"
  VM_NAME="family-vacation-planner-vm"
  STATIC_IP_NAME="family-vacation-planner-ip"

  if [[ -n "$DOMAIN" && ! "$DOMAIN" =~ ^[a-zA-Z0-9.-]+$ ]]; then
    echo "Invalid DOMAIN: '$DOMAIN'" >&2
    exit 1
  fi

  echo "Provisioning Compute Engine VM '$VM_NAME' in project=$PROJECT_ID zone=$ZONE..."
  gcloud services enable compute.googleapis.com --project "$PROJECT_ID"

  if ! gcloud compute firewall-rules describe allow-vacation-planner-web --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud compute firewall-rules create allow-vacation-planner-web \
      --project "$PROJECT_ID" \
      --allow tcp:80,tcp:443 \
      --target-tags=vacation-planner-web \
      --description="Allow HTTP/HTTPS (80, 443) for Family Vacation Planner Caddy proxy"
  else
    gcloud compute firewall-rules update allow-vacation-planner-web \
      --project "$PROJECT_ID" \
      --rules=tcp:80,tcp:443
  fi

  if gcloud compute firewall-rules describe allow-vacation-planner-8080 --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "Removing legacy public port 8080 firewall rule (traffic now goes through Caddy on 80/443)..."
    gcloud compute firewall-rules delete allow-vacation-planner-8080 --project "$PROJECT_ID" --quiet
  fi

  if ! gcloud compute instances describe "$VM_NAME" --zone "$ZONE" --project "$PROJECT_ID" >/dev/null 2>&1; then
    if ! gcloud compute addresses describe "$STATIC_IP_NAME" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
      gcloud compute addresses create "$STATIC_IP_NAME" \
        --project "$PROJECT_ID" \
        --region "$REGION"
    fi
    STATIC_IP="$(gcloud compute addresses describe "$STATIC_IP_NAME" --region "$REGION" --project "$PROJECT_ID" --format='get(address)')"

    gcloud compute instances create "$VM_NAME" \
      --project "$PROJECT_ID" \
      --zone "$ZONE" \
      --machine-type=e2-medium \
      --image-family=debian-12 \
      --image-project=debian-cloud \
      --address="$STATIC_IP" \
      --tags=vacation-planner-web
    echo "Waiting 20s for SSH on VM..."
    sleep 20
  fi

  echo "Uploading application code to $VM_NAME..."
  TAR_PATH="/tmp/family_vacation_planner_deploy.tar.gz"
  tar --exclude='.git' --exclude='__pycache__' --exclude='data/*.db' -czf "$TAR_PATH" .
  gcloud compute scp "$TAR_PATH" "$VM_NAME:/tmp/app.tar.gz" --zone "$ZONE" --project "$PROJECT_ID"

  gcloud compute ssh "$VM_NAME" --zone "$ZONE" --project "$PROJECT_ID" --command="
    sudo apt-get update -y && sudo apt-get install -y python3 python3-yaml sqlite3 caddy
    sudo mkdir -p /opt/family_vacation_planner
    sudo tar -xzf /tmp/app.tar.gz -C /opt/family_vacation_planner
    sudo mkdir -p /opt/family_vacation_planner/data
    sudo mkdir -p /etc/family_vacation_planner
    sudo chmod 700 /etc/family_vacation_planner
    sudo tee /etc/systemd/system/family-vacation-planner.service >/dev/null <<'UNIT'
[Unit]
Description=Family Vacation Planner Web & API Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/family_vacation_planner
Environment=HOST=127.0.0.1
Environment=PORT=8080
Environment=ELAL_LIVE_FETCH_ENABLED=1
Environment=VACATION_PLANNER_DB_PATH=/opt/family_vacation_planner/data/vacation_planner.db
EnvironmentFile=-/etc/family_vacation_planner/auth.env
ExecStart=/usr/bin/python3 -m backend.app.main --host 127.0.0.1 --port 8080
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
    sudo systemctl daemon-reload
    sudo systemctl enable family-vacation-planner.service
    sudo systemctl restart family-vacation-planner.service

    if [[ -n '$DOMAIN' ]]; then
      printf '%s {\n\treverse_proxy 127.0.0.1:8080\n}\n' '$DOMAIN' | sudo tee /etc/caddy/Caddyfile >/dev/null
    elif ! sudo grep -q 'reverse_proxy' /etc/caddy/Caddyfile 2>/dev/null; then
      printf ':80 {\n\treverse_proxy 127.0.0.1:8080\n}\n' | sudo tee /etc/caddy/Caddyfile >/dev/null
    fi
    sudo caddy validate --config /etc/caddy/Caddyfile
    sudo systemctl enable --now caddy
    sudo systemctl reload caddy
  "

  EXT_IP="$(gcloud compute instances describe "$VM_NAME" --zone "$ZONE" --project "$PROJECT_ID" --format='get(networkInterfaces[0].accessConfigs[0].natIP)')"
  echo "=================================================================="
  echo "Family Vacation Planner is LIVE on your Argolis GCE VM:"
  if [[ -n "$DOMAIN" ]]; then
    echo "  https://${DOMAIN}  (VM IP: ${EXT_IP})"
  else
    echo "  http://${EXT_IP}"
  fi
  echo "=================================================================="
  exit 0
fi

echo "Unknown mode: $MODE (use 'cloud-run' or 'gce-vm')"
exit 1
