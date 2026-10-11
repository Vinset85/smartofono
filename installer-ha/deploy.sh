#!/usr/bin/env bash
# Deploy videocitofono su Home Assistant (SSH).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
HA_HOST="${HA_HOST:-192.168.1.160}"
HA_USER="${HA_USER:-hassio}"
HA_PASS="${HA_PASS:-}"
HA_CONFIG="${HA_CONFIG:-/config}"
HA_SSH="${HA_USER}@${HA_HOST}"
TS="$(date +%s)"

ssh_ha() {
  if [ -n "$HA_PASS" ] && command -v sshpass >/dev/null 2>&1; then
    sshpass -p "$HA_PASS" ssh -o StrictHostKeyChecking=no "${HA_SSH}" "$@"
  else
    ssh -o StrictHostKeyChecking=no "${HA_SSH}" "$@"
  fi
}

scp_ha() {
  if [ -n "$HA_PASS" ] && command -v sshpass >/dev/null 2>&1; then
    sshpass -p "$HA_PASS" scp -O -o StrictHostKeyChecking=no "$@"
  else
    scp -O -o StrictHostKeyChecking=no "$@"
  fi
}

echo "==> Deploy HA -> ${HA_SSH}:${HA_CONFIG}"

TMP="/tmp/vc-deploy-${TS}"
ssh_ha "mkdir -p ${TMP}"

echo "    pyscript + www + lovelace + scripts"
tar -C "${ROOT}" -czf "/tmp/vc-deploy-${TS}.tar.gz" pyscript www lovelace \
  packages/automations.yaml.fixed packages/configuration.yaml.fixed
scp_ha "/tmp/vc-deploy-${TS}.tar.gz" "${HA_SSH}:${TMP}/bundle.tar.gz"
rm -f "/tmp/vc-deploy-${TS}.tar.gz"

ssh_ha "sudo bash -s" <<EOF
set -e
cd ${TMP}
tar -xzf bundle.tar.gz
cp -f pyscript/* ${HA_CONFIG}/pyscript/
cp -f www/* ${HA_CONFIG}/www/
mkdir -p ${HA_CONFIG}/lovelace
cp -f lovelace/* ${HA_CONFIG}/lovelace/
cp -f packages/automations.yaml.fixed /tmp/vc_automations.fixed
cp -f packages/configuration.yaml.fixed /tmp/vc_configuration.fixed
chown -R root:root ${HA_CONFIG}/pyscript ${HA_CONFIG}/www ${HA_CONFIG}/lovelace

python3 - <<'PY'
from pathlib import Path
import re

src = Path('/tmp/vc_automations.fixed').read_text(encoding='utf-8')
dst = Path('/config/automations.yaml')
text = dst.read_text(encoding='utf-8')
ids = re.findall(r"- id: '(1761000000\\d+)'", src)
for aid in ids:
    m = re.search(rf"- id: '{aid}'.*?(?=\\n- id: '|\\Z)", src, re.S)
    if not m:
        continue
    chunk = m.group(0)
    if f"'{aid}'" in text:
        text = re.sub(rf"- id: '{aid}'.*?(?=\\n- id: '|\\Z)", chunk, text,
                      count=1, flags=re.S)
        print('automation', aid, 'aggiornata')
    else:
        text = text.rstrip() + '\\n' + chunk
        print('automation', aid, 'aggiunta')
dst.write_text(text, encoding='utf-8')

cfg_src = Path('/tmp/vc_configuration.fixed').read_text(encoding='utf-8')
cfg = Path('/config/configuration.yaml')
cfg_text = cfg.read_text(encoding='utf-8')
if 'unique_id: vc_health_temp' in cfg_text:
    print('template/statistics: gia presenti')
else:
    start = cfg_src.find('# Sensori template')
    end = cfg_src.find('\ncommand_line:', start if start >= 0 else 0)
    if start < 0 or end < 0:
        raise SystemExit('blocchi template/statistics non trovati nel fixed')
    insert = cfg_src[start:end].strip() + '\\n\\n'
    anchor = 'command_line:'
    if anchor not in cfg_text:
        raise SystemExit('anchor command_line non trovato in configuration.yaml')
    cfg_text = cfg_text.replace(anchor, insert + anchor, 1)
    cfg.write_text(cfg_text, encoding='utf-8')
    print('template/statistics: inseriti')

if 'Videocitofono Guest PINs' in cfg_text:
    print('mqtt guest_pins: gia presente')
else:
    m = re.search(
        r'    - name: "Videocitofono Guest PINs".*?\n      icon: mdi:key-variant',
        cfg_src, re.S)
    if not m:
        print('mqtt guest_pins: SKIP (non in fixed)')
    else:
        block = m.group(0) + '\n'
        anchors = (
            '      icon: mdi:nfc-search-variant',
            '      icon: mdi:heart-pulse',
            '      icon: mdi:alert-octagon-outline',
        )
        inserted = False
        for anchor in anchors:
            if anchor in cfg_text:
                cfg_text = cfg_text.replace(anchor, anchor + '\n' + block, 1)
                inserted = True
                break
        if not inserted:
            raise SystemExit('anchor mqtt sensor non trovato in configuration.yaml')
        cfg.write_text(cfg_text, encoding='utf-8')
        print('mqtt guest_pins: inserito')
PY

cd ${HA_CONFIG}

TOK=\$(cat /run/s6/container_environment/SUPERVISOR_TOKEN 2>/dev/null || true)
if command -v ha >/dev/null 2>&1 && [ -n "\$TOK" ]; then
  ha core check --api-token "\$TOK" || true
  ha core reload --api-token "\$TOK" 2>/dev/null || true
elif command -v ha >/dev/null 2>&1; then
  ha core check || true
fi
rm -rf ${TMP}
EOF

echo "==> Deploy completato."
