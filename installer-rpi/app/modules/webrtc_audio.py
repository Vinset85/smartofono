"""WebRTCAudioController: subscribe audio-only su LiveKit room.

Wrapper di compatibilita' che mantiene la stessa API usata da
`main.py` (start/stop/active) ma sotto il cofano usa
`LiveKitSubscribeClient` (livekit-rtc Python SDK) invece di aiortc/WHEP.

Trigger e ruolo invariati:
    MQTT `videocitofono/responder/audio` payload "on"/"off".
    on  -> start() entra in LiveKit room "videocitofono" come `rpi`,
           subscribe SOLO audio. Il browser HA pubblica il microfono
           del rispondente nella stessa room.
    off -> stop() disconnette dalla room e ferma il player ffmpeg
           lato AudioBackchannel.

A differenza del consumer in ConversationScreen, NON consuma il video:
il visitatore RPi resta su CallingScreen con la sola scritta
"Chiamata in corso" e sente la voce del rispondente.

Quando il rispondente HA fa upgrade ad audio+video (preme tasto camera
del popup), questo controller viene fermato e ConversationScreen apre
il proprio LiveKitSubscribeClient con video+audio.
"""
from __future__ import annotations

import logging
from typing import Optional

from .livekit_client import LiveKitSubscribeClient

LOG = logging.getLogger(__name__)


class WebRTCAudioController:
    """Compat shim su LiveKitSubscribeClient (audio-only).

    Il nome storico WebRTC* e' mantenuto per non rompere import esistenti
    in main.py. Tutto il routing audio (mic ducking, ffmpeg EQ, PulseAudio
    sink) e' ancora gestito da AudioBackchannel; questo controller si
    limita a iniettare PCM Opus->s16 nel pipeline.
    """

    def __init__(self, audio_backchannel):
        self._client = LiveKitSubscribeClient(
            audio_backchannel=audio_backchannel,
            on_video_frame=None,  # audio-only
        )

    @property
    def active(self) -> bool:
        return self._client.active

    def start(self) -> None:
        LOG.info("WebRTCAudioController -> LiveKit subscribe audio-only")
        self._client.start()

    def stop(self) -> None:
        LOG.info("WebRTCAudioController stop")
        self._client.stop()
