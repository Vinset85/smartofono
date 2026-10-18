# Videocitofono — Postazione Esterna (Raspberry Pi 5)

Applicazione GUI Kivy per il pannello esterno del videocitofono. Gestisce:

- Pulsanti chiamata per nominativo (Famiglia X, Appartamento Y, ...)
- Apertura via **PIN** numerico (hash bcrypt + lockout)
- Apertura via **riconoscimento facciale** (ArcFace, con dlib come alternativa)
- Apertura via **badge NFC** (PN532 su USB)
- **Relè locale su GPIO12/13**: PIN, NFC e volto aprono anche se Home Assistant è giù
- **Gestione luminosità adattiva**: schermo a luminosità ridotta a riposo, piena luminosità su tocco o **rilevamento movimento** dalla camera
- **Screensaver** con orologio dopo inattività (risvegliato anche dal movimento)
- Pubblicazione eventi MQTT verso Home Assistant (`cmd_secret` sui comandi)
- Videochiamata **LiveKit** (camera + mic, AEC PipeWire)
- Chiamata diretta script HA via REST API (best-effort: l'apertura non dipende da HA)

## Struttura

```
installer-rpi/
├── app/
│   ├── main.py                       # entry point Kivy
│   ├── videocitofono.kv              # styling tutte le schermate
│   ├── requirements.txt
│   ├── config/
│   │   └── config.example.yaml       # copiare in config.yaml
│   ├── modules/
│   │   ├── config.py                 # caricamento YAML
│   │   ├── mqtt_client.py            # paho-mqtt publisher
│   │   ├── livekit_client.py         # sessione WebRTC verso HA
│   │   ├── audio_backchannel.py      # talkback + AEC
│   │   ├── cmd_auth.py               # token sui comandi MQTT
│   │   ├── ha_client.py              # REST -> Home Assistant
│   │   ├── pin_manager.py            # bcrypt + lockout
│   │   ├── face_recognition_stub.py  # recognizer dlib (il nome e' storico)
│   │   ├── face_arcface.py           # recognizer ArcFace, quello in uso
│   │   └── camera.py                 # picamera2 (preferito) / opencv
│   ├── screens/
│   │   ├── home.py
│   │   ├── calling.py
│   │   ├── pin.py
│   │   ├── face.py
│   │   └── placeholders.py           # result, screensaver
│   └── assets/                       # icone, avatar, placeholder camera
├── tests/
│   └── test_smoke.py                 # auth, PIN ospite, face, backup
├── systemd/
│   └── videocitofono.service         # autostart su graphical.target
├── scripts/
│   ├── install.sh                    # installer one-shot su Pi
│   ├── deploy.sh                     # rsync + install + riavvio da Mac
│   └── merge_nfc_config.py           # merge sezione nfc sul Pi (solo se assente)
└── README.md
```

## Installazione su RPi5

### Deploy automatico (Mac → Pi)

Con il Raspberry acceso e raggiungibile via SSH (chiave già configurata):

```bash
cd installer-rpi
./scripts/deploy.sh
```

Opzionale: `DEPLOY_HOST=192.168.1.x DEPLOY_USER=vinset ./scripts/deploy.sh`

Lo script sincronizza la cartella, esegue `install.sh` (venv, pip, copia in `/opt/videocitofono`), aggiunge la sezione `nfc` da `config.example.yaml` se manca in `config.yaml`, e riavvia `videocitofono.service`.

### Installazione manuale sul Pi

```bash
rsync -avz installer-rpi/ vinset@192.168.1.52:/home/vinset/videocitofono-installer/
ssh vinset@192.168.1.52
cd /home/vinset/videocitofono-installer
./scripts/install.sh
```

Lo script:
- installa pacchetti apt (python3, sdl2, picamera2, font emoji, ecc.)
- copia app in `/opt/videocitofono/app`
- crea venv Python in `/opt/videocitofono/venv` (con `--system-site-packages` per picamera2)
- copia `config.example.yaml` in `config.yaml` se mancante
- installa service systemd `videocitofono.service`

## Prima configurazione

Modificare `/opt/videocitofono/app/config/config.yaml`:

1. **`mqtt.broker`** — di solito `localhost` (mosquitto sulla stessa RPi)
2. **`home_assistant.token`** — Long-Lived Access Token da HA
   (Profilo → in fondo → "Crea token")
3. **`campanelli`** — elenco famiglie/appartamenti
4. **`pin.utenti_bootstrap`** — PIN iniziali (verranno hashati al primo avvio)
5. (opzionale) percorsi script HA `script_apri_porta` / `script_apri_cancello`

## Test manuale

```bash
cd /opt/videocitofono/app
../venv/bin/python3 main.py
```

Per uscire dal fullscreen in test: `Esc` (o disabilitare `ui.fullscreen` in config).

## Avvio service

```bash
sudo systemctl start videocitofono.service
sudo systemctl status videocitofono.service
journalctl -u videocitofono -f
```

## Schermate

| Nome          | Funzione                                                                       |
| ------------- | ------------------------------------------------------------------------------ |
| `home`        | Header + lista campanelli + metodi accesso (PIN/Volto/NFC)                     |
| `calling`     | Chiamata in corso (preview camera locale, timer, annulla, MQTT publish)        |
| `pin`         | Tastierino numerico, verifica bcrypt, lockout dopo N tentativi                 |
| `face`        | Preview camera + scansione continua (ArcFace o dlib)                          |
| `nfc`         | Lettura badge dal PN532, con cooldown                                          |
| `result`      | Esito accesso (✓/✗) con auto-return                                            |
| `screensaver` | Orologio + data dopo `screensaver_timeout_sec` (default 60s)                   |

## Apertura senza Home Assistant

PIN, NFC e volto si verificano sul Raspberry. L'impulso esce in locale,
**GPIO12 pin 32** (porta) e **GPIO13 pin 33** (cancello), 1 s, 3,3 V, massa
pin 30/34. HA riceve REST e MQTT solo se è raggiungibile: se è giù l'apertura
avviene lo stesso. Configurazione in `relay:` di `config.yaml`.

GPIO12 è solo il comando. I 12 V della serratura possono uscire dall'header
dell'HAT PoE (F), così in blackout restano sotto l'UPS dello switch: schema
e specifiche della serratura in
[hardware/SCHEMA-SERRATURA.md](../hardware/SCHEMA-SERRATURA.md).

## Eventi MQTT pubblicati

| Topic                        | Payload                                                                  |
| ---------------------------- | ------------------------------------------------------------------------ |
| `videocitofono/chiamata`     | `{"stato":"chiamata_in_corso","campanello":"famiglia_rossi"}`         |
| `videocitofono/chiamata`     | `{"stato":"annullata","campanello":"famiglia_rossi"}`                 |
| `videocitofono/apertura`     | `{"metodo":"pin","utente":"Admin","scope":"porta"}`                      |
| `videocitofono/evento`       | `{"tipo":"boot","dati":{"versione":"1.5.1"}}`                            |

> Sul lato HA li raccoglie `automation.chiamata_videocitofono`, nel package `installer-ha/packages/automations.yaml.fixed`.

## Roadmap

- [x] UI completa (tutte le schermate)
- [x] PIN con bcrypt + lockout
- [x] MQTT publish chiamata/apertura
- [x] HA REST chiamata script porta/cancello
- [x] Relè GPIO locale (apertura anche con HA giù)
- [x] Camera preview (picamera2 + fallback opencv)
- [x] Screensaver
- [x] Brightness adattiva (idle/active). Il pannello e' OLED e non ha
      backlight: la attenua un overlay nero in alpha, che su un emissivo e'
      fisicamente la cosa giusta
- [x] Motion detector da camera per wake-up automatico
- [x] Recognizer facciale reale (ArcFace, con dlib come alternativa)
- [x] Driver NFC (PN532, su USB e non su I2C)
- [x] Schermata Admin (gestione utenti, enrollment)
- [x] Audio bidirezionale (LiveKit)

## Comportamento luminosità / risveglio

| Evento                                    | Effetto                                                       |
| ----------------------------------------- | ------------------------------------------------------------- |
| Boot                                      | Luminosità piena                                              |
| Tocco schermo                             | Luminosità piena + reset timer idle                           |
| Movimento davanti alla camera             | Luminosità piena + reset timer idle (+ wake da screensaver)   |
| Inattività `idle_dim_sec` (default 20s)   | Riduce a `brightness_idle_pct` (default 20%)                  |
| Inattività `screensaver_timeout_sec` (60s)| Mostra screensaver con orologio                               |
| Inattività `display_off_sec` (180s)       | Spegne l'HDMI (`wlr-randr --off`)                             |
| Chiamata in corso (`calling`)             | Forza luminosità piena, disabilita idle/screensaver           |

Configurabile in `config.yaml` sezioni `ui` e `motion`:

```yaml
ui:
  idle_dim_sec: 20
  screensaver_timeout_sec: 60
  display_off_sec: 180
  brightness_idle_pct: 20
  brightness_active_pct: 100

motion:
  enabled: true
  pixel_thresh: 25          # quanto deve cambiare un pixel per "contare"
  area_thresh_pct: 5.0      # % minima di pixel cambiati per generare evento
  cooldown_sec: 2.0
  tick_hz: 1                # 1 valutazione/sec (picamera a basso consumo)
  wake_screensaver: true    # movimento riporta dalla schermata screensaver
```

> **Backlight**: `install.sh` configura una udev rule + aggiunge l'utente al gruppo `video`,
> permettendo la scrittura di `/sys/class/backlight/<dev>/brightness` senza sudo.
> Su display HDMI senza interfaccia backlight standard, il modulo cade su `vcgencmd display_power`
> (solo on/off) o no-op (solo log).

## Schermata Admin

Dalla Home, 5 tocchi in 3 secondi sulla fascia alta (~12%) aprono il PIN.
Solo un utente con `ruolo: admin` entra in Admin (iscrizione/revoca PIN, NFC, volto). Un PIN ospite o utente normale non apre la porta in questo percorso.

Reed antimanomissione GPIO27: `tamper.enabled` resta `false` finché il contatto non è montato.

## Soak 48 h dopo ciclo PoE

Dopo un distacco/riattacco PoE, lasciare l'impianto 48 h e verificare: servizio `videocitofono` attivo, NFC in ascolto, temperatura < 70 °C, nessun `over-current` USB ripetuto, backup giornaliero presente, HA health `status_summary=ok`.

## Note tecniche

- **Font emoji**: i pulsanti usano emoji unicode (🔔, ⌫, ✓, ✗). Servono `fonts-noto-color-emoji` (installati dal `install.sh`).
- **Cursore mouse**: nascosto con `Window.show_cursor=False` se `ui.cursor=false`.
- **Risoluzione**: schermo 5.5" tipico 1280×720 o 1920×1080. Ricalibrare `dp` se necessario tramite `Config.set('graphics', 'density', ...)`.
- **Camera live HA dashboard**: rimane gestita da `go2rtc` (stream `pi5cam_h264`). La `CameraPreview` di questa app è solo per preview UI locale (chiamata + face).
