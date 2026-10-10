# Installer Home Assistant - Unità interna videocitofono

> Stato: scaffold iniziale. Gli script saranno popolati man mano che la configurazione viene consolidata.

## Prerequisiti

- Home Assistant OS in esecuzione su minipc/x86 (testato su HAOS x86_64)
- Addon **Advanced SSH & Web Terminal** installato e avviato (porta 22, utente `hassio`)
- Addon **Mosquitto broker** installato (oppure broker esterno raggiungibile)
- HACS installato per i custom components (browser_mod, webrtc, pyscript)
- Token "Long-lived access" generato dal profilo utente HA

## Uso (target finale)

Da una macchina di sviluppo (Mac/Linux) con `ssh` e `rsync`:

```bash
cd installer-ha
./install.sh --host 192.168.1.160 --user hassio --token <LLAT>
```

Lo script:
1. Esegue backup di `/config` come snapshot
2. Verifica che gli addon richiesti siano installati e in esecuzione
3. Verifica che i custom components richiesti siano presenti
4. Copia (rsync) `packages/`, `pyscript/`, `www/`, `lovelace/` in `/config/`
5. Crea/aggiorna helper (input_text, input_select, input_boolean) via API REST
6. Aggiorna `configuration.yaml` per includere `packages: !include_dir_named packages`
7. Verifica config con `ha core check`
8. Riavvia HA

## Struttura

```
installer-ha/
├── install.sh                     # entrypoint (da creare)
├── packages/
│   └── videocitofono.yaml         # package autocontenuto
├── pyscript/
│   ├── update_registro_videocitofono.py
│   └── videocitofono.py
├── www/
│   ├── videocitofono/             # cartella video registrazioni
│   ├── placeholder.png
│   ├── minion.mp3
│   └── fanfara.mp3
├── lovelace/
│   └── videocitofono-dashboard.yaml
└── scripts/
    ├── backup.sh
    ├── deploy.sh                  # rsync verso HA
    └── check.sh                   # verifica integrità installazione
```

## Cosa NON fa l'installer (e perché)

- **Non installa addon**: gli addon HAOS vanno installati dall'UI o via API supervisor con token specifico (richiede setup separato)
- **Non installa HACS**: HACS richiede un'installazione iniziale interattiva (autenticazione GitHub)
- **Non gestisce certificati SSL**: lasciato al setup iniziale di HA + Duck DNS + Let's Encrypt

## Helper richiesti (da creare via UI o API)

| Helper | Tipo | Descrizione |
|---|---|---|
| `input_text.chiamate_lette` | input_text (max 255 char) | Lista JSON timestamp letti |
| `input_select.utenti_videocitofono` | input_select | Lista utenti riconosciuti |
| `input_boolean.videocitofono_enroll_mode` | input_boolean | Modalità enrollment attiva |

## Topic MQTT usati

| Topic | Direzione | Payload | Descrizione |
|---|---|---|---|
| `videocitofono/chiamata` | RPi → HA | `chiamata_in_corso` | Trigger chiamata |
| `videocitofono/impronta/match` | RPi → HA | `{"user_id": "...", "score": 95}` | Impronta riconosciuta |
| `videocitofono/nfc/read` | RPi → HA | `{"uid": "...", "user_id": "..."}` | Badge NFC letto |
| `videocitofono/cmd/apri_cancello` | HA → RPi | `ingresso\|strada` | Comando apertura cancello |
| `videocitofono/cmd/enroll_impronta` | HA → RPi | `{"user_id": "..."}` | Avvia enrollment impronta |
| `videocitofono/cmd/enroll_nfc` | HA → RPi | `{"user_id": "..."}` | Avvia enrollment badge NFC |
| `videocitofono/status/online` | RPi → HA (LWT) | `online`/`offline` | Heartbeat / availability |

> Topic provvisori, da consolidare nella fase di design dell'app RPi.

## TODO

- [ ] Definire schema completo entità HA (sensor, binary_sensor, switch, button, camera)
- [ ] Definire dashboard Lovelace (popup chiamata, gestione utenti, storico)
- [ ] Implementare `install.sh`
- [ ] Implementare `backup.sh` e `deploy.sh`
- [ ] Definire helper e scripts.yaml definitivi
- [ ] Migrare configurazione attuale dal file `configuration.yaml` al package autocontenuto
