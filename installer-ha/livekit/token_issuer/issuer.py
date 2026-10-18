"""Token issuer LiveKit per il videocitofono.

Espone un endpoint HTTP che firma JWT per i partecipanti (Pi e browser HA).
Il client (HA o Pi) chiama POST /token con identity+room e ottiene un
JWT da passare a `room.connect()`.

Endpoints:
    GET  /health         -> {ok, ws_url, ws_url_lan}
    POST /token          -> {token, ws_url, room, identity}
        body: {identity, room, name?, ttl_seconds?, can_publish?,
               can_subscribe?, prefer_lan?}
        - prefer_lan=true: il client chiede esplicitamente il ws_url
          interno LAN (es. il RPi che parla al miniPC HA).
        - default false: ritorna l'URL pubblico passante per Caddy
          (https same-origin, nessun mixed-content).
    POST /egress/start   -> {egress_id, filename, url}
    POST /egress/stop    -> {stopped: [...]}
        Registrazione MP4 della chiamata (vedi ../egress.yaml). Chiamati da
        HA via rest_command allo squillo e alla fine chiamata. Richiedono
        l'header X-VC-Egress con EGRESS_SECRET.

Sicurezza: POST /token richiede TOKEN_ISSUER_SECRET (header X-VC-Token).
Senza secret l'issuer risponde 503, salvo ALLOW_INSECURE_TOKEN_ISSUER=1
(solo lab). WAN passa da Caddy in HTTPS.

Gli endpoint /egress/* invece sono sempre autenticati con EGRESS_SECRET e
bloccati da Caddy sulla WAN: avviano scritture su disco, quindi non possono
restare aperti come /token.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

import aiohttp
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from livekit import api

LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]
TOKEN_ISSUER_SECRET = os.environ.get("TOKEN_ISSUER_SECRET", "").strip()
ALLOW_INSECURE_TOKEN_ISSUER = os.environ.get(
    "ALLOW_INSECURE_TOKEN_ISSUER", ""
).strip().lower() in ("1", "true", "yes")
# URL pubblico (passa da Caddy edge :443, wss same-origin con HA frontend).
## NB: il path NON deve includere `/rtc` finale. Il client SDK livekit-client
## 2.x appende `/rtc` da solo a wsUrl quando apre la signaling websocket
## (vedi SignalClient: `${host}/rtc?access_token=...`). Se impostiamo qui
## `wss://h/livekit/rtc`, il client tenta `wss://h/livekit/rtc/rtc?...` e
## il livekit-server risponde 404 ("could not establish signal connection:
## 404 page not found"). Il Caddyfile usa `handle_path /livekit/*` che
## strippa il prefisso, quindi /livekit/rtc?... diventa upstream /rtc?...
## che e' esattamente l'endpoint signaling del server.
LIVEKIT_HOST = os.environ.get("LIVEKIT_HOST", "wss://casa-esempio.duckdns.org/livekit")
# URL LAN interno (server LiveKit raggiungibile direttamente in LAN, no TLS).
LIVEKIT_HOST_LAN = os.environ.get("LIVEKIT_HOST_LAN", "ws://192.168.1.160:7880")

# --- Egress (registrazione chiamate) --------------------------------------
EGRESS_SECRET = os.environ.get("EGRESS_SECRET", "").strip()
# API REST (twirp) del livekit-server: loopback, siamo in network host.
LIVEKIT_API_URL = os.environ.get("LIVEKIT_API_URL", "http://127.0.0.1:7880")
# Mount di output DENTRO il container egress (vedi start.sh: bind su
# /config/www/videocitofono lato HA). Non e' un path di questo container.
EGRESS_OUTPUT_DIR = os.environ.get("EGRESS_OUTPUT_DIR", "/out").rstrip("/")
EGRESS_ROOM = os.environ.get("EGRESS_ROOM", "videocitofono")
# Identity del visitatore: il Pi entra in room con questa identity e pubblica
# camera+mic gia' da CallingScreen (VC_LK_PUBLISH=1 nel systemd del Pi).
EGRESS_IDENTITY = os.environ.get("EGRESS_IDENTITY", "rpi")
# URL pubblico del file per HA: /config/www/<x> e' servito come /local/<x>.
EGRESS_URL_PREFIX = os.environ.get(
    "EGRESS_URL_PREFIX", "/local/videocitofono")
# Nessuno slash o punto ammesso nel nome: il filepath finale e' costruito qui,
# il client non puo' scrivere fuori dalla cartella delle registrazioni.
_FILENAME_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}\.mp4$")
# Le API egress non devono mai bloccare l'automation HA della chiamata.
_EGRESS_TIMEOUT = aiohttp.ClientTimeout(total=8)

app = FastAPI(title="Videocitofono LiveKit Token Issuer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class TokenRequest(BaseModel):
    identity: str
    room: str
    name: Optional[str] = None
    ttl_seconds: int = 3600
    can_publish: bool = True
    can_subscribe: bool = True
    prefer_lan: bool = False


class TokenResponse(BaseModel):
    token: str
    ws_url: str
    room: str
    identity: str


class EgressStartRequest(BaseModel):
    # HA passa il nome file cosi' il registro chiamate e la registrazione
    # restano allineati sullo stesso timestamp. Se assente, lo generiamo qui.
    filename: Optional[str] = None
    room: Optional[str] = None
    identity: Optional[str] = None


class EgressStartResponse(BaseModel):
    egress_id: str
    filename: str
    url: str


class EgressStopRequest(BaseModel):
    room: Optional[str] = None
    # Senza egress_id fermiamo tutte le registrazioni attive della room: cosi'
    # HA non deve memorizzare l'id fra squillo e fine chiamata.
    egress_id: Optional[str] = None


class EgressStopResponse(BaseModel):
    stopped: list[str]


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "ws_url": LIVEKIT_HOST,
        "ws_url_lan": LIVEKIT_HOST_LAN,
        "egress_enabled": bool(EGRESS_SECRET),
    }


@app.post("/token", response_model=TokenResponse)
def issue_token(
    req: TokenRequest,
    x_vc_token: Optional[str] = Header(default=None, alias="X-VC-Token"),
) -> TokenResponse:
    if not TOKEN_ISSUER_SECRET:
        if not ALLOW_INSECURE_TOKEN_ISSUER:
            raise HTTPException(503, "TOKEN_ISSUER_SECRET non configurato")
    elif not x_vc_token or x_vc_token != TOKEN_ISSUER_SECRET:
        raise HTTPException(401, "token issuer non autorizzato")
    if not req.identity or not req.room:
        raise HTTPException(400, "identity e room obbligatori")
    grants = api.VideoGrants(
        room_join=True,
        room=req.room,
        can_publish=req.can_publish,
        can_subscribe=req.can_subscribe,
        can_publish_data=True,
    )
    builder = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(req.identity)
        .with_name(req.name or req.identity)
        .with_grants(grants)
        .with_ttl(_seconds_to_ttl(req.ttl_seconds))
    )
    ws_url = LIVEKIT_HOST_LAN if req.prefer_lan else LIVEKIT_HOST
    return TokenResponse(
        token=builder.to_jwt(),
        ws_url=ws_url,
        room=req.room,
        identity=req.identity,
    )


def _seconds_to_ttl(seconds: int):
    from datetime import timedelta
    return timedelta(seconds=max(60, seconds))


# --------------------------- egress -----------------------------------------


def _require_egress_auth(secret: Optional[str]) -> None:
    if not EGRESS_SECRET:
        raise HTTPException(503, "egress disabilitato: EGRESS_SECRET non impostato")
    if not secret or secret != EGRESS_SECRET:
        raise HTTPException(401, "egress non autorizzato")


def _safe_filename(name: Optional[str]) -> str:
    """Nome file whitelisted, senza path: l'egress scrive solo in OUTPUT_DIR."""
    if not name:
        return datetime.now().strftime("%Y%m%d-%H%M%S") + ".mp4"
    candidate = name.strip().replace("\\", "/").split("/")[-1]
    if not candidate.endswith(".mp4"):
        candidate += ".mp4"
    if not _FILENAME_RE.match(candidate):
        raise HTTPException(400, f"filename non valido: {name}")
    return candidate


def _lk_api() -> api.LiveKitAPI:
    return api.LiveKitAPI(
        LIVEKIT_API_URL,
        LIVEKIT_API_KEY,
        LIVEKIT_API_SECRET,
        timeout=_EGRESS_TIMEOUT,
    )


async def _stop_active_egress(lkapi: api.LiveKitAPI, room: str) -> list[str]:
    res = await lkapi.egress.list_egress(
        api.ListEgressRequest(room_name=room, active=True))
    stopped: list[str] = []
    for info in res.items:
        try:
            await lkapi.egress.stop_egress(
                api.StopEgressRequest(egress_id=info.egress_id))
            stopped.append(info.egress_id)
        except Exception:
            # Un egress terminato da solo (il Pi ha lasciato la room) risponde
            # errore su stop: non e' una condizione di errore per noi.
            pass
    return stopped


@app.post("/egress/start", response_model=EgressStartResponse)
async def egress_start(
    req: EgressStartRequest,
    x_vc_egress: Optional[str] = Header(default=None, alias="X-VC-Egress"),
) -> EgressStartResponse:
    """Avvia la registrazione MP4 del visitatore (participant egress).

    Si puo' chiamare appena il citofono suona, prima che il Pi abbia
    pubblicato: l'egress entra in room, attende le track e inizia a
    registrare appena arriva la prima. Si ferma da solo quando il Pi esce.
    """
    _require_egress_auth(x_vc_egress)
    room = req.room or EGRESS_ROOM
    identity = req.identity or EGRESS_IDENTITY
    filename = _safe_filename(req.filename)
    lkapi = _lk_api()
    try:
        # La room DEVE esistere prima dello start, altrimenti il server
        # risponde 404 "requested room does not exist": l'egress non fa
        # auto-create, lo fa solo il join di un partecipante. E fra due
        # chiamate la room non esiste (empty_timeout la chiude 60s dopo che
        # si e' svuotata), mentre il Pi entra in room 1-2s DOPO lo squillo.
        # Creandola qui, l'egress entra e aspetta il visitatore.
        await lkapi.room.create_room(api.CreateRoomRequest(name=room))
        # Doppia suonata o run precedente annullata (l'automation HA della
        # chiamata e' mode: restart): chiudiamo cio' che e' rimasto appeso,
        # altrimenti si accumulano egress attivi sulla stessa room.
        await _stop_active_egress(lkapi, room)
        info = await lkapi.egress.start_participant_egress(
            api.ParticipantEgressRequest(
                room_name=room,
                identity=identity,
                file_outputs=[
                    api.EncodedFileOutput(
                        file_type=api.EncodedFileType.MP4,
                        filepath=f"{EGRESS_OUTPUT_DIR}/{filename}",
                        # Senza questo, accanto all'mp4 compare un .json che
                        # il purge del registro non conosce e non pulisce.
                        disable_manifest=True,
                    )
                ],
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"start egress fallito: {e}")
    finally:
        await lkapi.aclose()
    return EgressStartResponse(
        egress_id=info.egress_id,
        filename=filename,
        url=f"{EGRESS_URL_PREFIX}/{filename}",
    )


@app.post("/egress/stop", response_model=EgressStopResponse)
async def egress_stop(
    req: EgressStopRequest,
    x_vc_egress: Optional[str] = Header(default=None, alias="X-VC-Egress"),
) -> EgressStopResponse:
    """Chiude la registrazione e finalizza l'MP4 (moov atom scrivibile).

    Il file resta inutilizzabile finche' l'egress non termina, quindi HA deve
    chiamare questo endpoint a fine chiamata prima di mostrare il video.
    """
    _require_egress_auth(x_vc_egress)
    room = req.room or EGRESS_ROOM
    lkapi = _lk_api()
    try:
        if req.egress_id:
            await lkapi.egress.stop_egress(
                api.StopEgressRequest(egress_id=req.egress_id))
            stopped = [req.egress_id]
        else:
            stopped = await _stop_active_egress(lkapi, room)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"stop egress fallito: {e}")
    finally:
        await lkapi.aclose()
    return EgressStopResponse(stopped=stopped)
