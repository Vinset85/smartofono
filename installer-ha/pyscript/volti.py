"""Gestione libreria volti riconoscimento facciale.

Espone 2 service:
- pyscript.videocitofono_enroll_volto: registra una nuova foto del volto
  per la persona indicata. Argomenti:
    nome:        nome persona (verra' sanitizzato)
    content_b64: foto in base64 (max 4 MB decoded). Idealmente JPEG
                 800x600 o superiore con UN solo volto frontale ben
                 illuminato.
- pyscript.videocitofono_delete_volto: elimina TUTTE le foto della
  persona indicata. Argomenti: nome.

Comunicazione: i volti sono memorizzati sul RPi (data/faces/<nome>/),
non su HA. Lo storage su HA e' inadatto perche' face_recognition gira
solo lato RPi. Il flusso e' quindi:
    HA service  -> mqtt videocitofono/cmd action=enroll_face/delete_face
    RPi handler -> face.enroll_image / face.delete_user
                -> mqtt videocitofono/volti/library (retain): lista
                   {nome, foto} aggiornata
HA legge il topic retain via sensore mqtt (configurato in
configuration.yaml.fixed) per aggiornare la card UI.
"""
import base64
import json
import re

TOPIC_CMD = "videocitofono/cmd"
TOPIC_LIBRARY = "videocitofono/volti/library"
MAX_BYTES = 4 * 1024 * 1024  # 4 MB per foto


def _sanitize_name(nome):
    if not nome:
        return ""
    s = nome.strip().replace(" ", "_")
    s = re.sub(r"[^A-Za-z0-9_\-]", "", s)
    return s[:64]


def _normalize_genere(g):
    if not g:
        return ""
    s = str(g).strip().upper()
    if s in ("M", "MALE", "MASCHIO", "MASCHILE", "U", "UOMO"):
        return "M"
    if s in ("F", "FEMALE", "FEMMINA", "FEMMINILE", "D", "DONNA"):
        return "F"
    return ""


@service
def videocitofono_enroll_volto(nome=None, content_b64=None, ext=None, genere=None):
    """Registra una nuova foto volto. Argomenti:
    - nome:        nome persona da associare (sara' sanitizzato).
    - content_b64: foto in base64 (max 4 MB decoded).
    - ext:         estensione opzionale (.jpg | .png), default '.jpg'.
    - genere:      'M' o 'F' (opzionale; salvato in meta.json sul RPi
                   per personalizzare il saluto Bentornato/Bentornata).
    """
    nome_safe = _sanitize_name(nome)
    if not nome_safe:
        log.warning(f"enroll volto: nome non valido ({nome!r})")
        return
    if not content_b64:
        log.warning("enroll volto: content_b64 mancante")
        return
    try:
        raw = base64.b64decode(content_b64, validate=True)
    except Exception as e:
        log.error(f"enroll volto: base64 invalido: {e}")
        return
    if len(raw) > MAX_BYTES:
        log.warning(f"enroll volto: file troppo grande ({len(raw)} bytes)")
        return
    payload = {
        "action": "enroll_face",
        "nome": nome_safe,
        "image_b64": content_b64,
        "ext": (ext or ".jpg").lower(),
    }
    g = _normalize_genere(genere)
    if g:
        payload["genere"] = g
    try:
        pyscript.videocitofono_mqtt_cmd(**payload)
        log.info(f"enroll volto richiesto: {nome_safe} ({len(raw)} bytes, g={g or '-'})")
    except Exception as e:
        log.error(f"enroll volto MQTT publish fallito: {e}")


@service
def videocitofono_update_volto(nome=None, genere=None):
    """Aggiorna i metadati (genere) di un volto gia' registrato."""
    nome_safe = _sanitize_name(nome)
    if not nome_safe:
        log.warning(f"update volto: nome non valido ({nome!r})")
        return
    g = _normalize_genere(genere)
    payload = {"action": "update_face", "nome": nome_safe, "genere": g}
    try:
        pyscript.videocitofono_mqtt_cmd(**payload)
        log.info(f"update volto richiesto: {nome_safe} g={g or '-'}")
    except Exception as e:
        log.error(f"update volto MQTT publish fallito: {e}")


@service
def videocitofono_set_volto_pin(nome=None, pin=None):
    """Imposta o rimuove il PIN associato a un volto.
    - nome: nome dell'utente (verra' sanitizzato)
    - pin:  4-8 cifre numeriche per impostare; stringa vuota o None per
            rimuovere il PIN (l'utente potra' accedere solo via volto).
    """
    nome_safe = _sanitize_name(nome)
    if not nome_safe:
        log.warning(f"set volto pin: nome non valido ({nome!r})")
        return
    pin_clean = ""
    if pin is not None:
        pin_clean = re.sub(r"\D", "", str(pin))
    if pin_clean and not (4 <= len(pin_clean) <= 8):
        log.warning(f"set volto pin: pin non valido (len={len(pin_clean)})")
        return
    payload = {"action": "set_face_pin", "nome": nome_safe, "pin": pin_clean}
    try:
        pyscript.videocitofono_mqtt_cmd(**payload)
        log.info(f"set volto pin richiesto: {nome_safe} pin={'set' if pin_clean else 'cleared'}")
    except Exception as e:
        log.error(f"set volto pin MQTT publish fallito: {e}")


@service
def videocitofono_rename_volto(nome=None, nuovo_nome=None):
    """Rinomina la persona registrata (sposta la cartella delle foto)."""
    old_safe = _sanitize_name(nome)
    new_safe = _sanitize_name(nuovo_nome)
    if not old_safe or not new_safe:
        log.warning(f"rename volto: nome non valido ({nome!r} -> {nuovo_nome!r})")
        return
    if old_safe == new_safe:
        log.info("rename volto: nessun cambio")
        return
    payload = {"action": "rename_face", "nome": old_safe, "nuovo_nome": new_safe}
    try:
        pyscript.videocitofono_mqtt_cmd(**payload)
        log.info(f"rename volto richiesto: {old_safe} -> {new_safe}")
    except Exception as e:
        log.error(f"rename volto MQTT publish fallito: {e}")


@service
def videocitofono_delete_volto(nome=None):
    """Elimina TUTTE le foto della persona indicata."""
    nome_safe = _sanitize_name(nome)
    if not nome_safe:
        log.warning(f"delete volto: nome non valido ({nome!r})")
        return
    payload = {"action": "delete_face", "nome": nome_safe}
    try:
        pyscript.videocitofono_mqtt_cmd(**payload)
        log.info(f"delete volto richiesto: {nome_safe}")
    except Exception as e:
        log.error(f"delete volto MQTT publish fallito: {e}")


@service
def videocitofono_refresh_volti():
    """Forza il RPi a ripubblicare la lista volti su videocitofono/volti/library."""
    payload = {"action": "list_faces"}
    try:
        pyscript.videocitofono_mqtt_cmd(**payload)
    except Exception as e:
        log.error(f"refresh volti MQTT publish fallito: {e}")


@service
def videocitofono_list_auto_faces(nome=None):
    """Elenca i campioni auto-enroll (`auto_*.jpg`) per una persona."""
    nome_safe = _sanitize_name(nome)
    if not nome_safe:
        log.warning(f"list auto faces: nome non valido ({nome!r})")
        return
    payload = {"action": "list_auto_faces", "nome": nome_safe}
    try:
        pyscript.videocitofono_mqtt_cmd(**payload)
    except Exception as e:
        log.error(f"list auto faces MQTT publish fallito: {e}")


@service
def videocitofono_delete_auto_face(nome=None, filename=None):
    """Elimina un singolo campione auto-enroll."""
    nome_safe = _sanitize_name(nome)
    fn = (filename or "").strip()
    if not nome_safe or not fn:
        log.warning("delete auto face: nome o filename mancante")
        return
    payload = {"action": "delete_auto_face", "nome": nome_safe, "filename": fn}
    try:
        pyscript.videocitofono_mqtt_cmd(**payload)
    except Exception as e:
        log.error(f"delete auto face MQTT publish fallito: {e}")


@service
def videocitofono_purge_auto_faces(nome=None):
    """Elimina tutti i campioni auto-enroll di una persona."""
    nome_safe = _sanitize_name(nome)
    if not nome_safe:
        log.warning(f"purge auto faces: nome non valido ({nome!r})")
        return
    payload = {"action": "purge_auto_faces", "nome": nome_safe}
    try:
        pyscript.videocitofono_mqtt_cmd(**payload)
    except Exception as e:
        log.error(f"purge auto faces MQTT publish fallito: {e}")


@mqtt_trigger("videocitofono/evento")
def videocitofono_auto_enroll_rejected(payload=None, **kw):
    if not payload:
        return
    try:
        d = json.loads(payload)
        if d.get("tipo") != "auto_enroll_rejected":
            return
        info = d.get("dati") or {}
        nome = info.get("nome", "?")
        service.call(
            "persistent_notification", "create",
            blocking=False,
            title="Auto-enroll rifiutato",
            message=(
                f"Identità non confermata per **{nome}** "
                f"(metodo {info.get('method', '?')}). Campione non salvato."
            ),
            notification_id=f"auto_enroll_rejected_{nome}",
        )
    except Exception as e:
        log.warning(f"auto_enroll_rejected notify err: {e}")
