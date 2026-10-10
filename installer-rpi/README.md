# Videocitofono — Postazione Esterna (Raspberry Pi 5)

Applicazione GUI Kivy per il pannello esterno del videocitofono. Gestisce:

- Pulsanti chiamata per nominativo (Famiglia X, Appartamento Y, ...)
- Apertura via **PIN** numerico (hash bcrypt + lockout)
- Apertura via **riconoscimento facciale** (UI + camera preview, modulo recognizer attualmente stub)
- Schermate placeholder per **impronta digitale** e **NFC** (in attesa hardware)
- **Gestione luminosità adattiva**: schermo a luminosità ridotta a riposo, piena luminosità su tocco o **rilevamento movimento** dalla camera
- **Screensaver** con orologio dopo inattività (risvegliato anche dal movimento)
- Pubblicazione eventi MQTT verso Home Assistant
- Chiamata diretta script HA via REST API

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
│   │   ├── ha_client.py              # REST -> Home Assistant
│   │   ├── pin_manager.py            # bcrypt + lockout
│   │   ├── face_recognition_stub.py  # placeholder face recognizer
│   │   └── camera.py                 # picamera2 (preferito) / opencv
│   ├── screens/
│   │   ├── home.py
│   │   ├── calling.py
│   │   ├── pin.py
│   │   ├── face.py
│   │   └── placeholders.py           # finger, nfc, result, screensaver
│   └── assets/                       # icone, avatar, placeholder camera
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
| `home`        | Header + lista campanelli + 4 metodi accesso (PIN/Volto/Impronta/NFC)          |
| `calling`     | Chiamata in corso (preview camera locale, timer, annulla, MQTT publish)        |
| `pin`         | Tastierino numerico, verifica bcrypt, lockout dopo N tentativi                 |
| `face`        | Preview camera + scan continua (recognizer attualmente stub)                   |
| `finger`      | Placeholder UI (HW non installato)                                             |
| `nfc`         | Placeholder UI (HW non installato)                                             |
| `result`      | Esito accesso (✓/✗) con auto-return                                            |
| `screensaver` | Orologio + data dopo `screensaver_timeout_sec` (default 60s)                   |

## Eventi MQTT pubblicati

| Topic                        | Payload                                                                  |
| ---------------------------- | ------------------------------------------------------------------------ |
| `videocitofono/chiamata`     | `{"stato":"chiamata_in_corso","campanello":"famiglia_rossi"}`         |
| `videocitofono/chiamata`     | `{"stato":"annullata","campanello":"famiglia_rossi"}`                 |
| `videocitofono/apertura`     | `{"metodo":"pin","utente":"Admin","scope":"porta"}`                      |
| `videocitofono/evento`       | `{"tipo":"boot","dati":{"versione":"0.1.0"}}`                            |

> Sul lato HA queste chiamate verranno mappate ad `automation.chiamata_videocitofono` (già esistente, deve essere aggiornata per leggere `campanello` da payload JSON in fase 4).

## Roadmap

- [x] Scaffold UI completa (tutte le schermate)
- [x] PIN con bcrypt + lockout
- [x] MQTT publish chiamata/apertura
- [x] HA REST chiamata script porta/cancello
- [x] Camera preview (picamera2 + fallback opencv)
- [x] Screensaver
- [x] Brightness adattiva (idle/active) con backlight sysfs
- [x] Motion detector da camera per wake-up automatico
- [ ] Recognizer facciale reale (face_recognition o opencv-LBPH)
- [ ] Driver fingerprint (R503 / GROW R307 - in attesa scelta modello)
- [ ] Driver NFC (PN532 I2C - in attesa scelta modello)
- [ ] Schermata Admin (gestione utenti, enrollment)
- [ ] Audio bidirezionale (richiede go2rtc + microfono RPi)

## Comportamento luminosità / risveglio

| Evento                                    | Effetto                                                       |
| ----------------------------------------- | ------------------------------------------------------------- |
| Boot                                      | Luminosità piena                                              |
| Tocco schermo                             | Luminosità piena + reset timer idle                           |
| Movimento davanti alla camera             | Luminosità piena + reset timer idle (+ wake da screensaver)   |
| Inattività `idle_dim_sec` (default 20s)   | Riduce a `brightness_idle_pct` (default 25%)                  |
| Inattività `screensaver_timeout_sec` (60s)| Mostra screensaver con orologio                               |
| Chiamata in corso (`calling`)             | Forza luminosità piena, disabilita idle/screensaver           |

Configurabile in `config.yaml` sezioni `ui` e `motion`:

```yaml
ui:
  idle_dim_sec: 20
  screensaver_timeout_sec: 60
  brightness_idle_pct: 25
  brightness_active_pct: 100

motion:
  enabled: true
  pixel_thresh: 25          # quanto deve cambiare un pixel per "contare"
  area_thresh_pct: 1.5      # % minima di pixel cambiati per generare evento
  cooldown_sec: 1.5
  tick_hz: 5                # 5 valutazioni/sec (basso CPU)
  wake_screensaver: true    # movimento riporta dalla schermata screensaver
```

> **Backlight**: `install.sh` configura una udev rule + aggiunge l'utente al gruppo `video`,
> permettendo la scrittura di `/sys/class/backlight/<dev>/brightness` senza sudo.
> Su display HDMI senza interfaccia backlight standard, il modulo cade su `vcgencmd display_power`
> (solo on/off) o no-op (solo log).

## Note tecniche

- **Font emoji**: i pulsanti usano emoji unicode (🔔, ⌫, ✓, ✗). Servono `fonts-noto-color-emoji` (installati dal `install.sh`).
- **Cursore mouse**: nascosto con `Window.show_cursor=False` se `ui.cursor=false`.
- **Risoluzione**: schermo 5.5" tipico 1280×720 o 1920×1080. Ricalibrare `dp` se necessario tramite `Config.set('graphics', 'density', ...)`.
- **Camera live HA dashboard**: rimane gestita da `go2rtc` (stream `pi5cam_h264`). La `CameraPreview` di questa app è solo per preview UI locale (chiamata + face).
