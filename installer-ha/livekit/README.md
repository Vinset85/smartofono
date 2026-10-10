# LiveKit + Caddy Edge per Videocitofono

Stack media-server SFU + reverse proxy TLS unificato.

## Architettura

```
                 (WAN - internet pubblico)
                          |
                          | TCP 443 / TCP 80 / UDP 8100 / TCP 7881
                          | (4 porte SINGOLE, nessun range)
                          v
              +--------------------------+
              |  Router casa (port-fwd)  |
              +-----------+--------------+
                          |
                          v  (LAN 192.168.1.0/24)
              +--------------------------+
              | mini-PC HA OS 1.160      |
              |                          |
              | :443  Caddy edge (TLS)   |---> /              -> :8123 HA
              | :80   Caddy redirect     |     /livekit/*     -> :7880 livekit
              |                          |     /livekit-token -> :8081 issuer
              | :8123 HA (HTTPS interno) |
              | :7880 LiveKit Server     |
              | :7881 LiveKit ICE/TLS    |
              | :8081 Token issuer       |
              | :8100 UDP RTP/RTCP mux   | (single-port mode)
              +--------------------------+
```

Tutti i client (tablet di casa, telefono fuori casa via HA Companion, RPi
videocitofono) parlano un solo origin pubblico:

- **Tablet/telefono**: `https://casa-esempio.duckdns.org`
  - frontend HA: `/`
  - LiveKit signaling: `wss://.../livekit/rtc`
  - Token JWT: `https://.../livekit-token/token`
- **RPi (LAN-only)**: parla in chiaro al miniPC HA per evitare il giro di Caddy
  - Token: `http://192.168.1.160:8081/token` (`prefer_lan: true`)
  - LiveKit ws: `ws://192.168.1.160:7880`

## File

| File | Ruolo |
|------|-------|
| `Caddyfile` | Reverse proxy edge: HA + LiveKit + token issuer su 1 origin |
| `docker-compose.yml` | Stack 3 container: livekit, token-issuer, caddy |
| `livekit.yaml` | Config LiveKit Server (porte, key/secret, room policy, RTC) |
| `start.sh` | Deploy idempotente via `docker run` (HAOS non ha docker-compose) |
| `token_issuer/issuer.py` | FastAPI: firma JWT LiveKit con prefer_lan toggle |

## Pre-requisiti host HA OS

1. **Cert TLS validi** in `/mnt/data/supervisor/ssl/{fullchain,privkey}.pem`
   gestiti dall'addon **Duck DNS** di HA (`casa-esempio.duckdns.org`).
   Se non li hai, decommenta la sezione `TLS-MANAGED-BY-CADDY` nel `Caddyfile`
   per delegare a Caddy il rinnovo via Let's Encrypt http-01.

2. **Port-forward sul router** (verso `192.168.1.160`): solo **4 porte
   singole**, nessun intervallo. Il router casa non supporta range e accetta
   solo porte ≤ 8191; questa configurazione rispetta entrambi i vincoli.

   | WAN | LAN | Protocollo | Uso |
   |---|---|---|---|
   | 443  | 443  | TCP | HTTPS Caddy (HA + LiveKit signaling + token) |
   | 80   | 80   | TCP | redirect → 443 (opzionale) |
   | 8100 | 8100 | UDP | LiveKit RTP/RTCP **single-port mux** (tutti i partecipanti) |
   | 7881 | 7881 | TCP | LiveKit ICE/TLS fallback (reti che bloccano UDP) |

   > **Single-port mux**: LiveKit Server (≥ v1.x) sa multiplexare TUTTO il
   > traffico media RTP/RTCP di tutti i partecipanti su una sola porta UDP
   > (`rtc.udp_port: 8100` in `livekit.yaml`). Le sessioni vengono
   > demultiplexate internamente via STUN username + SSRC. Performance
   > equivalenti al range mode per il nostro caso d'uso (max ~4 partecipanti
   > simultanei). Vedi `livekit.yaml`, sezione `rtc.udp_port`.

3. **Hairpin NAT abilitato** sul router (default su consumer router moderni).
   Permette ai tablet di casa di risolvere `casa-esempio.duckdns.org` → IP WAN
   → router → 192.168.1.160 senza split-DNS.

   Se il router non supporta hairpin, configura split-DNS sul router stesso
   o sul DHCP: `casa-esempio.duckdns.org A 192.168.1.160`.

4. **`addon Advanced SSH & Web Terminal`** attivo per il deploy.

## Deploy

Dal repo, sul Mac:

```bash
cd installer-ha
HA_PASS='LA_TUA_PASSWORD_HA' ./scripts/deploy-livekit-stack.sh
```

Lo script:

1. SCP della cartella `installer-ha/livekit/` in `/tmp/livekit/` su HA host
2. Install in `/mnt/data/supervisor/addons/local/livekit/` (path persistente HAOS)
3. Lancia `start.sh` che fa `docker run` dei 3 container in `network=host`
4. SCP di `installer-ha/www/vc-livekit.js` in `/config/www/`
5. Verifica health endpoints

## Verifica post-deploy

```bash
# LAN (interna):
curl -k https://192.168.1.160/livekit-token/health
curl http://192.168.1.160:8081/health
curl http://192.168.1.160:7880/

# WAN (dal cellulare in 4G o dal Mac in tethering):
curl https://casa-esempio.duckdns.org/livekit-token/health
# atteso: {"ok":true,"ws_url":"wss://casa-esempio.duckdns.org/livekit/rtc","ws_url_lan":"ws://192.168.1.160:7880"}
```

Browser di un tablet (DevTools console su `https://casa-esempio.duckdns.org`):

```js
vcLK.diagnostics()
// { secure: true, proto: "https:", origin: "https://casa-esempio.duckdns.org",
//   hasGUM: true, tokenUrl: ".../livekit-token/token",
//   wsUrl: "wss://casa-esempio.duckdns.org/livekit/rtc", sdkLoaded: false,
//   active: false }
```

Se `secure: false` o `hasGUM: false`: il tablet sta accedendo a HA via HTTP/IP nudo invece che dominio HTTPS. Aggiorna il bookmark / Fully Kiosk start URL.

## Configurazione tablet / telefono

| Device | URL HA da impostare |
|---|---|
| Tablet Fully Kiosk in casa | `https://casa-esempio.duckdns.org` |
| Telefono fuori casa (HA Companion) | `https://casa-esempio.duckdns.org` come "External URL" |
| RPi videocitofono (interno) | nessuna config: usa LAN diretta `192.168.1.160:8081/7880` |

Per l'app HA Companion: in `Impostazioni → Companion App → Server → URL` mettere SOLO l'External URL HTTPS. Niente Internal URL (lascia la stringa vuota): cosi' anche da casa l'app passa per Caddy/HTTPS, identico a quando si è fuori. Riduce edge case.

## Credenziali

`livekit.yaml`:
- API key: `videocitofono`
- API secret: `SOSTITUISCI_CON_IL_TUO_LIVEKIT_API_SECRET`

⚠️ Le credenziali sono in chiaro nel container `token-issuer` come ENV. Per
ruotarle: `openssl rand -hex 32`, aggiorna `livekit.yaml` (`keys:`) e
`docker-compose.yml`/`start.sh` (`LIVEKIT_API_SECRET`), poi `start.sh` (riavvia
i container).

## Troubleshooting

**Cert mismatch sul tablet** (warning "non sicuro"): il tablet sta accedendo
a `https://192.168.1.160` (IP) ma il cert e' valido per `casa-esempio.duckdns.org`.
Soluzioni:
- accedere via dominio (richiede hairpin NAT funzionante)
- importare cert come trusted nel browser/Fully Kiosk
- aggiungere `192.168.1.160` come SAN nel cert (richiede LE non standard)

**Caddy non parte (`bind: address already in use`)**: il miniPC HA ha gia'
qualcosa sulla 443. Probabilmente l'addon `Nginx Proxy Manager` o un Caddy
precedente. Spegnili o cambia la porta esposta in `Caddyfile` (es. `:8443`)
e aggiorna il port-forward.

**LiveKit `use_external_ip: true` non risolve correttamente**: succede in
NAT doppio (router ISP + router casa). Hardcoded l'IP pubblico in
`livekit.yaml` con `external_ip: <IP-PUBBLICO>` o usa STUN custom.

**`vcLK.diagnostics()` mostra `secure: false` su LAN**: il tablet usa ancora
`http://192.168.1.160:8123`. Cambia start URL.

**WHIP/legacy uplink che fallisce con `getUserMedia undefined`**: e' il
sintomo originale; significa che il tablet apre HA in HTTP. Step A
(questo deploy) lo risolve forzando HTTPS via Caddy edge.
