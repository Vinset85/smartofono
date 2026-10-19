"""Pyscript per gestione registro chiamate videocitofono.

Espone 4 service:
- pyscript.update_registro_videocitofono: aggiunge/aggiorna record
- pyscript.purge_registro_videocitofono: elimina record > N giorni + file video
- pyscript.pulisci_registro_videocitofono: svuota tutto (registro + video)
- pyscript.applica_retention_video_videocitofono: a fine chiamata tiene la
  registrazione solo se nessuno ha risposto

I file video sono salvati fisicamente in /config/www/videocitofono/ (accessibili
via HTTP come /local/videocitofono/<file>.mp4 per popup HTML5). Un simlink
/media/videocitofono -> /config/www/videocitofono li rende visibili anche nel
Media Browser di HA.
"""
import json
import os
from datetime import datetime, timedelta
from builtins import open

REGISTRO_FILE = "/config/www/registro_videocitofono.json"
VIDEO_DIR = "/config/www/videocitofono"
DEFAULT_PURGE_DAYS = 7
# Tetto disco: se le chiamate non risposte si accumulano prima del purge
# notturno, togliamo i file piu' vecchi. 2 GiB / 80 file.
VIDEO_MAX_BYTES = 2 * 1024 * 1024 * 1024
VIDEO_MAX_FILES = 80

# Un'azione di risposta o di apertura vale per l'ultima chiamata solo se quella
# chiamata e' ancora aperta, oppure si e' chiusa un attimo prima: rispondendo
# proprio allo scadere del timeout, il RPi pubblica "annullata" e HA
# "risposto"/"porta_aperta" quasi insieme, e l'ordine di arrivo non e' garantito.
FINESTRA_RACE_SEC = 30
# Durante una conversazione l'apertura della porta puo' arrivare anche un paio di
# minuti dopo la risposta: e' sempre la stessa chiamata.
FINESTRA_CONVERSAZIONE_SEC = 300


def _load_registro():
    try:
        with open(REGISTRO_FILE, "r") as f:
            content = json.load(f)
            return content.get("all", []) if isinstance(content, dict) else []
    except Exception as e:
        log.warning(f"Registro non leggibile: {e}")
        return []


def _save_registro(data):
    try:
        with open(REGISTRO_FILE, "w") as f:
            json.dump({"all": data}, f, indent=2)
        log.info(f"Registro salvato: {len(data)} record")
    except Exception as e:
        log.error(f"Errore scrittura registro: {e}")
    # Forza refresh del sensor command_line senza attendere scan_interval
    try:
        homeassistant.update_entity(entity_id="sensor.registro_videocitofono")
    except Exception as e:
        log.warning(f"Refresh sensor fallito: {e}")


def _video_disk_path(record):
    """Risolve il path fisico sul disco dal campo 'video' del record.
    Supporta sia vecchi path (/config/www/videocitofono/...) sia nuovi URL
    (/local/videocitofono/... o /media/local/videocitofono/...)."""
    v = (record.get("video") or "").strip()
    if not v:
        return None
    fname = v.split("/")[-1]
    if not fname.endswith(".mp4"):
        return None
    return os.path.join(VIDEO_DIR, fname)


def _momento(record, *chiavi):
    """Primo istante disponibile fra le chiavi indicate, come datetime."""
    for chiave in chiavi:
        valore = (record.get(chiave) or "").strip()
        if not valore:
            continue
        try:
            return datetime.fromisoformat(valore)
        except ValueError:
            continue
    return None


def _appartiene_alla_chiamata(record):
    """Dice se un'azione di risposta/apertura riguarda l'ultima chiamata.

    Serve perche' la porta si puo' aprire dalla dashboard anche quando nessuno
    ha suonato: senza questo controllo l'apertura veniva applicata all'ultima
    voce del registro, che poteva essere una chiamata persa chiusa da un pezzo.
    Restituisce (esito, motivo) e il motivo finisce nel log quando si rifiuta.
    """
    stato = (record.get("stato") or "in_corso").strip()
    if stato in ("in_corso", "non_risposta"):
        return True, ""
    if stato == "risposto":
        riferimento = _momento(record, "ora_risposta", "timestamp")
        limite = FINESTRA_CONVERSAZIONE_SEC
    else:
        riferimento = _momento(record, "ora_chiusura", "timestamp")
        limite = FINESTRA_RACE_SEC
    if riferimento is None:
        return False, f"ultimo record '{stato}' senza riferimento temporale"
    eta = (datetime.now() - riferimento).total_seconds()
    if eta <= limite:
        return True, ""
    return False, (f"ultimo record '{stato}' chiuso da {int(eta)}s "
                   f"(finestra {limite}s)")


def _delete_video(record):
    path = _video_disk_path(record)
    if not path:
        return False
    try:
        if os.path.exists(path):
            os.remove(path)
            log.info(f"Video eliminato: {path}")
            return True
    except Exception as e:
        log.error(f"Errore eliminazione {path}: {e}")
    return False


@service
def update_registro_videocitofono(stato="in_corso", video_path="", azione=None, campanello=None):
    """Aggiunge un nuovo record di chiamata oppure aggiorna l'ultimo con un'azione.

    Stati possibili:
      - 'in_corso'  -> chiamata appena partita (squilla, default)
      - 'risposto'  -> qualcuno ha risposto (audio/video) o aperto la porta
      - 'rifiutata' -> utente HA ha premuto "Chiudi" senza rispondere
      - 'persa'     -> timeout 60s popup OR cancello esterno (RPi annulla)

    Azioni (per aggiornamento dell'ultimo record):
      - None / 'suonata'    -> crea nuovo record (stato=in_corso default)
      - 'apertura'          -> stato=risposto + azione=apertura
      - 'risposta_audio'    -> stato=risposto + azione=risposta_audio
      - 'risposta_video'    -> stato=risposto + azione=risposta_video
      - 'talkback'          -> stato=risposto + azione=talkback

    Le quattro azioni di risposta valgono solo per una chiamata ancora aperta o
    appena conclusa (vedi _appartiene_alla_chiamata): aprire la porta dalla
    dashboard quando nessuno ha suonato non deve riscrivere la chiamata
    precedente.
      - 'rifiutata'         -> SE record ancora in_corso: stato=rifiutata
                              (NON sovrascrive 'risposto': se l'utente prima
                              ha risposto e poi chiude, resta 'risposto')
      - 'persa'             -> SE record ancora in_corso: stato=persa
                              (idem: non sovrascrive 'risposto')

    campanello: identificativo del campanello premuto sul RPi (opzionale).
    """
    now = datetime.now().isoformat()
    data = _load_registro()

    azioni_risposta = ("apertura", "risposta_video", "risposta_audio", "talkback")
    azioni_chiusura = ("rifiutata", "persa")

    if azione in azioni_risposta:
        if not data:
            log.warning(f"Azione {azione} ma registro vuoto, ignoro")
        else:
            ammessa, motivo = _appartiene_alla_chiamata(data[-1])
            if not ammessa:
                log.info(
                    f"Azione {azione} ignorata, nessuna chiamata a cui riferirla: "
                    f"{motivo}"
                )
            else:
                data[-1]["stato"] = "risposto"
                data[-1]["azione"] = azione
                data[-1]["ora_risposta"] = now
                log.info(f"Record aggiornato: risposto/{azione}")
    elif azione in azioni_chiusura:
        if not data:
            log.warning(f"Azione {azione} ma registro vuoto, ignoro")
        else:
            ultimo = data[-1]
            stato_attuale = ultimo.get("stato", "in_corso")
            if stato_attuale == "risposto":
                # Non sovrascrivere: una chiamata gia' risposta resta tale
                # anche se poi viene chiusa esplicitamente.
                log.info(
                    f"Azione {azione} ignorata: ultimo record gia' 'risposto'"
                )
            elif stato_attuale in ("in_corso", "non_risposta"):
                ultimo["stato"] = azione
                ultimo["ora_chiusura"] = now
                log.info(f"Record aggiornato: stato -> {azione}")
            else:
                log.info(
                    f"Azione {azione} ignorata: stato attuale '{stato_attuale}' non sovrascrivibile"
                )
    else:
        # Crea nuovo record (chiamata appena iniziata).
        # Normalizza video_path in URL /local/videocitofono/<file>.mp4
        video_url = video_path
        if video_path:
            fname = video_path.split("/")[-1]
            video_url = f"/local/videocitofono/{fname}"
        record = {
            "timestamp": now,
            "stato": stato,
            "video": video_url,
        }
        if campanello:
            record["campanello"] = campanello
        data.append(record)
        log.info(f"Nuovo record: {stato} - {video_url} - campanello={campanello}")

    _save_registro(data)


@service
def applica_retention_video_videocitofono(attesa=6, tentativi=3):
    """Chiamato a fine chiamata: conserva il video solo se non c'e' stata risposta.

    Politica scelta: la registrazione serve come prova di chi ha suonato quando
    in casa non c'era nessuno. Se qualcuno ha risposto (audio, video, talkback o
    apertura porta) il video non serve e viene cancellato subito, senza
    aspettare il purge dei 7 giorni.

    `attesa`: secondi da lasciare all'egress LiveKit per finalizzare l'MP4
    (l'automation chiama /egress/stop poco prima). Se il file non c'e' comunque
    - egress giu', o nessuna traccia pubblicata perche' la chiamata e' caduta
    subito - il riferimento viene azzerato, cosi' il registro non mostra piu'
    link a video inesistenti (era il sintomo dei record di agosto 2026).

    `tentativi`: quante volte riprovare, a distanza di `attesa`, quando la
    chiamata e' stata risposta ma l'MP4 non e' ancora sul disco. Al primo giro
    l'egress a volte non ha finito di scrivere: azzerare subito il riferimento
    lasciava il file sul disco per sempre, senza piu' nessun record che lo
    citasse (e' come e' rimasto l'orfano del 18 agosto).
    """
    data = _load_registro()
    if not data:
        return
    ultimo = data[-1]
    stato = (ultimo.get("stato") or "").strip()
    if stato == "risposto":
        for giro in range(max(1, int(tentativi))):
            task.sleep(max(0, int(attesa)))
            if _delete_video(ultimo):
                log.info("Retention: chiamata risposta, registrazione scartata")
                break
            path = _video_disk_path(ultimo)
            if path is None:
                break
            log.info(
                f"Retention: MP4 non ancora pronto ({path}), "
                f"tentativo {giro + 1}"
            )
        ultimo["video"] = ""
        _save_registro(data)
        return
    task.sleep(max(0, int(attesa)))
    path = _video_disk_path(ultimo)
    if path and not os.path.exists(path):
        ultimo["video"] = ""
        _save_registro(data)
        log.warning(f"Retention: nessun file da egress ({path}), riferimento rimosso")
        return
    log.info(f"Retention: registrazione conservata (stato={stato or 'n/d'})")


@service
def purge_registro_videocitofono(giorni=DEFAULT_PURGE_DAYS):
    """Rimuove record > N giorni (default 7) e cancella i relativi file video."""
    try:
        giorni = int(giorni)
    except Exception:
        giorni = DEFAULT_PURGE_DAYS
    data = _load_registro()
    if not data:
        log.info("Registro già vuoto, purge skip")
        return
    cutoff = datetime.now() - timedelta(days=giorni)
    tenuti = []
    eliminati = 0
    video_eliminati = 0
    for r in data:
        try:
            ts = datetime.fromisoformat(r["timestamp"])
        except Exception:
            tenuti.append(r)
            continue
        if ts > cutoff:
            tenuti.append(r)
        else:
            if _delete_video(r):
                video_eliminati += 1
            eliminati += 1
    _save_registro(tenuti)
    orfani = _rimuovi_video_orfani(tenuti)
    quota = _enforce_video_quota(tenuti)
    if quota:
        tenuti = quota
        _save_registro(tenuti)
    log.info(
        f"Purge completato: {eliminati} record eliminati (> {giorni}g), "
        f"{video_eliminati} video cancellati, {orfani} orfani rimossi, "
        f"{len(tenuti)} record rimasti"
    )


def _rimuovi_video_orfani(data):
    """Cancella gli MP4 che nessun record cita piu'.

    Restano indietro quando l'egress finisce di scrivere dopo che la retention
    ha ormai azzerato il riferimento, o quando la chiamata non arriva affatto nel
    registro (per esempio se qualcuno suona durante un riavvio di HA, con
    pyscript non ancora pronto). Sono file di ingresso ripresi senza che nessuna
    voce li mostri: non si possono ne' guardare ne' cancellare dall'interfaccia.
    """
    citati = set()
    for r in data:
        path = _video_disk_path(r)
        if path:
            citati.add(os.path.basename(path))
    rimossi = 0
    # Un file appena scritto puo' essere di una chiamata il cui record sta per
    # arrivare, o di una registrazione ancora in corso: si guarda solo indietro.
    soglia = (datetime.now() - timedelta(minutes=10)).timestamp()
    try:
        for fname in os.listdir(VIDEO_DIR):
            if not fname.endswith(".mp4") or fname in citati:
                continue
            full = os.path.join(VIDEO_DIR, fname)
            try:
                if os.path.getmtime(full) > soglia:
                    continue
            except Exception:
                continue
            try:
                os.remove(full)
                rimossi += 1
                log.info(f"Video orfano rimosso: {full}")
            except Exception as e:
                log.error(f"Errore rimozione orfano {full}: {e}")
    except Exception as e:
        log.warning(f"Scan cartella video fallito: {e}")
    return rimossi


def _enforce_video_quota(data, max_bytes=VIDEO_MAX_BYTES, max_files=VIDEO_MAX_FILES):
    """Cancella gli MP4 piu' vecchi se si supera tetto disco o numero file."""
    try:
        files = []
        for fname in os.listdir(VIDEO_DIR):
            if not fname.endswith(".mp4"):
                continue
            full = os.path.join(VIDEO_DIR, fname)
            try:
                st = os.stat(full)
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, full, fname))
    except Exception as e:
        log.warning(f"Quota video: scan fallito: {e}")
        return None
    files.sort()
    total = 0
    for _m, sz, _p, _n in files:
        total += sz
    changed = False
    while files and (len(files) > max_files or total > max_bytes):
        _mtime, size, full, fname = files.pop(0)
        try:
            os.remove(full)
            total -= size
            changed = True
            log.info(f"Quota video: rimosso {full}")
        except Exception as e:
            log.error(f"Quota video: errore {full}: {e}")
            continue
        for r in data:
            path = _video_disk_path(r)
            if path and os.path.basename(path) == fname:
                r["video"] = ""
    return data if changed else None


@time_trigger("startup")
def _purge_orfani_all_avvio():
    """Toglie gli MP4 che il registro non cita piu', senza toccare i recentissimi."""
    data = _load_registro()
    n = _rimuovi_video_orfani(data)
    quota = _enforce_video_quota(data)
    if quota:
        _save_registro(quota)
    if n:
        log.info(f"Avvio: {n} video orfani rimossi")


@service
def pulisci_registro_videocitofono():
    """Svuota COMPLETAMENTE il registro ed elimina TUTTI i video."""
    data = _load_registro()
    video_eliminati = 0
    for r in data:
        if _delete_video(r):
            video_eliminati += 1
    # Elimina anche eventuali mp4 orfani nella cartella
    try:
        for fname in os.listdir(VIDEO_DIR):
            if fname.endswith(".mp4"):
                full = os.path.join(VIDEO_DIR, fname)
                try:
                    os.remove(full)
                    video_eliminati += 1
                    log.info(f"Video orfano rimosso: {full}")
                except Exception as e:
                    log.error(f"Errore rimozione orfano {full}: {e}")
    except Exception as e:
        log.warning(f"Scan cartella video fallito: {e}")
    _save_registro([])
    log.info(f"Registro svuotato: {len(data)} record cancellati + {video_eliminati} video")
