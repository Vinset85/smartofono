#!/usr/bin/env bash
# Deploy asset HA videocitofono: pyscript NFC, card Lovelace, go2rtc RTSP → .185
set -euo pipefail

HA_HOST="${HA_HOST:-192.168.1.160}"
HA_USER="${HA_USER:-hassio}"
HA_PASS="${HA_PASS:-}"
PI_HOST="${PI_HOST:-192.168.1.185}"
REPO_HA="$(cd "$(dirname "$0")/.." && pwd)"

ssh_ha() {
    if [ -n "$HA_PASS" ] && command -v sshpass >/dev/null 2>&1; then
        sshpass -p "$HA_PASS" ssh -o StrictHostKeyChecking=no "${HA_USER}@${HA_HOST}" "$@"
    else
        ssh -o StrictHostKeyChecking=no "${HA_USER}@${HA_HOST}" "$@"
    fi
}

scp_ha() {
    if [ -n "$HA_PASS" ] && command -v sshpass >/dev/null 2>&1; then
        sshpass -p "$HA_PASS" scp -O -o StrictHostKeyChecking=no "$@"
    else
        scp -O -o StrictHostKeyChecking=no "$@"
    fi
}

echo "==> [1/4] www + pyscript + go2rtc (via /tmp)"
scp_ha "$REPO_HA/www/vc-nfc-card.js" "${HA_USER}@${HA_HOST}:/tmp/vc-nfc-card.js"
scp_ha "$REPO_HA/pyscript/nfc.py" "${HA_USER}@${HA_HOST}:/tmp/nfc.py"
scp_ha "$REPO_HA/config/go2rtc.yaml" "${HA_USER}@${HA_HOST}:/tmp/go2rtc.yaml"
ssh_ha "sudo cp /tmp/vc-nfc-card.js /config/www/vc-nfc-card.js && \
  sudo cp /tmp/nfc.py /config/pyscript/nfc.py && \
  sudo cp /tmp/go2rtc.yaml /config/go2rtc.yaml && \
  sudo chown root:root /config/www/vc-nfc-card.js /config/pyscript/nfc.py /config/go2rtc.yaml"

echo "==> [2/4] sensor evento NFC in configuration.yaml (se assente)"
ssh_ha "sudo python3 - <<'PY'
from pathlib import Path
p = Path('/config/configuration.yaml')
text = p.read_text(encoding='utf-8')
needle = 'Videocitofono Evento'
block = '''    - name: \"Videocitofono Evento\"
      state_topic: \"videocitofono/evento\"
      value_template: \"{{ value_json.tipo | default(value) }}\"
      json_attributes_topic: \"videocitofono/evento\"
      icon: mdi:information-outline
'''
if needle in text:
    print('evento sensor: gia presente')
else:
    marker = 'icon: mdi:nfc-variant'
    idx = text.find(marker)
    if idx < 0:
        raise SystemExit('marker NFC non trovato in configuration.yaml')
    line_end = text.find('\n', idx)
    text = text[:line_end + 1] + block + text[line_end + 1:]
    p.write_text(text, encoding='utf-8')
    print('evento sensor: aggiunto')
PY"

echo "==> [3/4] Lovelace: resource + card NFC in view Utenti"
scp_ha "$REPO_HA/scripts/patch_lovelace_utenti_nfc.py" "${HA_USER}@${HA_HOST}:/tmp/patch_lovelace_utenti_nfc.py"
ssh_ha "sudo python3 /tmp/patch_lovelace_utenti_nfc.py"

echo "==> [4/5] input_button + script applica + automazioni"
"${REPO_HA}/scripts/patch_ha_config_apply.sh" || true

echo "==> [5/5] reload HA (opzionale)"
ssh_ha "TOK=\$(cat /run/s6/container_environment/SUPERVISOR_TOKEN 2>/dev/null); curl -sS -X POST -H \"Authorization: Bearer \$TOK\" http://supervisor/core/restart 2>/dev/null || true"

echo "==> Fatto. Verifica:"
echo "    MQTT broker UI → ${PI_HOST}:1883"
echo "    WebRTC integration → http://${HA_HOST}:1984"
echo "    sensor.videocitofono_evento per feedback iscrizione tag"
