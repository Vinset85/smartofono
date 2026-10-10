#!/usr/bin/env bash
# Copia config.yaml dal Pi in config.example.yaml (merge con override).
set -euo pipefail

HOST="${1:-192.168.1.185}"
USER="${DEPLOY_USER:-vinset}"
KEY="${SSH_KEY:-$HOME/.ssh/id_videocitofono}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SSH=(ssh -i "$KEY" -o BatchMode=yes "${USER}@${HOST}")
PY=/opt/videocitofono/venv/bin/python3

"${SSH[@]}" "sudo ${PY} - <<'PY'
import yaml
from pathlib import Path

def load(p):
    if not Path(p).is_file():
        return {}
    with open(p, encoding=\"utf-8\") as f:
        return yaml.safe_load(f) or {}

def merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out

base = load(\"/opt/videocitofono/app/config/config.yaml\")
ov = load(\"/opt/videocitofono/app/config/config.override.yaml\")
full = merge(base, ov)
keys = (\"campanelli\", \"ui\", \"access_icons\", \"motion\", \"pin\",
        \"face_recognition\", \"fingerprint\", \"nfc\", \"audio\", \"tts\")
patch = {k: full[k] for k in keys if k in full}
example = load(\"/opt/videocitofono/app/config/config.example.yaml\")
for k, v in patch.items():
    example[k] = v
out = Path(\"/tmp/vc_config_example_export.yaml\")
with open(out, \"w\", encoding=\"utf-8\") as f:
    yaml.safe_dump(example, f, allow_unicode=True, sort_keys=False)
print(out)
PY"

scp -i "$KEY" -o BatchMode=yes "${USER}@${HOST}:/tmp/vc_config_example_export.yaml" \
  "$REPO/app/config/config.example.yaml"
echo "Aggiornato $REPO/app/config/config.example.yaml"
