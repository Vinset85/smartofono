"""Helper payload MQTT videocitofono/cmd con token auth."""

import json


def cmd_payload(action: str, **kwargs) -> str:
    token = ""
    try:
        ent = state.get("input_text.videocitofono_cmd_token")  # noqa: F821
        if ent and ent not in ("unknown", "unavailable", ""):
            token = str(ent).strip()
    except Exception:
        pass
    body = {"action": action, **kwargs}
    if token:
        body["token"] = token
    return json.dumps(body, ensure_ascii=False)


@service
def videocitofono_mqtt_cmd(action, **kwargs):
    """Pubblica su videocitofono/cmd con token da input_text."""
    topic = "videocitofono/cmd"
    payload = cmd_payload(action, **kwargs)
    mqtt.publish(topic=topic, payload=payload, qos=1)
    log.info(f"MQTT cmd {action} -> {topic}")
