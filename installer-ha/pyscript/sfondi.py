"""Gestione libreria sfondi videocitofono.

Espone 3 service:
- pyscript.videocitofono_refresh_sfondi: scansiona /config/www/vc-sfondi/ e
  popola le opzioni di input_select.videocitofono_sfondo.
- pyscript.videocitofono_upload_sfondo: salva un file (passato come base64)
  in /config/www/vc-sfondi/, sanitizza il nome, refresh + notifica RPi.
- pyscript.videocitofono_delete_sfondo: elimina un file dalla libreria, refresh
  + (se era selezionato) reset a 'default' + notifica RPi.

I file sono accessibili via HTTP HA come /local/vc-sfondi/<nome>, così il RPi
puo' scaricarli senza credenziali (within LAN).
"""
import base64
import json
import os
import re
from builtins import open

SFONDI_DIR = "/config/www/vc-sfondi"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 8 * 1024 * 1024  # 8 MB per file
SELECT_ENTITY = "input_select.videocitofono_sfondo"
TOPIC_CMD = "videocitofono/cmd"


def _ensure_dir():
    try:
        os.makedirs(SFONDI_DIR, exist_ok=True)
    except Exception as e:
        log.error(f"Creazione cartella sfondi fallita: {e}")


def _scan_files():
    _ensure_dir()
    try:
        names = []
        for fn in sorted(os.listdir(SFONDI_DIR)):
            ext = os.path.splitext(fn)[1].lower()
            if ext in ALLOWED_EXT and not fn.startswith("."):
                names.append(fn)
        return names
    except Exception as e:
        log.error(f"Scan cartella sfondi fallito: {e}")
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
    try:
        current = hass.states.get(SELECT_ENTITY)
        cur_state = current.state if current else "default"
        input_select.set_options(entity_id=SELECT_ENTITY, options=opts)
        if cur_state not in opts:
            input_select.select_option(entity_id=SELECT_ENTITY, option="default")
        log.info(f"input_select.videocitofono_sfondo opzioni aggiornate ({len(opts)})")
    except Exception as e:
        log.error(f"set_options sfondo fallito: {e}")


def _publish_library(files):
    try:
        videocitofono_mqtt_cmd(
            action="set_sfondi_library",
            base_url="/local/vc-sfondi/",
            files=files,
        )
    except Exception as e:
        log.warning(f"MQTT publish library sfondi fallito: {e}")


@service
def videocitofono_refresh_sfondi():
    """Rilegge la cartella sfondi e aggiorna l'input_select + notifica RPi."""
    files = _scan_files()
    _set_options(files)
    _publish_library(files)
    log.info(f"refresh sfondi: {len(files)} file = {files}")


@time_trigger("startup")
def videocitofono_sfondi_startup():
    """Primo refresh all'avvio, fatto da qui e non da un'automazione HA.

    L'automazione che chiamava il service dopo l'evento `homeassistant start`
    con un ritardo fisso a volte partiva prima che pyscript avesse compilato
    questo file, e HA segnalava "Action pyscript.videocitofono_refresh_sfondi
    not found". Con questo trigger la funzione parte quando i service esistono
    per definizione; l'attesa serve solo a dare tempo agli input_select di
    essere creati.
    """
    task.sleep(8)
    videocitofono_refresh_sfondi()


@service
def videocitofono_upload_sfondo(filename=None, content_b64=None):
    """Salva un nuovo sfondo. Argomenti:
    - filename:    nome file (verrà sanitizzato)
    - content_b64: contenuto file in base64 (max 8 MB decoded)
    """
    if not filename or not content_b64:
        log.warning("upload sfondo: parametri mancanti")
        return
    safe = _sanitize_name(filename)
    if not safe:
        log.warning(f"upload sfondo: nome non valido ({filename!r})")
        return
    try:
        raw = base64.b64decode(content_b64, validate=True)
    except Exception as e:
        log.error(f"upload sfondo: base64 invalido: {e}")
        return
    if len(raw) > MAX_BYTES:
        log.warning(f"upload sfondo: file troppo grande ({len(raw)} bytes)")
        return
    _ensure_dir()
    dst = os.path.join(SFONDI_DIR, safe)
    try:
        with open(dst, "wb") as f:
            f.write(raw)
        try:
            os.chmod(dst, 0o644)
        except Exception:
            pass
        log.info(f"upload sfondo OK: {safe} ({len(raw)} bytes)")
    except Exception as e:
        log.error(f"upload sfondo: scrittura fallita: {e}")
        return
    files = _scan_files()
    _set_options(files)
    _publish_library(files)


@service
def videocitofono_delete_sfondo(filename=None):
    """Elimina uno sfondo dalla libreria."""
    if not filename or filename == "default":
        log.warning("delete sfondo: nome non valido o 'default'")
        return
    safe = _sanitize_name(filename)
    if not safe:
        log.warning(f"delete sfondo: nome non valido ({filename!r})")
        return
    path = os.path.join(SFONDI_DIR, safe)
    try:
        if os.path.exists(path):
            os.remove(path)
            log.info(f"sfondo eliminato: {safe}")
    except Exception as e:
        log.error(f"delete sfondo: {e}")
        return
    files = _scan_files()
    _set_options(files)
    _publish_library(files)
    try:
        cur = hass.states.get(SELECT_ENTITY)
        if cur and cur.state == safe:
            input_select.select_option(entity_id=SELECT_ENTITY, option="default")
    except Exception:
        pass
