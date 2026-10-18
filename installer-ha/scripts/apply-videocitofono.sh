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
  pyscript/icone.py \
  pyscript/sfondi.py \
  pyscript/nfc.py \
  pyscript/volti.py \
  pyscript/guest_pin.py \
  packages/scripts.yaml.fixed \
  packages/automations.yaml.fixed \
  www/vc-livekit-preview.js \
  www/vc-livekit-call.js \
  www/vc-livekit.js \
  www/vc-ring-visitor.js \
  lovelace/videocitofono-health.json \
| ssh_ha 'cat > /tmp/vc_apply.tar'

ssh_ha 'sudo python3 -' <<'PY'
from pathlib import Path
import tarfile, datetime, shutil, json, urllib.request, os

ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
tf = tarfile.open("/tmp/vc_apply.tar")
need_ha_restart = False

def extract(member, dest):
    src = tf.extractfile(member)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read())
    print("wrote", dest)

extract("pyscript/mqtt_cmd.py", Path("/config/pyscript/mqtt_cmd.py"))
extract("pyscript/update_registro_videocitofono.py", Path("/config/pyscript/update_registro_videocitofono.py"))
extract("pyscript/icone.py", Path("/config/pyscript/icone.py"))
extract("pyscript/sfondi.py", Path("/config/pyscript/sfondi.py"))
extract("pyscript/nfc.py", Path("/config/pyscript/nfc.py"))
extract("pyscript/volti.py", Path("/config/pyscript/volti.py"))
extract("pyscript/guest_pin.py", Path("/config/pyscript/guest_pin.py"))
extract("packages/scripts.yaml.fixed", Path("/config/scripts.yaml"))
auto_src = tf.extractfile("packages/automations.yaml.fixed").read().decode()
auto_dst = Path("/config/automations.yaml")


def _auto_block(src, aid):
    marker = "- id: '%s'" % aid
    i = src.find(marker)
    if i < 0:
        return ""
    j = src.find("\n- id:", i + len(marker))
    chunk = src[i:j] if j >= 0 else src[i:]
    return chunk.rstrip() + "\n"


if auto_dst.exists():
    live = auto_dst.read_text()
    orig = live
    if "pyscript.videocitofono_mqtt_cmd" not in live and "videocitofono/cmd" in live and "campanelli" in live:
        live = live.replace(
            "  - action: mqtt.publish\n    data:\n      topic: videocitofono/cmd\n      qos: 1\n      retain: false\n      payload: >-\n        {\"action\":\"set_config\",\"persist_default\":true,\"config\":{\"campanelli\": {{ campanelli | tojson }} }}",
            "  - action: pyscript.videocitofono_mqtt_cmd\n    data:\n      action: set_config\n      persist_default: true\n      config: '{\"campanelli\": {{ campanelli | tojson }}}'",
            1,
        )
    def _replace_or_append(live_txt, aid):
        blk = _auto_block(auto_src, aid)
        if not blk:
            return live_txt
        for marker in ("- id: '%s'" % aid, '- id: "%s"' % aid):
            i = live_txt.find(marker)
            if i >= 0:
                j = live_txt.find("\n- id:", i + len(marker))
                return live_txt[:i] + blk + (live_txt[j + 1:] if j >= 0 else "")
        return live_txt.rstrip() + "\n" + blk

    for aid in ("1761000000023", "1761000000026", "1761000000027",
                "1761000000028", "1761000000029",
                "1761000000031", "1761000000032"):
        live = _replace_or_append(live, aid)
    import re as _re
    live = _re.sub(
        r"^  alias: Videocitofono[^\n]*(?:finger|impronta)[^\n]*$",
        "  alias: Videocitofono - Apertura via MQTT",
        live,
        flags=_re.I | _re.M,
    )
    blk5 = _auto_block(auto_src, "1761000000005")
    if blk5:
        marker = "- id: '1761000000005'"
        i = live.find(marker)
        if i >= 0:
            j = live.find("\n- id:", i + len(marker))
            live = live[:i] + blk5 + (live[j+1:] if j >= 0 else "")
    if live != orig:
        shutil.copy2(auto_dst, Path(str(auto_dst) + ".bak-apply-" + ts))
        auto_dst.write_text(live)
        print("automations_patched")
for name in (
    "vc-livekit-preview.js", "vc-livekit-call.js",
    "vc-livekit.js", "vc-ring-visitor.js",
):
    extract("www/" + name, Path("/config/www") / name)
res = Path("/config/.storage/lovelace_resources")
if res.exists():
    try:
        data = json.loads(res.read_text())
        items = (data.get("data") or {}).get("items") or []
        changed = False
        for item in items:
            url = str(item.get("url") or "")
            if "vc-livekit-call.js" in url:
                item["url"] = "/local/vc-livekit-call.js?v=" + ts
                changed = True
        if changed:
            res.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            print("lovelace_call_js_bust")
    except Exception as e:
        print("lovelace_bust_err", type(e).__name__)

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
def drop_yaml_key(src, key):
    needle = "  %s:" % key
    lines = src.splitlines(keepends=True)
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith(needle):
            i += 1
            while i < len(lines) and (
                lines[i].startswith("    ") or lines[i].startswith("  -")
            ):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)

if "videocitofono_finger_enabled" in text or "videocitofono_metodo_fingerprint_icona" in text:
    need_ha_restart = True
text = drop_yaml_key(text, "videocitofono_finger_enabled")
text = drop_yaml_key(text, "videocitofono_metodo_fingerprint_icona")
cfg.write_text(text)
print("cfg_ok")

def strip_finger(obj):
    def is_finger_leaf(o):
        if not isinstance(o, dict):
            return False
        if any(k in o for k in ("cards", "sections", "views", "config", "data", "version")):
            return False
        eid = str(o.get("entity") or "")
        if "finger_enabled" in eid or "metodo_fingerprint" in eid:
            return True
        blob = " ".join(str(o.get(k) or "") for k in ("name", "title", "content", "icon", "label")).lower()
        return "impronta" in blob or "mdi:fingerprint" in blob
    if isinstance(obj, dict):
        if is_finger_leaf(obj):
            return None
        out = {}
        for k, v in obj.items():
            if k in ("cards", "sections", "views", "entities", "targets") and isinstance(v, list):
                out[k] = [x for x in (strip_finger(i) for i in v) if x is not None]
            else:
                nv = strip_finger(v)
                if nv is None and k in ("data", "config", "views"):
                    raise RuntimeError("strip_finger refused to drop " + k)
                if nv is not None:
                    out[k] = nv
        title = str(out.get("title", ""))
        if "impronta" in title.lower():
            out["title"] = title.replace("PIN, volto, impronta, RFID", "PIN, volto, RFID")
        return out
    if isinstance(obj, list):
        return [x for x in (strip_finger(i) for i in obj) if x is not None]
    return obj

health_card = None
try:
    health_card = json.loads(tf.extractfile("lovelace/videocitofono-health.json").read().decode())
except Exception as e:
    print("health_json_err", type(e).__name__)

lov = Path("/config/.storage/lovelace.lovelace")
if lov.exists():
    try:
        raw = lov.read_text().strip()
        if raw in ("", "null", "None"):
            print("lovelace_live_empty_skip")
        else:
            data = json.loads(raw)
            stripped = strip_finger(data)
            cfg = ((stripped or {}).get("data") or {}).get("config") or {}
            views = cfg.get("views") if isinstance(cfg, dict) else None
            if not views:
                print("lovelace_strip_refused")
            else:
                changed = json.dumps(stripped) != json.dumps(data)
                if health_card:
                    view = {
                        "title": "Salute Videocitofono",
                        "path": "videocitofono-salute",
                        "icon": "mdi:heart-pulse",
                        "cards": [health_card],
                    }
                    found = False
                    for i, v in enumerate(views):
                        if not isinstance(v, dict):
                            continue
                        if v.get("path") == "videocitofono-salute" or v.get("title") == "Salute Videocitofono":
                            views[i] = view
                            found = True
                            break
                    if not found:
                        views.append(view)
                    cfg["views"] = views
                    stripped.setdefault("data", {})["config"] = cfg
                    changed = True
                    print("lovelace_health_upsert")
                if changed:
                    shutil.copy2(lov, Path(str(lov) + ".bak-apply-" + ts))
                    lov.write_text(json.dumps(stripped, ensure_ascii=False, separators=(",", ":")) + "\n")
                    need_ha_restart = True
                    print("lovelace_updated")
    except Exception as e:
        print("lovelace_finger_err", type(e).__name__)

er = Path("/config/.storage/core.entity_registry")
if er.exists():
    try:
        data = json.loads(er.read_text())
        ents = ((data.get("data") or {}).get("entities")) or []
        taken = {e.get("entity_id") for e in ents if isinstance(e, dict)}
        by_uid = {
            "1761000000004": "automation.videocitofono_timeout_chiamata",
            "1761000000007": "automation.videocitofono_refresh_icone_periodico",
            "1761000000010": "automation.videocitofono_pulsante_applica_configurazione",
        }
        by_old = {
            "automation.videocitofono_apertura_via_mqtt_pin_face_nfc_finger":
                "automation.videocitofono_pulsante_applica_configurazione",
            "automation.videocitofono_refresh_sfondi_a_ha_start":
                "automation.videocitofono_timeout_chiamata",
            "automation.videocitofono_refresh_icone_a_ha_start":
                "automation.videocitofono_refresh_icone_periodico",
        }
        renamed = 0
        for e in ents:
            if not isinstance(e, dict):
                continue
            uid = str(e.get("unique_id") or "")
            eid = str(e.get("entity_id") or "")
            new = by_uid.get(uid) or by_old.get(eid)
            if not new or eid == new:
                continue
            if new in taken:
                print("eid_skip_taken", eid, new)
                continue
            taken.discard(eid)
            taken.add(new)
            e["entity_id"] = new
            renamed += 1
            print("eid_renamed", eid, "->", new)
        if renamed:
            shutil.copy2(er, Path(str(er) + ".bak-apply-" + ts))
            er.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            need_ha_restart = True
            print("entity_registry_renamed", renamed)
    except Exception as e:
        print("entity_registry_err", type(e).__name__)

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

svcs = [
    "/services/script/reload",
    "/services/mqtt/reload",
    "/services/pyscript/reload",
    "/services/automation/reload",
]
if need_ha_restart:
    svcs.append("/services/homeassistant/restart")
for svc in svcs:
    try:
        api(svc)
    except Exception as e:
        print("reload_err", svc, type(e).__name__)
os.remove("/tmp/vc_apply.tar")
PY

echo "==> apply completato"
