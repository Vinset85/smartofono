"""Helper payload MQTT videocitofono/cmd con token da secrets.yaml."""

import json
from pathlib import Path

_SECRETS = Path("/config/secrets.yaml")
_SECRET_KEY = "videocitofono_cmd_secret"


def _cmd_token() -> str:
    try:
        for raw in _SECRETS.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith(_SECRET_KEY + ":"):
                continue
            return line.split(":", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    try:
        ent = state.get("input_text.videocitofono_cmd_token")  # noqa: F821
        if ent and ent not in ("unknown", "unavailable", ""):
            return str(ent).strip()
    except Exception:
        pass
    return ""


def cmd_payload(action: str, **kwargs) -> str:
    token = _cmd_token()
    body = {"action": action, **kwargs}
    if token:
        body["token"] = token
    return json.dumps(body, ensure_ascii=False)


@service
def videocitofono_mqtt_cmd(action, **kwargs):
    """Pubblica su videocitofono/cmd con token da secrets.yaml."""
    topic = "videocitofono/cmd"
    payload = cmd_payload(action, **kwargs)
    mqtt.publish(topic=topic, payload=payload, qos=1)
    log.info(f"MQTT cmd {action} -> {topic}")
