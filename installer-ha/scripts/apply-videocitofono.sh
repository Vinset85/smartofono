#!/usr/bin/env bash
# Applica SOLO i pezzi videocitofono su HA (pyscript, www, scripts, unique_id).
# Non sovrascrive intero configuration.yaml.
#
#   HA_PASS='...' ./scripts/apply-videocitofono.sh
#   HA_PASS_FILE=/tmp/vc_ha_pw ./scripts/apply-videocitofono.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HA_HOST="${HA_HOST:-192.168.1.160}"
HA_USER="${HA_USER:-hassio}"
if [ -z "${HA_PASS:-}" ] && [ -n "${HA_PASS_FILE:-}" ] && [ -f "$HA_PASS_FILE" ]; then
    HA_PASS="$(cat "$HA_PASS_FILE")"
fi
HA_PASS="${HA_PASS:-}"
HA_SSH="${HA_USER}@${HA_HOST}"

ssh_ha() {
  if [ -n "$HA_PASS" ] && command -v sshpass >/dev/null 2>&1; then
    sshpass -p "$HA_PASS" ssh -o StrictHostKeyChecking=no "${HA_SSH}" "$@"
  else
    ssh -o StrictHostKeyChecking=no "${HA_SSH}" "$@"
  fi
}

echo "==> apply videocitofono -> ${HA_SSH}"
COPYFILE_DISABLE=1 tar -C "$ROOT" --exclude='._*' -cf - \
  pyscript/mqtt_cmd.py \
  pyscript/update_registro_videocitofono.py \
  packages/scripts.yaml.fixed \
  www/vc-livekit-preview.js \
  www/vc-livekit-call.js \
  www/vc-livekit.js \
  www/vc-ring-visitor.js \
| ssh_ha 'cat > /tmp/vc_apply.tar'

ssh_ha 'sudo python3 -' <<'PY'
from pathlib import Path
import tarfile, datetime, shutil, json, urllib.request, os

ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
tf = tarfile.open("/tmp/vc_apply.tar")

def extract(member, dest):
    src = tf.extractfile(member)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read())
    print("wrote", dest)

extract("pyscript/mqtt_cmd.py", Path("/config/pyscript/mqtt_cmd.py"))
extract("pyscript/update_registro_videocitofono.py", Path("/config/pyscript/update_registro_videocitofono.py"))
extract("packages/scripts.yaml.fixed", Path("/config/scripts.yaml"))
for name in (
    "vc-livekit-preview.js", "vc-livekit-call.js",
    "vc-livekit.js", "vc-ring-visitor.js",
):
    extract("www/" + name, Path("/config/www") / name)

cfg = Path("/config/configuration.yaml")
shutil.copy2(cfg, Path(str(cfg) + ".bak-apply-" + ts))
need = [
    ('name: "Videocitofono Ultimo Campanello"', "      unique_id: vc_ultimo_campanello\n"),
    ('name: "Videocitofono Volti"', "      unique_id: vc_volti\n"),
    ('name: "Videocitofono NFC"', "      unique_id: vc_nfc\n"),
    ('name: "Videocitofono Evento"', "      unique_id: vc_evento\n"),
    ('name: "Videocitofono Health"', "      unique_id: vc_health\n"),
    ('name: "Videocitofono NFC Reader"', "      unique_id: vc_nfc_reader\n"),
    ('name: "Videocitofono Anomalia"', "      unique_id: vc_anomaly\n"),
    ('name: "Videocitofono Guest PINs"', "      unique_id: vc_guest_pins\n"),
]
lines = cfg.read_text().splitlines(keepends=True)
out, i = [], 0
while i < len(lines):
    ln = lines[i]
    out.append(ln)
    for needle, uid in need:
        if needle in ln:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if "unique_id:" not in nxt:
                out.append(uid)
            break
    i += 1
text = "".join(out)
if "unique_id: vc_registro" not in text and "name: Registro Videocitofono" in text:
    text = text.replace(
        "name: Registro Videocitofono\n",
        "name: Registro Videocitofono\n      unique_id: vc_registro\n",
        1,
    )
cfg.write_text(text)
print("cfg_ok")

tok_path = Path("/run/s6/container_environment/SUPERVISOR_TOKEN")
tok = tok_path.read_text().strip() if tok_path.exists() else ""

def api(path, method="POST", body=None):
    if not tok:
        print("skip", path)
        return
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        "http://supervisor/core/api" + path,
        data=data,
        headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(path, resp.status)

for svc in ("/services/script/reload", "/services/mqtt/reload", "/services/pyscript/reload"):
    try:
        api(svc)
    except Exception as e:
        print("reload_err", svc, type(e).__name__)
os.remove("/tmp/vc_apply.tar")
PY

echo "==> apply completato"
