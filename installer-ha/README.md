# Unità interna — Home Assistant

Questa è la parte che sta in casa: i package che definiscono entità e
automazioni, i pyscript che fanno il lavoro, le card della dashboard e lo stack
LiveKit per le videochiamate.

## Prerequisiti

- **Home Assistant OS** (collaudato su HAOS x86_64 su mini PC)
- addon **Mosquitto broker**, o un broker MQTT esterno raggiungibile
- integrazione **Pyscript** (da HACS): i file in `pyscript/` non sono
  decorativi, è lì che sta la logica
- addon **Advanced SSH & Web Terminal**, per arrivare a `/config`
- per le videochiamate, lo stack **LiveKit**: vedi [livekit/README.md](livekit/README.md)

## Installazione

L'installer gira **sull'host di Home Assistant**, non dal Mac: ha bisogno di
vedere `/config`. Dal terminale dell'addon SSH, con la cartella del progetto
raggiungibile:

```bash
cd installer-ha
cp secrets.yaml.example /config/secrets.yaml   # e riempilo
./install.sh
```

Se la configurazione non sta in `/config`, passa il percorso:
`HA_CONFIG=/percorso ./install.sh`.

Lo script copia i package, i pyscript, gli asset di `www/`, le card, i temi e i
default, poi **controlla che in `secrets.yaml` ci siano tutte le chiavi che i
package richiedono**. Quel controllo è il motivo per cui esiste: i package
usano `!secret`, e una chiave che manca non dà un errore di configurazione, dà
un Home Assistant che non riparte — e lo scopri col sistema già giù.

Non riavvia HA da solo. Dopo l'installazione: **Impostazioni > Sistema >
Riavvia**, e le card custom vanno aggiunte a mano in **Impostazioni >
Dashboard > Risorse** come `/local/<nome>.js`, tipo "modulo JavaScript".

## Struttura

```
installer-ha/
├── install.sh                  copia tutto in /config e verifica i segreti
├── secrets.yaml.example        le chiavi da generare, senza valori
├── packages/                   *.fixed: entità, automazioni e script di HA
├── pyscript/                   la logica: registro chiamate, NFC, volti,
│                               PIN ospiti, audit, voce notturna, icone
├── www/                        le card custom e gli asset serviti da /local
├── lovelace/                   le viste: dashboard, PIN ospiti, salute
├── themes/                     glass e vc-minimal
├── config/                     go2rtc e i default del pannello
├── livekit/                    lo stack delle videochiamate (Docker)
└── scripts/                    deploy e manutenzione
```

I file in `packages/` hanno estensione `.fixed` e l'installer la toglie quando
li copia: in `/config/packages/` arrivano come `configuration.yaml`,
`automations.yaml` e `scripts.yaml`.

## I segreti

Nel repository non c'è nessuna credenziale: `secrets.yaml.example` elenca le
chiavi con un segnaposto al posto del valore. Le tre che vanno **generate** e
non recuperate da qualche parte sono `vc_egress_secret`,
`videocitofono_cmd_secret` e `livekit_api_secret`:

```bash
openssl rand -hex 32
```

## MQTT

Il pannello e Home Assistant si parlano su MQTT sotto il prefisso
`videocitofono/`. I gruppi, come stanno nel codice:

| Prefisso | Direzione | A cosa serve |
|---|---|---|
| `cmd/...` | HA → pannello | comandi: apri, parla, risveglia, ricarica config |
| `chiamata`, `apertura`, `evento` | pannello → HA | cosa è accaduto al cancello |
| `responder/audio`, `responder/video`, `talkback/audio` | nei due versi | la conversazione |
| `nfc/...`, `volti/...`, `guest_pins/...` | nei due versi | anagrafiche: badge, volti, PIN ospiti |
| `health`, `status`, `logs`, `audit`, `anomaly` | pannello → HA | diagnostica e registro |

L'elenco esatto dei topic sta in `installer-rpi/app/modules/mqtt_client.py` e
nei pyscript che li ascoltano: è lì che va guardato, perché una tabella scritta
a mano si scolla dal codice al primo topic nuovo.

## Cosa l'installer non fa, e perché

- **non installa gli addon**: su HAOS passano dall'UI o dall'API del supervisor
  con un token dedicato, che è un altro giro di autenticazione;
- **non installa HACS**: la sua prima installazione è interattiva e vuole
  un'autenticazione GitHub;
- **non tocca i certificati**: restano al setup di HA con DuckDNS e Let's
  Encrypt;
- **non crea gli helper**: `input_text`, `input_select` e `input_boolean` li
  definiscono i package, quindi arrivano col riavvio.
