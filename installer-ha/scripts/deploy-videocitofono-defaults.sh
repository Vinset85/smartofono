#!/usr/bin/env bash
# Deploy defaults videocitofono: JSON helper HA, pyscript, automazione start.
set -euo pipefail

HA_HOST="${HA_HOST:-192.168.1.160}"
HA_USER="${HA_USER:-hassio}"
HA_PASS="${HA_PASS:-}"
PI_HOST="${PI_HOST:-192.168.1.185}"
PI_USER="${PI_USER:-vinset}"
PI_KEY="${SSH_KEY:-$HOME/.ssh/id_videocitofono}"
REPO_HA="$(cd "$(dirname "$0")/.." && pwd)"
REPO_RPI="$(cd "$REPO_HA/../installer-rpi" && pwd)"

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

echo "==> [1/3] Deploy RPi: config.example + restore script + systemd"
scp -i "$PI_KEY" -o StrictHostKeyChecking=no \
    "$REPO_RPI/app/config/config.example.yaml" \
    "$REPO_RPI/scripts/restore_config_defaults.py" \
    "$REPO_RPI/systemd/videocitofono.service" \
    "${PI_USER}@${PI_HOST}:/tmp/"

ssh -i "$PI_KEY" -o StrictHostKeyChecking=no "${PI_USER}@${PI_HOST}" 'bash -s' <<'EOF'
set -e
sudo cp /tmp/config.example.yaml /opt/videocitofono/app/config/config.example.yaml
sudo mkdir -p /opt/videocitofono/scripts
sudo cp /tmp/restore_config_defaults.py /opt/videocitofono/scripts/restore_config_defaults.py
sudo chmod 755 /opt/videocitofono/scripts/restore_config_defaults.py
sudo chown vinset:vinset /opt/videocitofono/scripts/restore_config_defaults.py
sudo cp /tmp/videocitofono.service /etc/systemd/system/videocitofono.service
sudo systemctl daemon-reload
/opt/videocitofono/venv/bin/python3 /opt/videocitofono/scripts/restore_config_defaults.py
sudo systemctl restart videocitofono.service
sleep 2
systemctl is-active videocitofono.service
grep feedback_volume /opt/videocitofono/app/config/config.yaml
test ! -f /opt/videocitofono/app/config/config.override.yaml && echo "override: rimosso"
EOF

echo "==> [2/3] Deploy HA: defaults.json + pyscript + script + automazione"
scp_ha "$REPO_HA/config/videocitofono_defaults.json" "${HA_USER}@${HA_HOST}:/tmp/videocitofono_defaults.json"
scp_ha "$REPO_HA/pyscript/defaults.py" "${HA_USER}@${HA_HOST}:/tmp/defaults.py"

ssh_ha 'bash -s' <<'EOF'
set -e
sudo cp /tmp/videocitofono_defaults.json /config/videocitofono_defaults.json
sudo cp /tmp/defaults.py /config/pyscript/defaults.py
sudo chown root:root /config/videocitofono_defaults.json /config/pyscript/defaults.py
EOF

# Patch scripts.yaml: aggiungi videocitofono_carica_defaults se assente
scp_ha "$REPO_HA/packages/scripts.yaml.fixed" "${HA_USER}@${HA_HOST}:/tmp/scripts_videocitofono.fixed"
ssh_ha "sudo python3 - <<'PY'
from pathlib import Path
import re
live = Path('/config/scripts.yaml')
block = Path('/tmp/scripts_videocitofono.fixed').read_text(encoding='utf-8')
m = re.search(r'^videocitofono_carica_defaults:.*?^(?=videocitofono_applica_config:)', block, re.M | re.S)
if not m:
    raise SystemExit('blocco carica_defaults non trovato nel template')
snippet = m.group(0)
text = live.read_text(encoding='utf-8')
if 'videocitofono_carica_defaults:' in text:
    print('script carica_defaults: gia presente')
else:
    text = text.replace('videocitofono_applica_config:', snippet + 'videocitofono_applica_config:', 1)
    live.write_text(text, encoding='utf-8')
    print('script carica_defaults: aggiunto')
PY"

# Patch automations.yaml: aggiungi automation 1761000000014 se assente
scp_ha "$REPO_HA/packages/automations.yaml.fixed" "${HA_USER}@${HA_HOST}:/tmp/automations_videocitofono.fixed"
ssh_ha "sudo python3 - <<'PY'
from pathlib import Path
live = Path('/config/automations.yaml')
block = Path('/tmp/automations_videocitofono.fixed').read_text(encoding='utf-8')
needle = \"id: '1761000000014'\"
if needle in live.read_text(encoding='utf-8'):
    print('automazione 1761000000014: gia presente')
else:
    start = block.find('- id: \\'1761000000014\\'')
    if start < 0:
        raise SystemExit('automazione template non trovata')
    snippet = block[start:]
    live.write_text(live.read_text(encoding='utf-8').rstrip() + '\\n' + snippet, encoding='utf-8')
    print('automazione 1761000000014: aggiunta')
PY"

echo "==> [3/3] Reload HA script + pyscript"
ssh_ha 'TOK=$(cat /run/s6/container_environment/SUPERVISOR_TOKEN 2>/dev/null); \
  curl -sS -X POST -H "Authorization: Bearer $TOK" http://supervisor/core/api/services/script/reload; \
  curl -sS -X POST -H "Authorization: Bearer $TOK" http://supervisor/core/api/services/automation/reload; \
  curl -sS -X POST -H "Authorization: Bearer $TOK" http://supervisor/core/api/services/pyscript/reload'

echo "==> Fatto. Defaults attivi su Pi (ogni restart) e HA (start + applica_config)."
