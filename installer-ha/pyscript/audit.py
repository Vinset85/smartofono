"""Audit trail HA.

Ascolta:
    videocitofono/health      -> aggiorna sensor.videocitofono_health
    videocitofono/apertura    -> append a input_text.videocitofono_audit
    videocitofono/audit       -> idem (eventi raw dal RPi)
    videocitofono/face/match  -> idem
    videocitofono/face/unknown_freq -> idem (con foto se disponibile)

Stato:
    sensor.videocitofono_audit_last  = ultimo evento (state=kind)
    input_text.videocitofono_audit   = JSON degli ultimi 50 eventi (FIFO)
"""
import json

AUDIT_INPUT = "input_text.videocitofono_audit"
HEALTH_SENSOR = "sensor.videocitofono_health"
LAST_EVT_SENSOR = "sensor.videocitofono_audit_last"

MAX_HISTORY = 50


def _read_history():
    try:
        cur = state.get(AUDIT_INPUT)
        if cur in (None, "unknown", "unavailable", ""):
            return []
        return json.loads(cur)
    except Exception:
        return []


def _push_event(evt: dict):
    """Inserisce evt in cima alla coda e aggiorna sensori."""
    if not isinstance(evt, dict):
        return
    hist = _read_history()
    hist.insert(0, evt)
    hist = hist[:MAX_HISTORY]
    try:
        # input_text ha limite 255 char: troncamento di sicurezza.
        s = json.dumps(hist, ensure_ascii=False)
        if len(s) > 250:
            for n in range(len(hist), 0, -1):
                s2 = json.dumps(hist[:n], ensure_ascii=False)
                if len(s2) <= 250:
                    s = s2
                    break
        state.set(AUDIT_INPUT, s)
    except Exception as e:
        log.warning(f"audit set err: {e}")
    try:
        state.set(LAST_EVT_SENSOR,
                  evt.get("kind", "event"),
                  new_attributes={k: v for k, v in evt.items() if k != "kind"})
    except Exception:
        pass


@mqtt_trigger("videocitofono/audit")
def videocitofono_audit_msg(payload=None, **kw):
    if not payload:
        return
    try:
        evt = json.loads(payload)
        _push_event(evt)
    except Exception as e:
        log.warning(f"audit parse err: {e}")


@mqtt_trigger("videocitofono/apertura")
def videocitofono_apertura_audit(payload=None, **kw):
    if not payload:
        return
    try:
        d = json.loads(payload)
        _push_event({
            "kind": "open",
            "ts": int(d.get("ts") or 0),
            "method": d.get("metodo", "?"),
            "user": d.get("utente", ""),
            "scope": d.get("scope", "porta"),
        })
    except Exception:
        pass


@mqtt_trigger("videocitofono/health")
def videocitofono_health_msg(payload=None, **kw):
    if not payload:
        return
    try:
        d = json.loads(payload)
        attrs = {k: v for k, v in d.items() if k not in ("temp_c",)}
        attrs["temp_c"] = d.get("temp_c")
        summary = d.get("status_summary", "unknown")
        state.set(HEALTH_SENSOR,
                  summary,
                  new_attributes=attrs)
    except Exception as e:
        log.warning(f"health parse err: {e}")
