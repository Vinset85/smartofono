#!/usr/bin/env bash
# Configura Mosquitto con autenticazione per videocitofono.
# Uso: sudo ./scripts/setup-mqtt-auth.sh [password_videocitofono] [password_ha]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASSWD_FILE="/etc/mosquitto/conf.d/videocitofono.passwd"
CONF_DST="/etc/mosquitto/conf.d/videocitofono.conf"
APP_USER="${APP_USER:-vinset}"
APP_ROOT="${APP_ROOT:-/opt/videocitofono}"

VC_PASS="${1:-}"
HA_PASS="${2:-}"

if [[ -z "${VC_PASS}" ]]; then
  VC_PASS="$(openssl rand -hex 16)"
  echo "Password videocitofono generata: ${VC_PASS}"
fi
if [[ -z "${HA_PASS}" ]]; then
  HA_PASS="$(openssl rand -hex 16)"
  echo "Password homeassistant generata: ${HA_PASS}"
fi

apt-get install -y mosquitto mosquitto-clients >/dev/null 2>&1 || true

install -m 0644 "${REPO_ROOT}/config/mosquitto-videocitofono.conf" "${CONF_DST}"
touch "${PASSWD_FILE}"
chmod 600 "${PASSWD_FILE}"
chown mosquitto:mosquitto "${PASSWD_FILE}" 2>/dev/null || true
mosquitto_passwd -b "${PASSWD_FILE}" videocitofono "${VC_PASS}"
mosquitto_passwd -b "${PASSWD_FILE}" homeassistant "${HA_PASS}"

# Il mosquitto.conf di Debian dichiara `listener 1883` e `allow_anonymous true`
# DOPO include_dir, quindi il listener del drop-in risulterebbe duplicato e
# mosquitto non partirebbe ("Duplicate listener on port 1883"); inoltre
# allow_anonymous true, essendo processato per ultimo, riaprirebbe il broker.
MAIN_CONF="/etc/mosquitto/mosquitto.conf"
if [[ -f "${MAIN_CONF}" ]]; then
  cp -n "${MAIN_CONF}" "${MAIN_CONF}.bak-preauth" 2>/dev/null || true
  python3 - "${MAIN_CONF}" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
out, changed = [], 0
for line in p.read_text().splitlines():
    if line.strip() in ("listener 1883", "allow_anonymous true"):
        out.append(f"# {line}   # spostato in conf.d/videocitofono.conf (auth)")
        changed += 1
    else:
        out.append(line)
if changed:
    p.write_text("\n".join(out) + "\n")
print(f"mosquitto.conf: {changed} direttive commentate (listener/allow_anonymous)")
PY
fi

systemctl enable mosquitto.service
systemctl restart mosquitto.service

if ! systemctl is-active --quiet mosquitto.service; then
  echo "ERRORE: mosquitto non e' ripartito. Log:" >&2
  journalctl -u mosquitto -n 15 --no-pager >&2
  exit 1
fi

CFG="${APP_ROOT}/app/config/config.yaml"
if [[ -f "${CFG}" ]]; then
  "${APP_ROOT}/venv/bin/python3" <<PY
import yaml
from pathlib import Path
p = Path("${CFG}")
cfg = yaml.safe_load(p.read_text()) or {}
mqtt = cfg.setdefault("mqtt", {})
mqtt["username"] = "videocitofono"
mqtt["password"] = "${VC_PASS}"
if not mqtt.get("cmd_secret"):
    mqtt["cmd_secret"] = "$(openssl rand -hex 12)"
p.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False))
print("config.yaml mqtt aggiornato (username, password, cmd_secret)")
PY
fi

echo "==> MQTT auth configurato"
echo "    videocitofono / ${VC_PASS}"
echo "    homeassistant / ${HA_PASS}"
echo "    cmd_secret in config.yaml (copiare in HA input_text.videocitofono_cmd_token)"
