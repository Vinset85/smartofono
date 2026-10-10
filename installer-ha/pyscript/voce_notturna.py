"""Volume della voce di benvenuto diverso di giorno e di notte.

Lo slider `input_number.videocitofono_volume_tts` resta l'unico valore che il
citofono riceve (l'automazione "Sync UI/Audio settings" lo propaga al RPi entro
un paio di secondi, che lo applica al TTS senza riavvii). Qui dentro si decide
quale valore scriverci:

- `videocitofono_volume_tts_giorno` e `..._notte` sono i due livelli;
- `videocitofono_voce_notte_inizio` e `..._fine` delimitano la fascia notturna,
  che normalmente scavalca la mezzanotte;
- `input_boolean.videocitofono_voce_notturna` disattiva tutto il meccanismo.

Una regolazione fatta a mano sullo slider principale non viene sovrascritta al
minuto dopo: viene memorizzata nel livello della fascia in corso, cosi' "adesso
e' troppo alta" diventa una preferenza persistente per quella fascia.

Perche' pyscript e non un'automazione YAML: la fascia a cavallo della mezzanotte
e la distinzione fra "l'ho scritto io" e "l'ha mosso l'utente" in Jinja
diventano illeggibili.
"""
import datetime

VOLUME = "input_number.videocitofono_volume_tts"
GIORNO = "input_number.videocitofono_volume_tts_giorno"
NOTTE = "input_number.videocitofono_volume_tts_notte"
INIZIO = "input_datetime.videocitofono_voce_notte_inizio"
FINE = "input_datetime.videocitofono_voce_notte_fine"
ABILITA = "input_boolean.videocitofono_voce_notturna"

# Valori del primo avvio, usati solo se l'helper non ha ancora un valore suo.
SEED_LIVELLI = {GIORNO: 70.0, NOTTE: 50.0}
SEED_ORARI = {INIZIO: "22:00:00", FINE: "07:30:00"}

# Sotto questa soglia il livello di una fascia si considera "mai impostato":
# senza `initial` HA crea gli input_number al minimo, non a `unknown`, e uno zero
# preso per buono lascerebbe la voce muta. I due helper hanno min 10 proprio per
# rendere lo zero irraggiungibile a mano.
LIVELLO_MINIMO = 10.0

# Finestra di silenzio dopo l'avvio di HA: gli helper tornano dallo stato
# ripristinato e `carica_defaults` scrive i suoi valori, e nessuno dei due e'
# una regolazione dell'utente da memorizzare.
ATTESA_AVVIO_SEC = 90

_pronto = False
# Ultimo valore scritto da noi sullo slider: serve a non confonderlo con una
# regolazione manuale.
_scritto_da_noi = None


def _valore(entity_id):
    """Numero dell'helper, oppure None se non ha ancora uno stato valido."""
    st = hass.states.get(entity_id)
    if st is None or st.state in ("unknown", "unavailable", ""):
        return None
    try:
        return float(st.state)
    except (TypeError, ValueError):
        return None


def _livello(entity_id):
    """Livello di una fascia, None se non ancora impostato (vedi LIVELLO_MINIMO)."""
    v = _valore(entity_id)
    if v is None or v < LIVELLO_MINIMO:
        return None
    return v


def _secondi_dalla_mezzanotte(entity_id):
    """Orario dell'input_datetime in secondi. None se non impostato."""
    st = hass.states.get(entity_id)
    if st is None or st.state in ("unknown", "unavailable", ""):
        return None
    ts = st.attributes.get("timestamp")
    if ts is None:
        return None
    return int(ts)


def _attivo():
    st = hass.states.get(ABILITA)
    return st is not None and st.state == "on"


def _e_notte():
    """True se adesso siamo nella fascia notturna."""
    ini = _secondi_dalla_mezzanotte(INIZIO)
    fin = _secondi_dalla_mezzanotte(FINE)
    if ini is None or fin is None or ini == fin:
        return False
    adesso = datetime.datetime.now()
    ora = adesso.hour * 3600 + adesso.minute * 60 + adesso.second
    if ini > fin:
        # Caso normale: la fascia scavalca la mezzanotte (22:00 -> 07:30).
        return ora >= ini or ora < fin
    return ini <= ora < fin


def _seed():
    """Popola gli helper mai impostati, senza toccare quelli con un valore."""
    for entity_id, valore in SEED_LIVELLI.items():
        if _livello(entity_id) is None:
            input_number.set_value(entity_id=entity_id, value=valore)
            log.info(f"voce notturna: {entity_id} inizializzato a {valore:.0f}%")
    for entity_id, orario in SEED_ORARI.items():
        if _secondi_dalla_mezzanotte(entity_id) in (None, 0):
            input_datetime.set_datetime(entity_id=entity_id, time=orario)
            log.info(f"voce notturna: {entity_id} inizializzato a {orario}")


@service
def videocitofono_applica_volume_voce():
    """Porta lo slider principale al livello della fascia in corso."""
    global _scritto_da_noi
    if not _attivo():
        return
    notte = _e_notte()
    atteso = _livello(NOTTE if notte else GIORNO)
    if atteso is None:
        return
    corrente = _valore(VOLUME)
    if corrente is not None and abs(corrente - atteso) < 0.01:
        return
    _scritto_da_noi = atteso
    input_number.set_value(entity_id=VOLUME, value=atteso)
    log.info(
        f"voce notturna: fascia {'notturna' if notte else 'diurna'}, "
        f"volume voce {atteso:.0f}% (era {corrente})"
    )


@time_trigger("startup")
def videocitofono_voce_notturna_startup():
    """Primo popolamento e prima applicazione all'avvio di HA.

    L'attesa iniziale lascia creare gli helper; quella finale copre il
    `carica_defaults` che parte 45 secondi dopo l'avvio.
    """
    global _pronto
    task.sleep(20)
    _seed()
    videocitofono_applica_volume_voce()
    task.sleep(ATTESA_AVVIO_SEC)
    _pronto = True


@time_trigger("cron(* * * * *)")
def videocitofono_voce_notturna_minuto():
    """Cambio di fascia al minuto giusto, e recupero se qualcuno sovrascrive."""
    videocitofono_applica_volume_voce()


@state_trigger(
    "input_number.videocitofono_volume_tts_giorno",
    "input_number.videocitofono_volume_tts_notte",
    "input_datetime.videocitofono_voce_notte_inizio",
    "input_datetime.videocitofono_voce_notte_fine",
    "input_boolean.videocitofono_voce_notturna",
)
def videocitofono_voce_notturna_impostazioni(**kwargs):
    """Una modifica alle impostazioni si vede subito, senza aspettare il minuto."""
    videocitofono_applica_volume_voce()


@state_trigger("input_number.videocitofono_volume_tts")
def videocitofono_voce_notturna_memorizza(value=None, **kwargs):
    """Ricorda nella fascia in corso il volume regolato a mano."""
    global _scritto_da_noi
    if not _pronto or not _attivo():
        return
    try:
        v = float(value)
    except (TypeError, ValueError):
        return
    if _scritto_da_noi is not None and abs(v - _scritto_da_noi) < 0.01:
        return
    if v < LIVELLO_MINIMO:
        return
    bersaglio = NOTTE if _e_notte() else GIORNO
    if _valore(bersaglio) == v:
        return
    input_number.set_value(entity_id=bersaglio, value=v)
    log.info(f"voce notturna: {v:.0f}% memorizzato in {bersaglio}")
