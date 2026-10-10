"""Schermata Conversazione: mostra il flusso video+audio del rispondente
HA via LiveKit room "videocitofono".

Architettura post-refactor LiveKit (2026-04):
    [browser HA pubblica camera + mic in LiveKit room]
        v
    [LiveKit Server self-hosted su mini-PC HA :7880, SFU]
        v
    [LiveKitSubscribeClient livekit-rtc Python SDK su RPi]
        - audio: AudioStream s16/mono/48k -> AudioBackchannel.feed_webrtc_pcm
                 -> ffmpeg EQ -> PulseAudio ec_sink
        - video: VideoStream RGB24 -> Kivy texture (drop-oldest blit)

Vantaggi vs aiortc/WHEP:
    - Decoder libwebrtc nativo (no pyav: niente freeze H264/VP8)
    - RTCP feedback gestito -> niente encoder stalls lato browser
    - Bandwidth estimation reale -> niente drop fps a 0
    - Riconnessione automatica su packet loss / ICE restart
    - SDK production-grade, stabile su Pi5 ARM64

Pi -> HA video continua a viaggiare separatamente via go2rtc Pi
(RTSP/WHIP) e card custom:webrtc-camera nel popup HA: questa parte
funzionava gia' bene e non e' toccata da questo refactor.

Trigger entry/exit: lo screen viene mostrato/nascosto da
`main.py:_handle_responder_video()` su MQTT
`videocitofono/responder/video` (payload "on"/"off").
"""
from __future__ import annotations

import logging
import os
import threading
import urllib.request
from io import BytesIO
from typing import Optional

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.graphics.texture import Texture
from kivy.properties import StringProperty

from modules.livekit_client import (
    LiveKitSubscribeClient,
    livekit_publish_kwargs_from_config,
)

from .bg_screen import BgScreen

LOG = logging.getLogger(__name__)

# Step B5: publish camera+mic via LiveKit dal RPi. In transizione
# (Step C non ancora completato) il sensore puo' essere tenuto da
# go2rtc-pi: per evitare conflitti, il publish e' opt-in via env var.
# Una volta decommissionato go2rtc-pi (Step C), passare il default a 1
# o esportare VC_LK_PUBLISH=1 in /etc/systemd/.../environment.
_LK_PUBLISH = os.environ.get("VC_LK_PUBLISH", "0") == "1"


# Snapshot JPEG locale dal go2rtc dello stesso RPi: usato per il
# "selfview picture-in-picture" mostrato in alto-dx durante la
# conversazione video. Il visitatore vede come e' inquadrato.
SELFVIEW_URL = "http://127.0.0.1:1984/api/frame.jpeg?src=pi5cam_h264"
SELFVIEW_FPS = 5


class ConversationScreen(BgScreen):
    # Risoluzione attesa del flusso LiveKit dal browser HA (publish
    # camera 480x480). Il blit Kivy adatta in automatico se differente.
    FRAME_W = 480
    FRAME_H = 480

    HOLD_SEC = 3  # durata overlay "Porta aperta" / "Chiamata terminata"
    CLOSE_ARM_SEC = 2.5  # debounce post-transizione del bottone "Chiudi"

    overlay_text = StringProperty("")

    def __init__(self, app_ctx, bg_source: str | None = None, **kw):
        super().__init__(bg_source=bg_source, **kw)
        self.app_ctx = app_ctx
        self._lk: Optional[LiveKitSubscribeClient] = None
        self._hold_event = None  # Clock.schedule_once per chiusura post-overlay
        self._selfview_event = None  # Clock.schedule_interval handle
        self._selfview_inflight = False  # evita fetch concorrenti
        # Backpressure video blit: se il main thread Kivy non riesce a
        # blittare in tempo, accumulare Clock.schedule_once con buffer
        # rgb 690KB ciascuno (480x480x3) satura RAM e ritarda l'UI.
        # Teniamo solo l'ultimo frame e droppiamo i precedenti.
        self._pending_frame = None  # (rgb_bytes, w, h) ultimo da blittare
        self._pending_lock = threading.Lock()
        self._blit_scheduled = False
        # Anti-bounce: il transition CallingScreen -> ConversationScreen
        # avviene quando arriva MQTT chiamata=risposto. Se in quel
        # momento il visitatore stava tappando "Annulla chiamata" della
        # CallingScreen, il release del touch puo' cadere sul bottone
        # "Chiudi chiamata" della ConversationScreen (stessa posizione)
        # chiudendo subito la chiamata. Disarmiamo on_close per i primi
        # CLOSE_ARM_SEC secondi dopo l'enter.
        self._close_armed = False
        self._close_arm_event = None

    # ------- Lifecycle Kivy -------

    def on_pre_enter(self, *_):
        LOG.info("ConversationScreen on_pre_enter -> LiveKit attach video")
        self.overlay_text = ""
        # Disarma il bottone "Chiudi chiamata" per CLOSE_ARM_SEC: evita
        # click propagati dalla CallingScreen (vedi commento nel
        # costruttore).
        self._close_armed = False
        if self._close_arm_event:
            self._close_arm_event.cancel()
        def _arm(*_a):
            self._close_armed = True
            LOG.info("Bottone Chiudi armato")
        self._close_arm_event = Clock.schedule_once(_arm, self.CLOSE_ARM_SEC)
        # Flusso ring->answer: il LiveKit client e' stato creato e
        # avviato dalla CallingScreen (publish-only) cosi' il rispondente
        # vede il visitatore gia' durante lo squillo. Qui ci limitiamo
        # ad attaccare la callback video per il blit Kivy.
        lk = getattr(self.app_ctx, "lk_session", None)
        if lk is None:
            # Fallback (non dovrebbe succedere): se per qualche motivo
            # arriviamo qui senza una sessione attiva, ne creiamo una.
            ab = (
                getattr(self.app_ctx, "talkback", None)
                or getattr(getattr(self.app_ctx, "app", None), "talkback", None)
            )
            lk = LiveKitSubscribeClient(
                audio_backchannel=ab,
                on_video_frame=self._push_frame,
                publish_av=_LK_PUBLISH,
                **livekit_publish_kwargs_from_config(
                    getattr(self.app_ctx, "config", None)
                ),
            )
            lk.start()
            self.app_ctx.lk_session = lk
        else:
            lk.set_on_video_frame(self._push_frame)
        self._lk = lk
        # Selfview locale via go2rtc snapshot.
        self._start_selfview()

    def on_leave(self, *_):
        LOG.info("ConversationScreen on_leave")
        if self._hold_event:
            self._hold_event.cancel()
            self._hold_event = None
        if self._close_arm_event:
            self._close_arm_event.cancel()
            self._close_arm_event = None
        self._close_armed = False
        self._first_frame_logged = False
        self.overlay_text = ""
        self._stop_selfview()
        # Stacchiamo la callback ma NON fermiamo la sessione LiveKit:
        # il cleanup centrale (main._cleanup_lk_session) si occupa di
        # stop quando si torna a home dopo annullata/terminata/porta_aperta.
        if self._lk is not None:
            try:
                self._lk.set_on_video_frame(None)
            except Exception:
                pass
            self._lk = None

    # ------- Kivy main thread blit -------

    def _push_frame(self, rgb_bytes: bytes, w: int, h: int) -> None:
        """Callback dal LiveKitSubscribeClient (thread asyncio interno).
        Drop-oldest: se il blit precedente non e' ancora stato eseguito
        dal main thread Kivy, sovrascrivi il pending.
        """
        if not getattr(self, "_first_frame_logged", False):
            self._first_frame_logged = True
            LOG.info("ConversationScreen: PRIMO frame video rispondente %dx%d", w, h)
        with self._pending_lock:
            self._pending_frame = (rgb_bytes, w, h)
            if self._blit_scheduled:
                return
            self._blit_scheduled = True
        Clock.schedule_once(self._blit_pending, 0)

    def _blit_pending(self, _dt) -> None:
        with self._pending_lock:
            data = self._pending_frame
            self._pending_frame = None
            self._blit_scheduled = False
        if data is None:
            return
        rgb_bytes, w, h = data
        try:
            img = self.ids.get("video")
            if img is None:
                return
            tex = img.texture
            if tex is None or tex.size != (w, h):
                tex = Texture.create(size=(w, h), colorfmt="rgb")
                tex.flip_vertical()
                img.texture = tex
            tex.blit_buffer(rgb_bytes, colorfmt="rgb", bufferfmt="ubyte")
            img.canvas.ask_update()
        except Exception as e:
            LOG.error("blit err: %s", e)

    # ------- Selfview (PiP) locale via go2rtc snapshot -------

    def _start_selfview(self) -> None:
        from modules.go2rtc_control import is_paused
        if is_paused():
            LOG.debug("selfview skip (go2rtc in pausa per LiveKit)")
            return
        if self._selfview_event is not None:
            return
        self._selfview_inflight = False
        self._selfview_event = Clock.schedule_interval(
            self._selfview_tick, 1.0 / SELFVIEW_FPS
        )
        LOG.info("selfview avviato (%dfps via %s)", SELFVIEW_FPS, SELFVIEW_URL)

    def _stop_selfview(self) -> None:
        if self._selfview_event is not None:
            try:
                self._selfview_event.cancel()
            except Exception:
                pass
            self._selfview_event = None
        sv = self.ids.get("selfview")
        if sv is not None:
            sv.opacity = 0
            sv.texture = None

    def _selfview_tick(self, _dt) -> None:
        if self._selfview_inflight:
            return  # skip se la rete e' lenta, non accumuliamo richieste
        self._selfview_inflight = True
        threading.Thread(
            target=self._selfview_fetch, name="vc-selfview", daemon=True
        ).start()

    def _selfview_fetch(self) -> None:
        try:
            with urllib.request.urlopen(SELFVIEW_URL, timeout=0.6) as r:
                data = r.read()
            Clock.schedule_once(lambda *_: self._selfview_blit(data), 0)
        except Exception as e:
            LOG.debug("selfview fetch err: %s", e)
        finally:
            self._selfview_inflight = False

    def _selfview_blit(self, data: bytes) -> None:
        try:
            sv = self.ids.get("selfview")
            if sv is None:
                return
            img = CoreImage(BytesIO(data), ext="jpg")
            sv.texture = img.texture
            sv.opacity = 0.92
        except Exception as e:
            LOG.debug("selfview blit err: %s", e)

    # ------- Bottoni / overlay azioni -------

    def on_close(self) -> None:
        """Bottone "Chiudi chiamata" (RPi): termina la chiamata pubblicando
        MQTT `chiamata=annullata`. Iniziato dal lato esterno, niente
        overlay (l'utente sta scegliendo lui di uscire).
        """
        if not self._close_armed:
            LOG.info("ConversationScreen close ignorato (debounce post-transizione)")
            return
        LOG.info("ConversationScreen close -> chiamata annullata")
        try:
            self.app_ctx.mqtt.publish_chiamata("annullata", "")
        except Exception as e:
            LOG.warning("publish annullata err: %s", e)
        try:
            self.manager.current = "home"
        except Exception as e:
            LOG.error("close transition err: %s", e)

    def mostra_porta_aperta(self) -> None:
        """Termina la conversazione e mostra la schermata 'Porta aperta'
        (stessa usata dopo apertura via PIN sul RPi): icona door_open +
        titolo grande, auto-back a home dopo AUTO_BACK_SEC."""
        LOG.info("mostra_porta_aperta -> result screen")
        try:
            if self._lk is not None:
                self._lk.stop()
        except Exception as e:
            LOG.warning("stop livekit err: %s", e)
        if self._hold_event:
            self._hold_event.cancel()
            self._hold_event = None
        try:
            result = self.manager.get_screen("result")
            result.mostra_risultato(
                success=True,
                titolo="Porta aperta",
                dettaglio="",
                image_source="assets/door_open.png",
            )
            self.manager.current = "result"
        except Exception as e:
            LOG.error("transition result err: %s", e)

    def mostra_chiamata_terminata(self) -> None:
        """Overlay "Chiamata terminata" 3s -> home. Vedi _hold_e_chiudi."""
        self._hold_e_chiudi("Chiamata terminata")

    def _hold_e_chiudi(self, testo: str) -> None:
        """Mostra `testo` come overlay sopra il video per HOLD_SEC
        secondi, poi torna a home. Usato per dare feedback visivo al
        visitatore esterno quando il rispondente apre la porta o chiude
        la chiamata dal popup HA durante una conversazione video.

        IMPORTANTE: ferma SUBITO il client LiveKit cosi' che il browser
        HA possa chiudere completamente la propria pubblicazione senza
        tenere streamato per altri 3s. L'overlay rimane visibile come
        freeze + testo finche' non torna a home.
        """
        LOG.info("Hold overlay %r per %ds poi home", testo, self.HOLD_SEC)
        self.overlay_text = testo
        try:
            if self._lk is not None:
                self._lk.stop()
        except Exception as e:
            LOG.warning("hold cleanup livekit err: %s", e)
        if self._hold_event:
            self._hold_event.cancel()

        def _to_home(*_):
            try:
                self.manager.current = "home"
            except Exception as e:
                LOG.error("hold -> home err: %s", e)

        self._hold_event = Clock.schedule_once(_to_home, self.HOLD_SEC)

    def on_touch_down(self, touch):
        self.app_ctx.activity_touch()
        return super().on_touch_down(touch)
