#!/usr/bin/env bash
# Deploy RPi passando da Home Assistant (192.168.1.160).
# Utile quando il Mac non raggiunge il Pi (.52) ma HA è sulla stessa LAN.
#
#   HA_PASS='...' ./scripts/deploy-via-ha.sh
#   HA_HOST=192.168.1.160 PI_HOST=192.168.1.52 PI_PASS='...' ./scripts/deploy-via-ha.sh
#
# Prerequisiti:
#   - addon Advanced SSH su HA (porta 22, utente hassio)
#   - Pi raggiungibile da HA (ping/ssh): verificare con
#       ssh hassio@HA_HOST "ping -c1 PI_HOST"
#   - sshpass sul Mac (brew install sshpass) oppure chiave SSH verso hassio
set -euo pipefail

HA_HOST="${HA_HOST:-192.168.1.160}"
HA_USER="${HA_USER:-hassio}"
HA_PASS="${HA_PASS:-}"
PI_HOST="${PI_HOST:-192.168.1.185}"
PI_USER="${PI_USER:-vinset}"
PI_PASS="${PI_PASS:-}"

LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_INSTALLER="/home/${PI_USER}/videocitofono-installer"
TMP_HA="/tmp/videocitofono-installer"

ssh_ha() {
    if [ -n "$HA_PASS" ] && command -v sshpass >/dev/null 2>&1; then
        sshpass -p "$HA_PASS" ssh -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            "${HA_USER}@${HA_HOST}" "$@"
    else
        ssh -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            "${HA_USER}@${HA_HOST}" "$@"
    fi
}

scp_ha() {
    if [ -n "$HA_PASS" ] && command -v sshpass >/dev/null 2>&1; then
        sshpass -p "$HA_PASS" scp -O -r -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null "$@"
    else
        scp -O -r -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null "$@"
    fi
}

echo "==> Verifica reachability Pi da HA (${PI_HOST})"
if ! ssh_ha "ping -c 1 -W 3 ${PI_HOST} >/dev/null 2>&1"; then
    echo "ERRORE: da ${HA_HOST} il Pi ${PI_HOST} non risponde al ping." >&2
    echo "  Il videocitofono può funzionare in locale (touchscreen) ma HA/MQTT/deploy" >&2
    echo "  richiedono che il Pi sia di nuovo sulla LAN (cavo Ethernet consigliato)." >&2
    exit 1
fi

echo "==> [1/4] SCP installer → HA:${TMP_HA}"
ssh_ha "rm -rf '${TMP_HA}' && mkdir -p '${TMP_HA}'"
scp_ha "${LOCAL_ROOT}/." "${HA_USER}@${HA_HOST}:${TMP_HA}/"

echo "==> [2/4] SCP installer HA → Pi:${REMOTE_INSTALLER}"
if [ -n "$PI_PASS" ] && command -v sshpass >/dev/null 2>&1; then
    ssh_ha "sshpass -p '${PI_PASS}' scp -O -r -o StrictHostKeyChecking=no \
        '${TMP_HA}/' '${PI_USER}@${PI_HOST}:${REMOTE_INSTALLER}/'"
else
    ssh_ha "scp -O -r -o StrictHostKeyChecking=no \
        '${TMP_HA}/' '${PI_USER}@${PI_HOST}:${REMOTE_INSTALLER}/'"
fi

echo "==> [3/3] install.sh (no apt/pip) + merge NFC + restart su Pi"
RUN_INSTALL="cd '${REMOTE_INSTALLER}' && chmod +x scripts/install.sh && SKIP_APT=1 SKIP_PIP_UPGRADE=1 ./scripts/install.sh"
RUN_MERGE="/opt/videocitofono/venv/bin/python3 '${REMOTE_INSTALLER}/scripts/merge_nfc_config.py' || true"
RUN_RESTART="sudo systemctl restart videocitofono.service && systemctl is-active videocitofono.service"

if [ -n "$PI_PASS" ] && command -v sshpass >/dev/null 2>&1; then
    ssh_ha "sshpass -p '${PI_PASS}' ssh -o StrictHostKeyChecking=no \
        '${PI_USER}@${PI_HOST}' \"${RUN_INSTALL} && ${RUN_MERGE} && ${RUN_RESTART}\""
else
    ssh_ha "ssh -o StrictHostKeyChecking=no '${PI_USER}@${PI_HOST}' \
        \"${RUN_INSTALL} && ${RUN_MERGE} && ${RUN_RESTART}\""
fi

echo "==> Deploy via HA completato (NFC non forzato via MQTT: serve token cmd)."
