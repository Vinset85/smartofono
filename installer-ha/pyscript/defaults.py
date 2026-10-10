"""Ripristina helper HA videocitofono ai valori di default.

Legge /config/videocitofono_defaults.json (generato dal repo, allineato a
config.example.yaml del RPi) e imposta ogni helper prima di applica_config.
"""
import json
from builtins import open

DEFAULTS_PATH = "/config/videocitofono_defaults.json"


def _apply_entity(entity_id: str, value) -> None:
    domain = entity_id.split(".", 1)[0]
    if domain == "input_boolean":
        if value:
            service.call("input_boolean", "turn_on", entity_id=entity_id)
        else:
            service.call("input_boolean", "turn_off", entity_id=entity_id)
    elif domain == "input_number":
        service.call("input_number", "set_value", entity_id=entity_id, value=float(value))
    elif domain == "input_text":
        service.call("input_text", "set_value", entity_id=entity_id, value=str(value))
    elif domain == "input_select":
        service.call("input_select", "select_option", entity_id=entity_id, option=str(value))


@service
def videocitofono_carica_defaults():
    """Imposta tutti gli helper videocitofono ai valori in videocitofono_defaults.json."""
    try:
        with open(DEFAULTS_PATH, encoding="utf-8") as f:
            defaults = json.load(f)
    except Exception as e:
        log.error(f"videocitofono_carica_defaults: impossibile leggere {DEFAULTS_PATH}: {e}")
        return
    ok = 0
    for entity_id, value in defaults.items():
        try:
            _apply_entity(entity_id, value)
            ok += 1
        except Exception as e:
            log.warning(f"videocitofono_carica_defaults: skip {entity_id}: {e}")
    log.info(f"videocitofono_carica_defaults: {ok}/{len(defaults)} helper impostati")
