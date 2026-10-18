"""Servizi pyscript per gestire i PIN ospite del videocitofono.

Espongono:
    pyscript.videocitofono_create_guest_pin(label, valid_hours, max_uses, scope)
    pyscript.videocitofono_revoke_guest_pin(id)
    pyscript.videocitofono_list_guest_pins()

Comunicano con il RPi via MQTT (videocitofono/guest_pins/cmd) e
ricevono la lista corrente su `videocitofono/guest_pins/list` (retain).
La lista viene esposta come `sensor.videocitofono_guest_pins` con
`attributes.items` contenente l'array.
"""
import json

LIST_SENSOR = "sensor.videocitofono_guest_pins"
CMD_TOPIC = "videocitofono/cmd"


@service
def videocitofono_create_guest_pin(label="", valid_hours=24,
                                    max_uses=1, scope="porta"):
    """Crea un PIN ospite. Il PIN generato viene esposto come
    persistent_notification sulla dashboard (titolo: "PIN ospite")."""
    pyscript.videocitofono_mqtt_cmd(
        action="guest_pin_create",
        label=str(label or ""),
        valid_hours=float(valid_hours or 24),
        max_uses=int(max_uses or 1),
        scope=str(scope or "porta"),
    )


@service
def videocitofono_revoke_guest_pin(id_=""):
    if not id_:
        return
    pyscript.videocitofono_mqtt_cmd(action="guest_pin_revoke", id=str(id_))


@service
def videocitofono_list_guest_pins():
    pyscript.videocitofono_mqtt_cmd(action="guest_pin_list")


@mqtt_trigger("videocitofono/guest_pins/created")
def videocitofono_guest_pin_created(payload=None, **kw):
    if not payload:
        return
    try:
        d = json.loads(payload)
        msg = (f"PIN ospite generato: **{d.get('pin','?')}**\n\n"
               f"Etichetta: {d.get('label','-')}\n"
               f"Scade: {d.get('expires_human','-')}\n"
               f"Max usi: {d.get('max_uses', '?')}")
        service.call("persistent_notification", "create",
                     blocking=False,
                     title="PIN ospite",
                     message=msg,
                     notification_id=f"guest_pin_{d.get('id','x')}")
    except Exception as e:
        log.warning(f"guest pin created err: {e}")


@mqtt_trigger("videocitofono/guest_pins/list")
def videocitofono_guest_pin_list_msg(payload=None, **kw):
    if not payload:
        return
    try:
        d = json.loads(payload)
        items = d.get("items", [])
        state.set(LIST_SENSOR, len(items),
                  new_attributes={"items": items, "friendly_name": "PIN ospite"})
    except Exception as e:
        log.warning(f"guest pin list err: {e}")
