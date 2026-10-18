"""Controlli statici + logica dei template MQTT/notify (stdlib only)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages"
CFG = (PKG / "configuration.yaml.fixed").read_text()
AUTO = (PKG / "automations.yaml.fixed").read_text()


def test_guest_pins_usa_get_items_non_metodo():
    assert "value_json.get('items'" in CFG
    assert "value_json.items |" not in CFG


def test_chiamata_stato_con_guard_mapping():
    assert "value_json.stato if value_json is mapping else value" in AUTO


def test_registra_risposta_tollerante_non_json():
    assert "trigger.payload_json.stato if trigger.payload_json is mapping else trigger.payload" in AUTO


def _stato(value_json, value):
    raw = value_json.get("stato") if isinstance(value_json, dict) else value
    if raw in (None, ""):
        raw = value
    return str(raw).strip()


def test_logica_stato_json_e_stringa():
    assert _stato({"stato": "chiamata_in_corso"}, "x") == "chiamata_in_corso"
    assert _stato(None, "annullata") == "annullata"
    assert _stato("nope", "risposto_audio") == "risposto_audio"


def test_notify_group_e_url_relativo():
    assert "name: videocitofono" in CFG
    assert "service: mobile_app_vinset_iphone" in CFG
    assert "service: mobile_app_vinset_iphone_vecchio" in CFG
    assert "service: mobile_app_iphone_stefania" in CFG
    assert "action: notify.videocitofono" in AUTO
    assert "tag: videocitofono_chiamata" in AUTO
    assert "url: '{{ nav_path }}'" in AUTO
    assert "casa-esempio.duckdns.org" not in AUTO.split("Videocitofono - Notifica mobile chiamata", 1)[-1][:2500]


def test_clear_notification_su_fine_chiamata():
    assert "message: clear_notification" in AUTO
    chunk = AUTO.split("Videocitofono - Stop suoneria su fine chiamata", 1)[1][:1800]
    assert "clear_notification" in chunk
    assert "tag: videocitofono_chiamata" in chunk


def test_mqtt_unique_id_su_tutti_i_sensori():
    for uid in (
        "vc_online",
        "vc_stato_chiamata",
        "vc_stato_chiamata_raw",
        "vc_ultimo_campanello",
        "vc_volti",
        "vc_nfc",
        "vc_evento",
        "vc_health",
        "vc_nfc_reader",
        "vc_anomaly",
        "vc_guest_pins",
        "vc_registro",
    ):
        assert f"unique_id: {uid}" in CFG


def test_cmd_mqtt_non_espone_helper_negli_script():
    scripts = (PKG / "scripts.yaml.fixed").read_text()
    assert "states('input_text.videocitofono_cmd_token')" not in scripts
    assert "action: pyscript.videocitofono_mqtt_cmd" in scripts
    mqtt_cmd = (ROOT / "pyscript" / "mqtt_cmd.py").read_text()
    assert "videocitofono_cmd_secret" in mqtt_cmd
    assert "_purge_cmd_retain" in mqtt_cmd
    assert 'payload=""' in mqtt_cmd.replace(" ", "") or 'payload=""' in mqtt_cmd
    assert "retain=True" in mqtt_cmd
    icone = (ROOT / "pyscript" / "icone.py").read_text()
    assert "videocitofono_mqtt_cmd" in icone
    assert AUTO.count("pyscript.videocitofono_mqtt_cmd") >= 1
    assert "Videocitofono - Alert NFC non in ascolto" in AUTO
    assert "notification_id: videocitofono_nfc_down" in AUTO
    assert "Videocitofono - NFC ascolto ripristinato" in AUTO
    assert "- id: '1761000000026'" in AUTO
    assert "- id: '1761000000027'" in AUTO
    assert AUTO.count("- id: '1761000000024'") == 1


def test_fingerprint_rimosso():
    assert "videocitofono_finger_enabled" not in CFG
    assert "videocitofono_metodo_fingerprint_icona" not in CFG
    assert "videocitofono_finger_enabled" not in AUTO
    scripts = (PKG / "scripts.yaml.fixed").read_text()
    assert "fingerprint" not in scripts
    assert "finger_enabled" not in scripts
    icone = (ROOT / "pyscript" / "icone.py").read_text()
    assert "metodo_fingerprint_icona" not in icone
    lov = (ROOT / "lovelace" / "lovelace.lovelace.fixed").read_text()
    data = json.loads(lov)
    views = ((data.get("data") or {}).get("config") or {}).get("views") or []
    assert len(views) >= 1
    assert "finger_enabled" not in lov
    assert "metodo_fingerprint_icona" not in lov
    assert "Iscrivi nuova impronta" not in lov


def test_call_card_usa_icone_mdi():
    js = (ROOT / "www" / "vc-livekit-call.js").read_text()
    assert "mdi:door-open" in js
    assert "mdi:phone-hangup" in js
    assert "mdi:microphone" in js
    assert "mdi:video" in js
    assert "mdi:phone-ring" in js
    assert "🎙" not in js
    assert "🔓" not in js


def test_quota_video_e_purge_avvio():
    reg = (ROOT / "pyscript" / "update_registro_videocitofono.py").read_text()
    assert "VIDEO_MAX_BYTES" in reg
    assert "VIDEO_MAX_FILES" in reg
    assert "def _enforce_video_quota" in reg
    assert '@time_trigger("startup")' in reg


def test_livekit_turn_relay_porte_basse():
    lk = (ROOT / "livekit" / "livekit.yaml").read_text()
    assert "relay_range_start: 8102" in lk
    assert "relay_range_end: 8106" in lk
    assert "udp_port: 3478" in lk
