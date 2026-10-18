"""Helper payload MQTT videocitofono/cmd con token da secrets.yaml."""

import json
from pathlib import Path

_SECRETS = Path("/config/secrets.yaml")
_SECRET_KEY = "videocitofono_cmd_secret"
TOPIC_CMD = "videocitofono/cmd"


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


def _coerce_kwargs(kwargs: dict) -> dict:
    out = dict(kwargs)
    cfg = out.get("config")
    if isinstance(cfg, str):
        try:
            out["config"] = json.loads(cfg)
        except Exception:
            pass
    return out


@service
def videocitofono_mqtt_cmd(action, **kwargs):
    """Pubblica su videocitofono/cmd con token da secrets.yaml (mai retain)."""
    payload = cmd_payload(action, **_coerce_kwargs(kwargs))
    mqtt.publish(topic=TOPIC_CMD, payload=payload, qos=1, retain=False)
    log.info(f"MQTT cmd {action} -> {TOPIC_CMD}")


@time_trigger("startup")
def _purge_cmd_retain():
    """Svuota un eventuale retain vecchio su videocitofono/cmd."""
    mqtt.publish(topic=TOPIC_CMD, payload="", qos=1, retain=True)
    log.info("MQTT cmd retain azzerato")
