"""Gestione tag NFC del videocitofono.

Espone i seguenti service:
- pyscript.videocitofono_nfc_enroll: avvia iscrizione del prossimo tag
  rilevato per la persona indicata.
- pyscript.videocitofono_nfc_delete: rimuove un tag (per uid) o tutti i
  tag di un utente (per nome).
- pyscript.videocitofono_nfc_refresh: chiede al RPi di ripubblicare la
  lista tag su videocitofono/nfc/library (retain).

Comunicazione: la libreria UID->utente vive sul RPi
(/opt/videocitofono/data/nfc_tags.json). HA invia comandi via
videocitofono/cmd e legge lo stato via topic retain
videocitofono/nfc/library.
"""
import re

TOPIC_CMD = "videocitofono/cmd"


def _sanitize_name(nome):
    if not nome:
        return ""
    s = str(nome).strip().replace(" ", "_")
    s = re.sub(r"[^A-Za-z0-9_\-]", "", s)
    return s[:64]


def _sanitize_uid(uid):
    if not uid:
        return ""
    s = re.sub(r"[^a-fA-F0-9]", "", str(uid))
    return s.lower()


def _norm_scope(scope):
    s = (scope or "porta").strip().lower()
    return s if s in ("porta", "cancello") else "porta"


@service
def videocitofono_nfc_enroll(nome=None, scope=None, label=None,
                             timeout_sec=None):
    """Avvia iscrizione del prossimo tag rilevato.
    - nome:        utente da associare (richiesto)
    - scope:       'porta' (default) o 'cancello'
    - label:       etichetta libera (es. 'Portachiavi rosso')
    - timeout_sec: timeout finestra di iscrizione (default 30s)
    """
    nome_safe = _sanitize_name(nome)
    if not nome_safe:
        log.warning(f"nfc_enroll: nome non valido ({nome!r})")
        return
    try:
        timeout_val = float(timeout_sec) if timeout_sec else 30.0
    except Exception:
        timeout_val = 30.0
    payload = {
        "action": "nfc_enroll",
        "nome": nome_safe,
        "scope": _norm_scope(scope),
        "label": (label or "").strip()[:64],
        "timeout_sec": max(5.0, min(120.0, timeout_val)),
    }
    try:
        videocitofono_mqtt_cmd(**payload)
        log.info(f"nfc_enroll richiesto: {nome_safe} "
                 f"({payload['scope']}, t={payload['timeout_sec']}s)")
    except Exception as e:
        log.error(f"nfc_enroll MQTT publish fallito: {e}")


@service
def videocitofono_nfc_delete(uid=None, nome=None):
    """Rimuove un tag (per uid esadecimale) oppure tutti i tag di un
    utente (per nome). Almeno uno tra `uid` e `nome` e' richiesto."""
    uid_safe = _sanitize_uid(uid)
    nome_safe = _sanitize_name(nome)
    if not uid_safe and not nome_safe:
        log.warning("nfc_delete: serve uid o nome")
        return
    payload = {"action": "nfc_delete"}
    if uid_safe:
        payload["uid"] = uid_safe
    if nome_safe:
        payload["nome"] = nome_safe
    try:
        videocitofono_mqtt_cmd(**payload)
        log.info(f"nfc_delete richiesto: uid={uid_safe!r} "
                 f"nome={nome_safe!r}")
    except Exception as e:
        log.error(f"nfc_delete MQTT publish fallito: {e}")


@service
def videocitofono_nfc_refresh():
    """Forza il RPi a ripubblicare la lista tag NFC."""
    try:
        videocitofono_mqtt_cmd(action="nfc_list")
    except Exception as e:
        log.error(f"nfc_refresh MQTT publish fallito: {e}")
