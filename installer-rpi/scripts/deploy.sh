#!/usr/bin/env bash
# Deploy da Mac/PC → Raspberry: rsync della cartella installer-rpi + install.sh + restart.
# Prerequisiti: SSH senza password (chiave) verso il Pi, Pi acceso sulla stessa LAN.
#
#   ./scripts/deploy.sh
#   DEPLOY_HOST=192.168.1.80 DEPLOY_USER=vinset ./scripts/deploy.sh
#   UPGRADE_DEPS=1 ./scripts/deploy.sh   # pip upgrade (numpy 2 rompe picamera2)
#
# Se il Mac non raggiunge il Pi (SSH timeout) ma HA sì:
#   HA_PASS='...' PI_PASS='...' ./scripts/deploy-via-ha.sh
set -euo pipefail

HOST="${DEPLOY_HOST:-192.168.1.185}"
RUSER="${DEPLOY_USER:-vinset}"
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_DIR="/home/${RUSER}/videocitofono-installer"
SSH_KEY="${DEPLOY_SSH_KEY:-$HOME/.ssh/id_videocitofono}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20 -o ConnectionAttempts=1)
if [ -f "$SSH_KEY" ]; then
  SSH_OPTS+=(-i "$SSH_KEY")
fi
SSH_BASE=(ssh "${SSH_OPTS[@]}")

echo "==> Rsync → ${RUSER}@${HOST}:${REMOTE_DIR}"
RSYNC_SSH="ssh ${SSH_OPTS[*]}"
rsync -avz --delete -e "$RSYNC_SSH" \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  "${LOCAL_ROOT}/" "${RUSER}@${HOST}:${REMOTE_DIR}/"

echo "==> Install dipendenze + copia in /opt, merge NFC se assente, restart"
"${SSH_BASE[@]}" "${RUSER}@${HOST}" "
set -euo pipefail
chmod +x '${REMOTE_DIR}/scripts/install.sh' '${REMOTE_DIR}/scripts/upgrade-deps.sh' || true
cd '${REMOTE_DIR}'
SKIP_APT=1 SKIP_PIP_UPGRADE=1 ./scripts/install.sh
if [[ '${UPGRADE_DEPS:-0}' == '1' ]]; then
  ./scripts/upgrade-deps.sh || true
else
  echo 'skip upgrade-deps (UPGRADE_DEPS=1 per forzare; numpy 2 rompe picamera2)'
fi
/opt/videocitofono/venv/bin/python3 '${REMOTE_DIR}/scripts/merge_nfc_config.py' || true
chmod +x '${REMOTE_DIR}/scripts/configure-static-ip.sh' || true
if [[ '${FORCE_STATIC_IP:-0}' == '1' ]]; then
  '${REMOTE_DIR}/scripts/configure-static-ip.sh' || true
else
  echo 'skip configure-static-ip (FORCE_STATIC_IP=1 per forzare; evita blip NM)'
fi
/opt/videocitofono/venv/bin/python3 '${REMOTE_DIR}/scripts/set_nfc_override.py'
sudo systemctl restart videocitofono.service
systemctl is-active videocitofono.service
"

echo "==> Deploy completato. Log: ssh ${RUSER}@${HOST} 'journalctl -u videocitofono -n 40 --no-pager'"
