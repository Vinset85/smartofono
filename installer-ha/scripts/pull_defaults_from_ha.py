#!/usr/bin/env python3
"""Legge helper HA videocitofono e aggiorna config.example.yaml + videocitofono_defaults.json.

Uso (sull'host HA):
  python3 pull_defaults_from_ha.py

Oppure via SSH:
  ssh hassio@192.168.1.160 'python3 -' < pull_defaults_from_ha.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML richiesto", file=sys.stderr)
    sys.exit(1)

RESTORE = Path("/config/.storage/core.restore_state")
OUT_JSON = Path("/config/videocitofono_defaults.json")
# Path repo quando eseguito localmente (override via env)
REPO_EXAMPLE = Path(
    __file__).resolve().parents[2] / "installer-rpi" / "app" / "config" / "config.example.yaml"
REPO_JSON = Path(__file__).resolve().parents[1] / "config" / "videocitofono_defaults.json"


def _states() -> dict[str, str]:
    data = json.loads(RESTORE.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for item in data.get("data", []):
        st = item.get("state", {})
        eid = st.get("entity_id", "")
        if "videocitofono" in eid and eid.startswith(
            ("input_text.", "input_number.", "input_select.", "input_boolean.")
        ):
            out[eid] = str(st.get("state", ""))
    return out


def _bool_on(val: str) -> bool:
    return val == "on"


def _num(val: str, default: float) -> float:
    if val in ("", "unknown", "unavailable"):
        return default
    return float(val)


def build_ha_json(st: dict[str, str]) -> dict:
    def g(key: str, default="") -> str:
        return st.get(key, default)

    return {
        "input_text.videocitofono_indirizzo": g("input_text.videocitofono_indirizzo", "Via Roma 1"),
        "input_text.videocitofono_campanello1_id": g("input_text.videocitofono_campanello1_id"),
        "input_text.videocitofono_campanello1_nome": g("input_text.videocitofono_campanello1_nome"),
        "input_text.videocitofono_campanello2_id": g("input_text.videocitofono_campanello2_id"),
        "input_text.videocitofono_campanello2_nome": g("input_text.videocitofono_campanello2_nome"),
        "input_text.videocitofono_campanello3_id": g("input_text.videocitofono_campanello3_id"),
        "input_text.videocitofono_campanello3_nome": g("input_text.videocitofono_campanello3_nome"),
        "input_text.videocitofono_campanello4_id": g("input_text.videocitofono_campanello4_id", ""),
        "input_text.videocitofono_campanello4_nome": g("input_text.videocitofono_campanello4_nome", ""),
        "input_select.videocitofono_lingua": g("input_select.videocitofono_lingua", "it"),
        "input_select.videocitofono_sfondo": g("input_select.videocitofono_sfondo", "trulli.jpg"),
        "input_select.videocitofono_suoneria": g("input_select.videocitofono_suoneria", "classica"),
        "input_select.videocitofono_campanello1_icona": g("input_select.videocitofono_campanello1_icona"),
        "input_select.videocitofono_campanello2_icona": g("input_select.videocitofono_campanello2_icona"),
        "input_select.videocitofono_campanello3_icona": g("input_select.videocitofono_campanello3_icona"),
        "input_select.videocitofono_campanello4_icona": g("input_select.videocitofono_campanello4_icona", "default"),
        "input_select.videocitofono_metodo_pin_icona": g("input_select.videocitofono_metodo_pin_icona"),
        "input_select.videocitofono_metodo_face_icona": g("input_select.videocitofono_metodo_face_icona"),
        "input_select.videocitofono_metodo_fingerprint_icona": g("input_select.videocitofono_metodo_fingerprint_icona"),
        "input_select.videocitofono_metodo_nfc_icona": g("input_select.videocitofono_metodo_nfc_icona"),
        "input_number.videocitofono_brightness_idle": _num(g("input_number.videocitofono_brightness_idle"), 20),
        "input_number.videocitofono_brightness_active": _num(g("input_number.videocitofono_brightness_active"), 100),
        "input_number.videocitofono_idle_dim_timeout": _num(g("input_number.videocitofono_idle_dim_timeout"), 20),
        "input_number.videocitofono_screensaver_timeout": _num(g("input_number.videocitofono_screensaver_timeout"), 60),
        # Snapshot motion: min 5.0 per evitare falsi positivi JPEG (standby).
        "input_number.videocitofono_motion_sensitivity": max(
            _num(g("input_number.videocitofono_motion_sensitivity"), 5.0), 5.0
        ),
        "input_number.videocitofono_volume_speaker": _num(g("input_number.videocitofono_volume_speaker"), 85),
        "input_number.videocitofono_volume_microfono": _num(g("input_number.videocitofono_volume_microfono"), 140),
        "input_number.videocitofono_volume_feedback": _num(g("input_number.videocitofono_volume_feedback"), 30),
        "input_number.videocitofono_volume_tts": _num(g("input_number.videocitofono_volume_tts"), 85),
        "input_boolean.videocitofono_motion_enabled": _bool_on(g("input_boolean.videocitofono_motion_enabled", "on")),
        "input_boolean.videocitofono_face_enabled": _bool_on(g("input_boolean.videocitofono_face_enabled", "on")),
        "input_boolean.videocitofono_finger_enabled": _bool_on(g("input_boolean.videocitofono_finger_enabled", "off")),
        "input_boolean.videocitofono_pin_enabled": _bool_on(g("input_boolean.videocitofono_pin_enabled", "on")),
        "input_boolean.videocitofono_nfc_enabled": _bool_on(g("input_boolean.videocitofono_nfc_enabled", "on")),
        "input_boolean.videocitofono_dnd": _bool_on(g("input_boolean.videocitofono_dnd", "off")),
        "input_boolean.videocitofono_audio_locale_enabled": _bool_on(
            g("input_boolean.videocitofono_audio_locale_enabled", "on")
        ),
        "input_boolean.videocitofono_auto_recognize": _bool_on(
            g("input_boolean.videocitofono_auto_recognize", "off")
        ),
        "input_boolean.videocitofono_liveness": _bool_on(g("input_boolean.videocitofono_liveness", "on")),
    }


def patch_example(cfg: dict, ha: dict) -> dict:
    cfg.setdefault("ui", {})
    cfg["ui"]["indirizzo"] = ha["input_text.videocitofono_indirizzo"]
    cfg["ui"]["language"] = ha["input_select.videocitofono_lingua"]
    cfg["ui"]["sfondo"] = ha["input_select.videocitofono_sfondo"]
    cfg["ui"]["dnd"] = ha["input_boolean.videocitofono_dnd"]
    cfg["ui"]["brightness_idle_pct"] = int(ha["input_number.videocitofono_brightness_idle"])
    cfg["ui"]["brightness_active_pct"] = int(ha["input_number.videocitofono_brightness_active"])
    cfg["ui"]["idle_dim_sec"] = int(ha["input_number.videocitofono_idle_dim_timeout"])
    cfg["ui"]["screensaver_timeout_sec"] = int(ha["input_number.videocitofono_screensaver_timeout"])
    cfg["ui"]["feedback_volume"] = round(ha["input_number.videocitofono_volume_feedback"] / 100.0, 2)

    campanelli = []
    for n in (1, 2, 3, 4):
        cid = ha[f"input_text.videocitofono_campanello{n}_id"]
        if not cid:
            continue
        icon = ha[f"input_select.videocitofono_campanello{n}_icona"]
        if icon in ("default", ""):
            icon = ""
        campanelli.append({
            "id": cid,
            "nome": ha[f"input_text.videocitofono_campanello{n}_nome"] or cid,
            "icona": icon,
        })
    cfg["campanelli"] = campanelli

    cfg.setdefault("access_icons", {})
    cfg["access_icons"]["pin"] = ha["input_select.videocitofono_metodo_pin_icona"]
    cfg["access_icons"]["face"] = ha["input_select.videocitofono_metodo_face_icona"]
    cfg["access_icons"]["fingerprint"] = ha["input_select.videocitofono_metodo_fingerprint_icona"]
    cfg["access_icons"]["nfc"] = ha["input_select.videocitofono_metodo_nfc_icona"]

    cfg.setdefault("motion", {})
    cfg["motion"]["enabled"] = ha["input_boolean.videocitofono_motion_enabled"]
    cfg["motion"]["area_thresh_pct"] = ha["input_number.videocitofono_motion_sensitivity"]

    cfg.setdefault("pin", {})
    cfg["pin"]["enabled"] = ha["input_boolean.videocitofono_pin_enabled"]

    cfg.setdefault("face_recognition", {})
    cfg["face_recognition"]["enabled"] = ha["input_boolean.videocitofono_face_enabled"]
    cfg["face_recognition"]["liveness_enabled"] = ha["input_boolean.videocitofono_liveness"]
    cfg["face_recognition"].setdefault("auto_recognize", {})
    cfg["face_recognition"]["auto_recognize"]["enabled"] = ha["input_boolean.videocitofono_auto_recognize"]

    cfg.setdefault("fingerprint", {})
    cfg["fingerprint"]["enabled"] = ha["input_boolean.videocitofono_finger_enabled"]

    cfg.setdefault("nfc", {})
    cfg["nfc"]["enabled"] = ha["input_boolean.videocitofono_nfc_enabled"]

    cfg.setdefault("audio", {})
    cfg["audio"]["enabled"] = ha["input_boolean.videocitofono_audio_locale_enabled"]
    cfg["audio"]["volume_speaker_pct"] = int(ha["input_number.videocitofono_volume_speaker"])
    cfg["audio"]["volume_mic_pct"] = int(ha["input_number.videocitofono_volume_microfono"])
    cfg["audio"]["suoneria"] = ha["input_select.videocitofono_suoneria"]

    cfg.setdefault("tts", {})
    cfg["tts"]["volume"] = round(ha["input_number.videocitofono_volume_tts"] / 100.0, 2)

    return cfg


def main() -> int:
    st = _states()
    ha = build_ha_json(st)

    # Il volume della voce serve per il config del RPi ma non va fra i default
    # ripristinati da `carica_defaults` all'avvio: lo decide la fascia oraria
    # (pyscript/voce_notturna.py), e un valore fisso qui lo sovrascriverebbe a
    # ogni riavvio di HA.
    defaults = {k: v for k, v in ha.items()
                if k != "input_number.videocitofono_volume_tts"}

    if REPO_JSON.parent.exists():
        REPO_JSON.write_text(json.dumps(defaults, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Scritto {REPO_JSON}")

    if OUT_JSON.parent.exists():
        OUT_JSON.write_text(json.dumps(defaults, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Scritto {OUT_JSON}")

    if REPO_EXAMPLE.is_file():
        cfg = yaml.safe_load(REPO_EXAMPLE.read_text(encoding="utf-8")) or {}
        cfg = patch_example(cfg, ha)
        REPO_EXAMPLE.write_text(
            yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        print(f"Aggiornato {REPO_EXAMPLE}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
