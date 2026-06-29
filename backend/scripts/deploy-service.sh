#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-34.158.77.250}"
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/root/mvm-vpn/backend}"
SERVICE="${1:-}"

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SSH_TARGET="${REMOTE_USER}@${REMOTE_HOST}"

TAR_EXCLUDES=(
  --exclude='__pycache__'
  --exclude='.venv'
  --exclude='.env'
  --exclude='._*'
  --exclude='.DS_Store'
)

usage() {
  cat <<EOF
Usage: $(basename "$0") <admin|tg|vk|server-manager|all>

Environment:
  REMOTE_HOST   default: ${REMOTE_HOST}
  REMOTE_USER   default: ${REMOTE_USER}
  REMOTE_DIR    default: ${REMOTE_DIR}
EOF
}

service_paths() {
  case "$1" in
    admin) echo "bot_admin" ;;
    tg|vk) echo "bot" ;;
    server-manager) echo "server_manager" ;;
    all) echo "bot bot_admin server_manager" ;;
    *) return 1 ;;
  esac
}

service_unit() {
  case "$1" in
    admin) echo "mvm-admin-bot.service" ;;
    tg) echo "mvm-tg-bot.service" ;;
    vk) echo "mvm-vk-bot.service" ;;
    server-manager) echo "mvm-server-manager.service" ;;
    *) return 1 ;;
  esac
}

service_requirements() {
  case "$1" in
    admin) echo "bot_admin/requirements.txt" ;;
    tg|vk) echo "bot/requirements.txt" ;;
    server-manager) echo "server_manager/requirements.txt" ;;
    *) return 1 ;;
  esac
}

upload_paths() {
  local service="$1"
  local paths
  paths="$(service_paths "$service")"

  echo ">>> Uploading ${service} to ${SSH_TARGET}:${REMOTE_DIR}"
  # shellcheck disable=SC2086
  tar czf - "${TAR_EXCLUDES[@]}" -C "${BACKEND_DIR}" ${paths} \
    | ssh -o StrictHostKeyChecking=no "${SSH_TARGET}" "mkdir -p '${REMOTE_DIR}' && cd '${REMOTE_DIR}' && tar xzf -"
}

install_and_restart() {
  local service="$1"
  local unit requirements

  unit="$(service_unit "$service")"
  requirements="$(service_requirements "$service")"

  echo ">>> Installing deps and restarting ${unit}"
  ssh -o StrictHostKeyChecking=no "${SSH_TARGET}" bash -s <<EOF
set -euo pipefail
cd '${REMOTE_DIR}'
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r '${requirements}'
systemctl restart '${unit}'
sleep 2
systemctl is-active '${unit}'
EOF
}

deploy_one() {
  local service="$1"
  upload_paths "$service"
  install_and_restart "$service"
  echo ">>> Deployed ${service}"
}

if [[ -z "${SERVICE}" ]]; then
  usage
  exit 1
fi

case "${SERVICE}" in
  admin|tg|vk|server-manager)
    deploy_one "${SERVICE}"
    ;;
  all)
    upload_paths all
    for svc in admin tg vk server-manager; do
      install_and_restart "${svc}"
    done
    echo ">>> Deployed all services"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown service: ${SERVICE}" >&2
    usage
    exit 1
    ;;
esac

echo ">>> Done"
