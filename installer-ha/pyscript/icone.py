"""Gestione libreria icone (avatar) campanelli videocitofono.

Espone 3 service (analoghi a quelli sfondi):
- pyscript.videocitofono_refresh_icone: scansiona /config/www/vc-icone/ e
  popola le opzioni dei 4 input_select.videocitofono_campanelloN_icona.
- pyscript.videocitofono_upload_icona: salva un file (passato come base64)
  in /config/www/vc-icone/, sanitizza il nome, refresh + notifica RPi.
- pyscript.videocitofono_delete_icona: elimina un file dalla libreria,
  refresh + (se era selezionato in qualche campanello) reset a 'default'
  + notifica RPi.

I file sono accessibili via HTTP HA come /local/vc-icone/<nome>, cosi' il
RPi puo' scaricarli senza credenziali (within LAN).
"""
import base64
import json
import os
import re
from builtins import open

ICONE_DIR = "/config/www/vc-icone"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 4 * 1024 * 1024  # 4 MB per icona (sono piccole)
SELECT_ENTITIES = [
    "input_select.videocitofono_campanello1_icona",
    "input_select.videocitofono_campanello2_icona",
    "input_select.videocitofono_campanello3_icona",
    "input_select.videocitofono_campanello4_icona",
    "input_select.videocitofono_metodo_pin_icona",
    "input_select.videocitofono_metodo_face_icona",
    "input_select.videocitofono_metodo_nfc_icona",
]
TOPIC_CMD = "videocitofono/cmd"


def _ensure_dir():
    try:
        os.makedirs(ICONE_DIR, exist_ok=True)
    except Exception as e:
        log.error(f"Creazione cartella icone fallita: {e}")


def _scan_files():
    _ensure_dir()
    try:
        names = []
        for fn in sorted(os.listdir(ICONE_DIR)):
            ext = os.path.splitext(fn)[1].lower()
            if ext in ALLOWED_EXT and not fn.startswith("."):
                names.append(fn)
        return names
    except Exception as e:
        log.error(f"Scan cartella icone fallito: {e}")
        return []


def _sanitize_name(filename: str) -> str:
    base = os.path.basename(filename or "")
    base = base.replace(" ", "_")
    base = re.sub(r"[^A-Za-z0-9._\-]", "", base)
    if not base:
        return ""
    name, ext = os.path.splitext(base)
    if ext.lower() not in ALLOWED_EXT:
        return ""
    return f"{name[:60]}{ext.lower()}"


def _set_options(options):
    opts = ["default"] + [o for o in options if o != "default"]
    for ent in SELECT_ENTITIES:
        try:
            current = hass.states.get(ent)
            cur_state = current.state if current else "default"
            input_select.set_options(entity_id=ent, options=opts)
            if cur_state not in opts:
                input_select.select_option(entity_id=ent, option="default")
        except Exception as e:
            log.error(f"set_options icone {ent} fallito: {e}")
    log.info(f"input_select icone aggiornati ({len(opts)} opzioni)")


def _publish_library(files):
    try:
        videocitofono_mqtt_cmd(
            action="set_icone_library",
            base_url="/local/vc-icone/",
            files=files,
        )
    except Exception as e:
        log.warning(f"MQTT publish library icone fallito: {e}")


@service
def videocitofono_refresh_icone():
    """Rilegge la cartella icone e aggiorna gli input_select + notifica RPi."""
    files = _scan_files()
    _set_options(files)
    _publish_library(files)
    log.info(f"refresh icone: {len(files)} file = {files}")


@time_trigger("startup")
def videocitofono_icone_startup():
    """Primo refresh all'avvio: vedi la nota gemella in sfondi.py.

    L'automazione HA con ritardo fisso arrivava a volte prima che pyscript
    avesse compilato questo file, con l'errore "Action
    pyscript.videocitofono_refresh_icone not found".
    """
    task.sleep(8)
    videocitofono_refresh_icone()


@service
def videocitofono_upload_icona(filename=None, content_b64=None):
    """Salva una nuova icona. Argomenti:
    - filename:    nome file (verra' sanitizzato)
    - content_b64: contenuto file in base64 (max 4 MB decoded)
    """
    if not filename or not content_b64:
        log.warning("upload icona: parametri mancanti")
        return
    safe = _sanitize_name(filename)
    if not safe:
        log.warning(f"upload icona: nome non valido ({filename!r})")
        return
    try:
        raw = base64.b64decode(content_b64, validate=True)
    except Exception as e:
        log.error(f"upload icona: base64 invalido: {e}")
        return
    if len(raw) > MAX_BYTES:
        log.warning(f"upload icona: file troppo grande ({len(raw)} bytes)")
        return
    _ensure_dir()
    dst = os.path.join(ICONE_DIR, safe)
    try:
        with open(dst, "wb") as f:
            f.write(raw)
        try:
            os.chmod(dst, 0o644)
        except Exception:
            pass
        log.info(f"upload icona OK: {safe} ({len(raw)} bytes)")
    except Exception as e:
        log.error(f"upload icona: scrittura fallita: {e}")
        return
    files = _scan_files()
    _set_options(files)
    _publish_library(files)


@service
def videocitofono_delete_icona(filename=None):
    """Elimina un'icona dalla libreria."""
    if not filename or filename == "default":
        log.warning("delete icona: nome non valido o 'default'")
        return
    safe = _sanitize_name(filename)
    if not safe:
        log.warning(f"delete icona: nome non valido ({filename!r})")
        return
    path = os.path.join(ICONE_DIR, safe)
    try:
        if os.path.exists(path):
            os.remove(path)
            log.info(f"icona eliminata: {safe}")
    except Exception as e:
        log.error(f"delete icona: {e}")
        return
    files = _scan_files()
    _set_options(files)
    _publish_library(files)
    for ent in SELECT_ENTITIES:
        try:
            cur = hass.states.get(ent)
            if cur and cur.state == safe:
                input_select.select_option(entity_id=ent, option="default")
        except Exception:
            pass
