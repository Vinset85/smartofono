"""LiveKit client per RPi (subscribe + publish opzionale).

Sostituisce sia `webrtc_audio.py` (audio-only) sia il consumer video
aiortc di `conversation.py`. Step B5 (2026-04): aggiunto path publish
opt-in per pubblicare camera+mic del RPi nella stessa room.

Architettura V1.1 (subscribe + opt-in publish):
    [Browser HA, view "Conversazione" /lovelace/conversazione]
        |  livekit-client web SDK + custom:vc-livekit-call
        |    publish: camera + mic (rispondente)
        |    subscribe: camera + mic (visitatore RPi)
        v
    [LiveKit Server self-hosted su mini-PC HA :7880, single-port mux]
        |  WebRTC SFU
        v
    [LiveKitClient RPi qui sotto, livekit-rtc Python SDK]
        |  subscribe:
        |    AudioStream s16/mono/48k -> AudioBackchannel.feed_webrtc_pcm
        |    VideoStream RGB24        -> Kivy texture callback
        |  publish (opt-in via VC_LK_PUBLISH=1):
        |    LocalAudioTrack <- arecord PCM s16 mono 48k da PulseAudio ec_source
        |    LocalVideoTrack <- Picamera2 YUV420 1280x720@15fps

In Step C (decommissioning) il publish diventa default-on e il path
go2rtc-pi/RTSP/WHIP viene rimosso. In transizione, default-off per
non confliggere col sensore tenuto da go2rtc-pi.

Vantaggi rispetto a aiortc + WHEP / WHIP go2rtc:
    - Decoder/encoder libwebrtc nativo (non pyav fragile)
    - RTCP feedback / receiver reports gestiti -> niente encoder stalls
    - Bandwidth estimation reale -> niente drop fps a 0
    - Riconnessione automatica ICE restart
    - SDK production-grade (Spotify Greenroom, NEAR, ecc.)
    - 1 sola connessione bidirezionale invece di 2 (subscribe + WHIP)

Trigger: ConversationScreen.on_pre_enter istanzia il client, on_leave
lo ferma. Il flag publish_av abilita anche il publish.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

import numpy as np

LOG = logging.getLogger(__name__)


# Endpoint del token issuer Python (vedi installer-ha/livekit/token_issuer/).
# Esposto sul mini-PC HA come container docker-compose, network host.
#
# Il RPi parla in LAN diretta al miniPC HA: niente passaggio da Caddy/TLS
# (latenza inutile, e cert /ssl/ ha CN=casa-esempio.duckdns.org che non
# matcha 192.168.1.160). Quindi:
#   - token issuer:   http://192.168.1.160:8081/token   (LAN, no TLS)
#   - LiveKit ws:     ws://192.168.1.160:7880          (LAN, no TLS)
#
# Override possibile via env var per testing/staging.
TOKEN_URL = os.environ.get("VC_LK_TOKEN_URL", "http://192.168.1.160:8081/token")
TOKEN_ISSUER_SECRET = os.environ.get("VC_LK_TOKEN_SECRET", "").strip()
LIVEKIT_WS = os.environ.get("VC_LK_WS_URL", "ws://192.168.1.160:7880")


def _token_headers() -> dict:
    if TOKEN_ISSUER_SECRET:
        return {"X-VC-Token": TOKEN_ISSUER_SECRET}
    return {}

# Mic device per arecord. Default "pulse:ec_source" = source PipeWire
# generata dal module-echo-cancel (vedi setup PA su RPi). Per fallback
# hardware diretto (no AEC), settare VC_LK_MIC_DEVICE=default.
MIC_DEVICE = os.environ.get("VC_LK_MIC_DEVICE", "pulse:ec_source")

# Room fissa: poiche' c'e' un solo videocitofono e un solo "lato HA"
# che chiama, una room costante e' sufficiente. Il visitatore Pi entra
# come `rpi`, il rispondente HA come `ha-<browser_id>`.
DEFAULT_ROOM = "videocitofono"
DEFAULT_IDENTITY = "rpi"

DEFAULT_PUBLISH_WIDTH = 1280
DEFAULT_PUBLISH_HEIGHT = 720
DEFAULT_PUBLISH_FPS = 15
# Bitrate massimo encode video publish (bps). Su LAN cablata la banda non
# e' un vincolo: 800k era tarato per WiFi/Internet, ora alziamo per un
# 720p nettamente piu' nitido. 2.5 Mbps e' un buon compromesso qualita'
# vs carico encoder OpenH264 software sul Pi5.
DEFAULT_PUBLISH_BITRATE = 2_500_000


def livekit_publish_kwargs_from_config(cfg: dict | None) -> dict[str, Any]:
    """Risoluzione/fps/bitrate publish camera da config.yaml sezione `livekit`."""
    lk = (cfg or {}).get("livekit", {}) or {}
    return {
        "publish_video_size": (
            int(lk.get("publish_width", DEFAULT_PUBLISH_WIDTH)),
            int(lk.get("publish_height", DEFAULT_PUBLISH_HEIGHT)),
        ),
        "publish_video_fps": int(lk.get("publish_fps", DEFAULT_PUBLISH_FPS)),
        "publish_video_bitrate": int(
            lk.get("publish_bitrate", DEFAULT_PUBLISH_BITRATE)
        ),
    }


# Tipo del callback frame video: (rgb_bytes, width, height) -> None.
CameraFrameCallback = Callable[[Any, int, int], None]

# Tipo del callback frame video subscribe: (rgb_bytes, width, height) -> None.
# Chiamato dal thread asyncio interno. Il consumer (Kivy) deve accodare
# il blit sul main thread.
VideoFrameCallback = Callable[[bytes, int, int], None]


class LiveKitSubscribeClient:
    """Client LiveKit subscribe-only.

    API simile a `WebRTCAudioController` per minimizzare le modifiche al
    codice chiamante: `start()`, `stop()`, `active`.

    Aggiunge il callback `on_video_frame` per ricevere anche il video.
    Se `on_video_frame=None`, il client subscribe solo all'audio (utile
    in modalita' "Risposta audio" dove il rispondente HA invia solo mic).
    """

    def __init__(
        self,
        audio_backchannel,
        on_video_frame: Optional[VideoFrameCallback] = None,
        room: str = DEFAULT_ROOM,
        identity: str = DEFAULT_IDENTITY,
        publish_av: bool = False,
        publish_video_size: tuple[int, int] = (
            DEFAULT_PUBLISH_WIDTH,
            DEFAULT_PUBLISH_HEIGHT,
        ),
        publish_video_fps: int = DEFAULT_PUBLISH_FPS,
        publish_video_bitrate: int = DEFAULT_PUBLISH_BITRATE,
        # Default da env var VC_LK_MIC_DEVICE (default modulo:
        # "pulse:ec_source"). Override programmatico passando esplicito.
        mic_device: Optional[str] = None,
    ):
        self._ab = audio_backchannel
        self._on_video = on_video_frame
        self._on_camera_frame: Optional[CameraFrameCallback] = None
        self._room_name = room
        self._identity = identity
        self._loop_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()
        self._room: Any = None
        self._active = False
        # Step B5: publish opt-in. Quando True il client pubblica anche
        # camera+mic del RPi nella stessa room, cosi' il rispondente HA
        # vede e sente il visitatore senza dipendere da go2rtc/WHIP.
        self._publish_av = bool(publish_av)
        self._pub_w, self._pub_h = publish_video_size
        self._pub_fps = int(publish_video_fps)
        self._pub_bitrate = int(publish_video_bitrate)
        self._mic_device = str(mic_device) if mic_device else MIC_DEVICE
        # Risorse del publisher (lazy init dentro l'event loop):
        self._mic_proc: Any = None       # subprocess.Popen di arecord
        self._mic_task: Any = None       # asyncio.Task del feed audio
        self._cam_obj: Any = None        # legacy: Picamera2 dedicato (non piu' usato)
        self._cam_sess: Any = None       # PicamSession singleton condiviso
        self._cam_task: Any = None       # asyncio.Task del feed video
        self._audio_source: Any = None   # rtc.AudioSource
        self._video_source: Any = None   # rtc.VideoSource
        # Guadagno uplink: 4x a riposo (MEMS VoiceHat debole). Mentre HA
        # parla scende per non rimandare l'eco residua dell'AEC.
        self._mic_gain = 4.0
        self._stats_lock = threading.Lock()
        self._call_stats: dict[str, Any] = {
            "connection_quality": "unknown",
            "rtt_ms": None,
            "packet_loss": None,
        }
        self._stats_task: Any = None

    @property
    def active(self) -> bool:
        return self._active

    def get_call_stats(self) -> dict[str, Any]:
        with self._stats_lock:
            return dict(self._call_stats)

    def _set_call_stats(self, **kw) -> None:
        with self._stats_lock:
            self._call_stats.update(kw)

    def set_on_video_frame(self, cb: Optional[VideoFrameCallback]) -> None:
        """Aggiorna runtime il callback video. Usato per il flusso
        ring->answer: il client viene avviato in CallingScreen senza
        callback (publish-only), e quando il visitatore entra in
        ConversationScreen si attacca il callback per il display.
        Idempotente; se il VideoStream e' gia' aperto, il loop di
        consumo lo cattura via self._on_video al prossimo frame."""
        self._on_video = cb

    def set_on_camera_frame(self, cb: Optional[CameraFrameCallback]) -> None:
        """Callback RGB per analisi locale (es. riconoscimento visitatore
        durante publish). Invocato da thread pool, throttled ~2 Hz."""
        self._on_camera_frame = cb

    def start(self) -> None:
        if self._active:
            LOG.info("LiveKitSubscribeClient gia' attivo, skip")
            return
        self._active = True
        self._stop_event.clear()
        self._loop_thread = threading.Thread(
            target=self._run_loop, name="vc-livekit-aio", daemon=True
        )
        self._loop_thread.start()
        LOG.info("LiveKitSubscribeClient avviato (room=%s identity=%s, video=%s)",
                 self._room_name, self._identity, self._on_video is not None)

    def stop(self, timeout: float = 8.0) -> None:
        if not self._active:
            return
        self._active = False
        self._stop_event.set()
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._cleanup(), loop)
        try:
            self._ab.stop_webrtc()
        except Exception:
            pass
        t = self._loop_thread
        if t and t.is_alive():
            try:
                t.join(timeout=timeout)
            except Exception:
                pass
        LOG.info("LiveKitSubscribeClient fermato")
        self._set_call_stats(
            connection_quality="unknown", rtt_ms=None, packet_loss=None)

    # ---------- internal ----------

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception as e:
            LOG.error("livekit aio loop terminated: %s", e, exc_info=True)
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self._loop = None

    async def _main(self) -> None:
        # Backoff retry: l'altro lato (browser HA) puo' essere lento
        # ad arrivare in room. Cold-start tipico 1-3 retry.
        backoff = 0.5
        while not self._stop_event.is_set():
            try:
                await self._connect_and_consume()
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOG.warning("livekit connect err: %s", e)
            if self._stop_event.is_set():
                break
            await self._sleep_until_stop(backoff)
            backoff = min(backoff * 1.5, 5.0)

    async def _sleep_until_stop(self, timeout: float) -> None:
        """Attesa del backoff che si interrompe appena arriva stop().

        _stop_event e' un threading.Event (stop() viene chiamato dal thread
        Kivy) quindi non e' awaitable: lo si controlla a piccoli passi. Senza
        questo, chiudere una chiamata durante il backoff lasciava il thread
        del loop bloccato fino a 5s.
        """
        deadline = time.monotonic() + timeout
        while not self._stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.1, remaining))

    async def _connect_and_consume(self) -> None:
        # Import dentro la funzione per non bloccare l'import del modulo
        # se livekit-rtc non e' installato (utile in dev local).
        from livekit import rtc  # type: ignore

        token, ws_url = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_token
        )

        room = rtc.Room()
        self._room = room

        finished = asyncio.Event()

        @room.on("disconnected")
        def _on_disconnected(reason: Any = None):
            LOG.info("livekit room disconnected reason=%s", reason)
            finished.set()

        @room.on("connection_state_changed")
        def _on_state(state: Any):
            LOG.info("livekit connection state=%s", state)
            s = str(state).lower()
            if "connected" in s:
                self._set_call_stats(connection_quality="good")
            elif "reconnect" in s:
                self._set_call_stats(connection_quality="poor")
            elif "disconnect" in s:
                self._set_call_stats(connection_quality="lost")

        @room.on("connection_quality_changed")
        def _on_quality(quality: Any):
            qmap = {0: "unknown", 1: "excellent", 2: "good", 3: "poor", 4: "lost"}
            try:
                qi = int(quality)
            except Exception:
                qi = quality
            label = qmap.get(qi, str(quality))
            self._set_call_stats(connection_quality=label)

        @room.on("participant_connected")
        def _on_participant(p: Any):
            LOG.info("livekit participant connected: %s", p.identity)

        @room.on("track_subscribed")
        def _on_track_subscribed(track: Any, publication: Any, participant: Any):
            LOG.info("livekit track subscribed kind=%s sid=%s from=%s",
                     track.kind, track.sid, participant.identity)
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                asyncio.create_task(self._consume_audio(rtc, track))
            elif track.kind == rtc.TrackKind.KIND_VIDEO:
                # Il consumer video parte sempre: legge i frame anche
                # se _on_video e' None (drop dei frame, niente blit).
                # Cosi' quando ConversationScreen attacca il callback
                # via set_on_video_frame, il flusso e' gia' decoded
                # e il primo frame rendered avviene in <100ms invece
                # che attendere keyframe successivi.
                asyncio.create_task(self._consume_video(rtc, track))

        try:
            await room.connect(
                ws_url,
                token,
                options=rtc.RoomOptions(auto_subscribe=True),
            )
            LOG.info("livekit connected as %s in %s", self._identity, self._room_name)
            if self._publish_av:
                await self._start_publishers(rtc, room)
            self._stats_task = asyncio.create_task(self._stats_poll_loop(room))
            # Resta in attesa di stop_event o disconnect remoto.
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(finished.wait(), timeout=0.5)
                    break
                except asyncio.TimeoutError:
                    continue
        finally:
            if self._stats_task is not None:
                self._stats_task.cancel()
                try:
                    await self._stats_task
                except Exception:
                    pass
                self._stats_task = None
            await self._stop_publishers()
            try:
                await room.disconnect()
            except Exception:
                pass
            if self._room is room:
                self._room = None

    # ---------- publishers (opt-in) ----------

    async def _start_publishers(self, rtc, room) -> None:
        """Avvia publish di camera+mic dal RPi nella stessa Room.

        Non bloccante per i subscribe: se uno dei due fallisce (mic o cam
        indisponibile), logga e prosegue con quello che funziona. Il
        rispondente HA vedra'/sentira' solo cio' che il Pi riesce a
        pubblicare.
        """
        # --- audio publish ---
        try:
            # queue_size_ms=100 (default 1000): buffer interno LiveKit
            # ridotto a 100ms. Con il default da 1s il browser HA
            # percepisce il mic del Pi con ~700-1000ms di ritardo
            # (l'AudioSource accumula frame fino a saturazione coda).
            # 100ms = 5 frame da 20ms, sufficienti per coprire jitter
            # di scheduling Python e network LAN.
            try:
                self._audio_source = rtc.AudioSource(48000, 1, queue_size_ms=100)
            except TypeError:
                # SDK piu' vecchio senza queue_size_ms
                self._audio_source = rtc.AudioSource(48000, 1)
            audio_track = rtc.LocalAudioTrack.create_audio_track(
                "rpi-mic", self._audio_source
            )
            await room.local_participant.publish_track(
                audio_track,
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
            )
            LOG.info("livekit publish: mic track pubblicata (%s)", self._mic_device)
            self._mic_task = asyncio.create_task(self._mic_capture_loop(rtc))
        except Exception as e:
            LOG.warning("livekit publish audio FAIL: %s", e)
            self._audio_source = None

        # --- video publish ---
        try:
            self._video_source = rtc.VideoSource(self._pub_w, self._pub_h)
            video_track = rtc.LocalVideoTrack.create_video_track(
                "rpi-cam", self._video_source
            )
            # simulcast=False: il publisher Python emette un solo layer.
            # Con simulcast il SDK Python crea piu' SSRC (q+h) ma non li
            # alimenta in modo simmetrico: il browser HA puo' ricevere
            # qualche keyframe iniziale e poi bloccarsi quando RTCP
            # richiede un layer mai effettivamente codificato. Forzando un
            # solo stream il decoder Chrome resta sano per tutta la chiamata.
            #
            # video_codec=H264: simmetrico al fix lato browser. Chrome
            # decodifica H264 in HW, e il publisher Python (libwebrtc
            # nativo) usa OpenH264 / libavcodec con NEON sul Pi5: encode
            # piu' leggero di VP8 a parita' di qualita'.
            try:
                pub_opts = rtc.TrackPublishOptions(
                    source=rtc.TrackSource.SOURCE_CAMERA,
                    video_encoding=rtc.VideoEncoding(
                        max_framerate=self._pub_fps,
                        max_bitrate=self._pub_bitrate,
                    ),
                    simulcast=False,
                    video_codec=rtc.VideoCodec.H264,
                )
            except (TypeError, AttributeError):
                # Fallback per SDK piu' vecchi senza video_codec o senza
                # enum VideoCodec (es. livekit-rtc <1.0): negoziazione
                # lasciata al server (probabile VP8 default).
                try:
                    pub_opts = rtc.TrackPublishOptions(
                        source=rtc.TrackSource.SOURCE_CAMERA,
                        video_encoding=rtc.VideoEncoding(
                            max_framerate=self._pub_fps,
                            max_bitrate=self._pub_bitrate,
                        ),
                        simulcast=False,
                    )
                except TypeError:
                    pub_opts = rtc.TrackPublishOptions(
                        source=rtc.TrackSource.SOURCE_CAMERA,
                        video_encoding=rtc.VideoEncoding(
                            max_framerate=self._pub_fps,
                            max_bitrate=self._pub_bitrate,
                        ),
                    )
            await room.local_participant.publish_track(video_track, pub_opts)
            LOG.info("livekit publish: cam track pubblicata (%dx%d@%dfps %dkbps)",
                     self._pub_w, self._pub_h, self._pub_fps,
                     self._pub_bitrate // 1000)
            self._cam_task = asyncio.create_task(self._cam_capture_loop(rtc))
        except Exception as e:
            LOG.warning("livekit publish video FAIL: %s", e)
            self._video_source = None

    async def _stop_publishers(self) -> None:
        """Ferma i task di capture e libera le risorse hardware."""
        for t in (self._mic_task, self._cam_task):
            if t and not t.done():
                t.cancel()
                try:
                    await t
                except Exception:
                    pass
        self._mic_task = None
        self._cam_task = None
        try:
            if self._mic_proc:
                self._mic_proc.terminate()
                try:
                    self._mic_proc.wait(timeout=1.0)
                except Exception:
                    self._mic_proc.kill()
        except Exception:
            pass
        self._mic_proc = None
        try:
            if self._cam_obj:
                try:
                    self._cam_obj.stop()
                except Exception:
                    pass
                # close() chiude i fd /dev/media* e rilascia la camera
                # kernel-side (stato Configured -> Available). Senza
                # close, la prossima Picamera2() solleva
                # "Camera in Configured state trying acquire()".
                try:
                    self._cam_obj.close()
                except Exception:
                    pass
        except Exception:
            pass
        self._cam_obj = None
        self._audio_source = None
        self._video_source = None

    async def _mic_capture_loop(self, rtc) -> None:
        """Cattura PCM dal mic via arecord e alimenta AudioSource a 20ms.

        arecord legge da PulseAudio ec_source (output del module-echo-cancel)
        gia' filtrato AEC. Preferisce mono (AEC caricato a 1 canale). Fallback
        stereo: sul VoiceHat il MEMS e' sul canale destro.
        Ogni 20ms = 960 samples @ 48kHz.
        """
        import subprocess
        chunk_samples = 48000 // 50  # 960
        chunk_bytes_mono = chunk_samples * 2
        chunk_bytes_stereo = chunk_samples * 4
        # period 480 frame (10ms) e buffer 1920 frame (40ms) = latenza
        # intrinseca arecord 40ms invece dei 200-500ms di default ALSA.
        def _cmd(channels: int) -> list[str]:
            return [
                "arecord", "-q",
                "-D", self._mic_device,
                "-f", "S16_LE",
                "-r", "48000",
                "-c", str(channels),
                "-t", "raw",
                "--period-size=480",
                "--buffer-size=1920",
            ]

        channels = 1
        chunk_bytes = chunk_bytes_mono
        try:
            self._mic_proc = subprocess.Popen(
                _cmd(1),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except FileNotFoundError:
            LOG.warning("arecord non installato, mic publish off")
            return
        except Exception as e:
            LOG.warning("arecord spawn err: %s", e)
            return
        # Se ec_source e' ancora stereo, arecord -c 1 muore subito.
        await asyncio.sleep(0.15)
        if self._mic_proc.poll() is not None:
            LOG.info("arecord mono fallito, fallback stereo (canale R)")
            try:
                self._mic_proc = subprocess.Popen(
                    _cmd(2),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                channels = 2
                chunk_bytes = chunk_bytes_stereo
            except Exception as e:
                LOG.warning("arecord stereo spawn err: %s", e)
                return
        LOG.info(
            "mic capture loop avviato (device=%s 48k %s)",
            self._mic_device, "mono" if channels == 1 else "stereo-R",
        )
        loop = asyncio.get_event_loop()
        n_read = 0
        n_sent = 0
        last_log = time.monotonic()
        mono = np.zeros(chunk_samples, dtype=np.int16)
        # Soglia RMS del PCM HA: sotto = silenzio/rumore, sopra = sta parlando.
        far_end_rms_th = 500.0
        gain_idle = 4.0
        gain_echo = 0.25
        try:
            while not self._stop_event.is_set():
                data = await loop.run_in_executor(
                    None, self._mic_proc.stdout.read, chunk_bytes
                )
                if not data:
                    LOG.warning("mic arecord stdout EOF: pipe chiusa (mic morto?)")
                    break
                n_read += 1
                if len(data) < chunk_bytes:
                    data = data + b"\x00" * (chunk_bytes - len(data))
                try:
                    samples = np.frombuffer(data, dtype=np.int16)
                    if channels == 2:
                        samples = samples[1::2]
                    pb = 0.0
                    if self._ab is not None:
                        pb = float(getattr(self._ab, "playback_rms", 0.0) or 0.0)
                    target = gain_echo if pb >= far_end_rms_th else gain_idle
                    alpha = 0.45 if target < self._mic_gain else 0.06
                    self._mic_gain += (target - self._mic_gain) * alpha
                    mono = samples.astype(np.int32) * self._mic_gain
                    np.clip(mono, -32768, 32767, out=mono)
                    mono = mono.astype(np.int16)
                    frame = rtc.AudioFrame.create(48000, 1, chunk_samples)
                    np_view = np.frombuffer(frame.data, dtype=np.int16)
                    np_view[:] = mono
                    await self._audio_source.capture_frame(frame)
                    n_sent += 1
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    LOG.warning("audio capture_frame err: %s", e)
                now = time.monotonic()
                if now - last_log >= 5.0:
                    rms = 0
                    try:
                        if mono.size:
                            rms = int(np.sqrt(np.mean(mono.astype(np.int32) ** 2)))
                    except Exception:
                        pass
                    LOG.info(
                        "mic publish stats: read=%d sent=%d rms=%d gain=%.2f far_rms=%.0f",
                        n_read, n_sent, rms, self._mic_gain,
                        float(getattr(self._ab, "playback_rms", 0.0) or 0.0) if self._ab else 0.0,
                    )
                    last_log = now
        except asyncio.CancelledError:
            pass
        except Exception as e:
            LOG.info("mic capture loop end: %s", e)
        LOG.info("mic capture loop terminato")

    @staticmethod
    def _yuv420_to_rgb(arr: Any, width: int, height: int, max_width: int = 720) -> Any:
        import cv2
        yuv = arr.reshape((height * 3 // 2, width))
        rgb = cv2.cvtColor(yuv, cv2.COLOR_YUV420p2RGB)
        if width > max_width:
            nh = int(height * max_width / width)
            rgb = cv2.resize(rgb, (max_width, nh), interpolation=cv2.INTER_AREA)
        return rgb

    def _feed_camera_frame_async(self, loop, arr: Any) -> None:
        cb = self._on_camera_frame
        if cb is None:
            return
        w, h = self._pub_w, self._pub_h

        def _work() -> None:
            try:
                rgb = LiveKitSubscribeClient._yuv420_to_rgb(arr, w, h)
                cb2 = self._on_camera_frame
                if cb2 is not None:
                    cb2(rgb, rgb.shape[1], rgb.shape[0])
            except Exception as e:
                LOG.debug("camera frame callback err: %s", e)

        try:
            loop.run_in_executor(None, _work)
        except Exception as e:
            LOG.debug("camera frame executor err: %s", e)

    async def _cam_capture_loop(self, rtc) -> None:
        """Cattura frame YUV420 e alimenta il VideoSource LiveKit.

        IMPORTANTE (Pi5): la cattura passa per il PicamSession singleton
        (modo 'call') invece di istanziare un Picamera2 dedicato. Aprire un
        SECONDO Picamera2 (o aprire/chiudere ripetutamente) mentre il
        PicamSession di motion esiste lascia libcamera bloccata in stato
        'Running/Configured' -> il publisher cattura buffer vuoti -> I420 a
        zero = immagine VERDE/distorta dalla 2a chiamata, e il motion entra
        in loop infinito di "acquire FAIL". Con un solo oggetto vivo e solo
        switch di modo il problema sparisce. Formato YUV420 nativo = I420
        planar = LiveKit VideoBufferType.I420.
        """
        loop = asyncio.get_event_loop()
        try:
            from modules.camera_session import PicamSession  # type: ignore
        except Exception as e:
            LOG.warning("camera_session non disponibile, cam publish off: %s", e)
            return
        sess = PicamSession.instance()
        sess.set_call_mode(self._pub_w, self._pub_h, self._pub_fps)
        # acquire fa I/O camera (open/switch): in executor per non bloccare
        # l'event loop asyncio.
        ok = False
        try:
            ok = await loop.run_in_executor(None, sess.acquire, "call")
        except Exception as e:
            LOG.error("PicamSession.acquire(call) eccezione: %s", e)
            ok = False
        if not ok:
            LOG.error(
                "PicamSession.acquire(call) FAIL -> track video pubblicato "
                "ma senza frame (immagine congelata sul subscriber)"
            )
            return
        self._cam_sess = sess
        LOG.info("cam capture loop avviato via PicamSession (%dx%d@%dfps YUV420)",
                 self._pub_w, self._pub_h, self._pub_fps)
        period = 1.0 / max(self._pub_fps, 1)
        n_cap = 0
        n_sent = 0
        n_err = 0
        last_log = time.monotonic()
        last_face_feed = 0.0
        face_feed_interval = 0.45
        try:
            while not self._stop_event.is_set():
                t0 = loop.time()
                try:
                    arr = await loop.run_in_executor(None, sess.capture, "call")
                    if arr is None:
                        # mode mismatch / capture err transitorio: salta frame
                        # senza incrementare n_err (evita spam log).
                        n_err += 1
                        dt0 = loop.time() - t0
                        if dt0 < period:
                            await asyncio.sleep(period - dt0)
                        continue
                    # picamera2 con format=YUV420 ritorna ndarray shape (h*1.5, w) uint8
                    raw = arr.tobytes()
                    n_cap += 1
                    frame = rtc.VideoFrame(
                        self._pub_w, self._pub_h,
                        rtc.VideoBufferType.I420,
                        raw,
                    )
                    self._video_source.capture_frame(frame)
                    n_sent += 1
                    now_mono = time.monotonic()
                    if (self._on_camera_frame is not None
                            and now_mono - last_face_feed >= face_feed_interval):
                        last_face_feed = now_mono
                        self._feed_camera_frame_async(loop, arr)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    n_err += 1
                    if n_err <= 5 or n_err % 30 == 0:
                        LOG.warning("video capture err #%d: %s", n_err, e)
                # frame pacing
                dt = loop.time() - t0
                if dt < period:
                    await asyncio.sleep(period - dt)
                now = loop.time()
                if now - last_log >= 5.0:
                    LOG.info("cam publish stats: cap=%d sent=%d err=%d size=%dx%d",
                             n_cap, n_sent, n_err, self._pub_w, self._pub_h)
                    last_log = now
        except asyncio.CancelledError:
            pass
        except Exception as e:
            LOG.info("cam capture loop end: %s", e)
        # NB: NON chiudiamo la camera qui. La cattura usa il PicamSession
        # singleton, che resta vivo: a fine chiamata main.py fa
        # PicamSession.release() (o lo switch a 'motion' al resume), un
        # solo ciclo open/close gestito centralmente. Chiudere qui creerebbe
        # di nuovo il conflitto di possesso con motion.
        self._cam_sess = None
        LOG.info("cam capture loop terminato (PicamSession resta gestito da main)")

    def _fetch_token(self) -> tuple[str, str]:
        """HTTP POST sincrono al token issuer (run_in_executor caller).

        prefer_lan=True: il token issuer ritorna ws_url interno LAN
        (ws://192.168.1.160:7880) invece di quello pubblico TLS (wss
        passante per Caddy). Il RPi e' sulla stessa LAN del miniPC HA,
        non ha senso fare tre hop in piu' (RPi -> Caddy:443 -> LK:7880).
        """
        body = json.dumps({
            "identity": self._identity,
            "room": self._room_name,
            "name": self._identity,
            "ttl_seconds": 3600,
            "can_publish": True,
            "can_subscribe": True,
            "prefer_lan": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            TOKEN_URL, data=body,
            headers={"Content-Type": "application/json", **_token_headers()},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"token issuer unreachable: {e}") from e
        token = payload["token"]
        ws_url = payload.get("ws_url") or LIVEKIT_WS
        return token, ws_url

    async def _stats_poll_loop(self, room) -> None:
        """Aggiorna metriche qualità chiamata durante sessione attiva."""
        while not self._stop_event.is_set():
            rtt_ms = None
            packet_loss = None
            try:
                for rp in getattr(room, "remote_participants", {}).values():
                    for pub in getattr(rp, "track_publications", {}).values():
                        track = getattr(pub, "track", None)
                        if track is None:
                            continue
                        get_stats = getattr(track, "get_stats", None)
                        if not callable(get_stats):
                            continue
                        stats = await get_stats()
                        for st in stats or []:
                            rtt = getattr(st, "round_trip_time", None)
                            if rtt is not None:
                                rtt_ms = max(rtt_ms or 0, float(rtt) * 1000.0)
                            loss = getattr(st, "packets_lost", None)
                            total = getattr(st, "packets_received", None)
                            if loss is not None and total:
                                packet_loss = round(
                                    100.0 * float(loss) / max(1.0, float(total)), 2)
            except Exception as e:
                LOG.debug("livekit stats poll err: %s", e)
            upd = {}
            if rtt_ms is not None:
                upd["rtt_ms"] = round(rtt_ms, 1)
            if packet_loss is not None:
                upd["packet_loss"] = packet_loss
            if upd:
                self._set_call_stats(**upd)
            await asyncio.sleep(5.0)

    # ---------- consumers ----------

    async def _consume_audio(self, rtc, track) -> None:
        """Consuma AudioFrame dalla track LiveKit, normalizza a s16/mono/48k
        e chiama feed_webrtc_pcm sul backchannel esistente.

        livekit-rtc espone gia' AudioFrame in PCM s16 sul layout configurato.
        Apriamo lo stream con sample_rate=48000, num_channels=1: il SDK fa
        resampling lato C++ libwebrtc (efficient). Non serve pyav.
        """
        ab = self._ab
        if ab is None:
            LOG.warning("audio_backchannel non presente, drain audio")
            return
        LOG.info("LiveKit audio consumer avviato")
        stream = rtc.AudioStream(track, sample_rate=48000, num_channels=1)
        try:
            async for evt in stream:
                if self._stop_event.is_set():
                    break
                frame = evt.frame
                # frame.data e' memoryview di int16 little-endian, mono.
                pcm_bytes = bytes(frame.data)
                try:
                    ab.feed_webrtc_pcm(pcm_bytes, 48000, 1)
                except Exception as e:
                    LOG.warning("feed_webrtc_pcm err: %s", e)
        except Exception as e:
            LOG.info("livekit audio stream ended: %s", e)
        finally:
            try:
                ab.stop_webrtc()
            except Exception:
                pass
            LOG.info("LiveKit audio consumer terminato")

    async def _consume_video(self, rtc, track) -> None:
        """Consuma VideoFrame dalla track LiveKit, converte a RGB24 e
        chiama il callback `on_video_frame(rgb_bytes, w, h)`.

        Decoder livewebrtc nativo: H264/VP8/VP9/AV1 supportati senza
        pyav. Il VideoStream emette VideoFrame con buffer in formato
        I420 di default; convert_to(RGB24) e' una passata SIMD efficiente.
        """
        # cb viene riletto ad ogni frame da self._on_video: il flusso
        # ring->answer attacca la callback dopo che il consumer e' gia'
        # partito. Se cb e' None il frame viene scartato (decoded ma
        # non blittato).
        LOG.info("LiveKit video consumer avviato")
        n = 0; n_ok = 0; last_log = time.monotonic()
        last_w, last_h = 0, 0
        # Forziamo formato di output RGB24 nello stream (richiede SDK 1.1+).
        try:
            stream = rtc.VideoStream(track, format=rtc.VideoBufferType.RGB24)
        except Exception:
            # Fallback: stream nativo (I420), convertiamo per frame.
            stream = rtc.VideoStream(track)
        n_skip_placeholder = 0
        try:
            async for evt in stream:
                if self._stop_event.is_set():
                    break
                frame = evt.frame
                n += 1
                # Quando il publisher rinegozia bitrate/risoluzione (es.
                # adaptive stream del browser HA durante congestione) il
                # SDK puo' emettere frame placeholder 8x8 o piu' piccoli
                # di 64px per qualche centinaio di ms. Blittarli causa
                # un visibile sfarfallio nero su Kivy: scartiamo subito.
                fw = int(getattr(frame, "width", 0))
                fh = int(getattr(frame, "height", 0))
                if fw < 64 or fh < 64:
                    n_skip_placeholder += 1
                    continue
                try:
                    cb = self._on_video
                    if cb is None:
                        # Drop: nessun consumer attaccato (es. siamo in
                        # CallingScreen prima del rispondi). Lasciamo
                        # comunque che libwebrtc decoda per mantenere
                        # caldo il decoder e non perdere keyframe.
                        last_w = int(getattr(frame, "width", 0)) or last_w
                        last_h = int(getattr(frame, "height", 0)) or last_h
                    else:
                        rgb_bytes, w, h = self._frame_to_rgb(frame, rtc)
                        cb(rgb_bytes, w, h)
                        n_ok += 1
                        last_w, last_h = w, h
                except Exception as e:
                    if n_ok == 0 or n % 200 == 0:
                        LOG.warning("video frame convert err #%d: %s", n, e)
                now = time.monotonic()
                if now - last_log >= 5.0:
                    LOG.info("livekit video stats: recv=%d blit=%d skip_ph=%d size=%dx%d",
                             n, n_ok, n_skip_placeholder, last_w, last_h)
                    last_log = now
        except Exception as e:
            LOG.info("livekit video stream ended: %s (recv=%d blit=%d)",
                     e, n, n_ok)
        finally:
            LOG.info("LiveKit video consumer terminato")

    @staticmethod
    def _frame_to_rgb(frame: Any, rtc) -> tuple[bytes, int, int]:
        """Converte un VideoFrame livekit-rtc in (rgb_bytes, w, h).

        Compatibile con SDK 1.1.x: prova prima `frame.convert(RGB24)`,
        fallback su numpy reshape se gia' RGB24.
        """
        w = int(getattr(frame, "width", 0))
        h = int(getattr(frame, "height", 0))
        # SDK 1.1+: frame.convert(buffer_type) -> nuovo VideoFrame.
        try:
            converted = frame.convert(rtc.VideoBufferType.RGB24)
            data = bytes(converted.data)
            return data, int(converted.width), int(converted.height)
        except Exception:
            pass
        # Fallback: assume gia' RGB24 in frame.data
        data = bytes(frame.data)
        if w and h and len(data) == w * h * 3:
            return data, w, h
        # Ultimo fallback: assume I420 e converte con numpy
        if w and h:
            arr = np.frombuffer(data, dtype=np.uint8)
            # I420 size = w*h*3//2; non sempre vero. Saltiamo se mismatch.
            if len(arr) >= w * h * 3 // 2:
                yuv = arr[: w * h * 3 // 2]
                rgb = LiveKitSubscribeClient._i420_to_rgb24(yuv, w, h)
                return rgb.tobytes(), w, h
        raise ValueError(f"unsupported frame format len={len(data)} w={w} h={h}")

    @staticmethod
    def _i420_to_rgb24(yuv: np.ndarray, w: int, h: int) -> np.ndarray:
        """Conversione I420->RGB24 leggera con numpy. Solo fallback;
        normalmente livekit-rtc fa la conversione lato C++."""
        y = yuv[: w * h].reshape((h, w)).astype(np.int32)
        u = yuv[w * h : w * h + (w * h) // 4].reshape((h // 2, w // 2))
        v = yuv[w * h + (w * h) // 4 :].reshape((h // 2, w // 2))
        u = u.repeat(2, axis=0).repeat(2, axis=1).astype(np.int32) - 128
        v = v.repeat(2, axis=0).repeat(2, axis=1).astype(np.int32) - 128
        r = (y + (1.402 * v).astype(np.int32)).clip(0, 255)
        g = (y - (0.344136 * u).astype(np.int32) - (0.714136 * v).astype(np.int32)).clip(0, 255)
        b = (y + (1.772 * u).astype(np.int32)).clip(0, 255)
        rgb = np.stack([r, g, b], axis=-1).astype(np.uint8)
        return rgb

    async def _cleanup(self) -> None:
        # Cancella i task pendenti prima del disconnect, altrimenti al
        # close del loop resta "Task was destroyed but it is pending".
        current = asyncio.current_task()
        pending = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        try:
            if self._room:
                await self._room.disconnect()
        except Exception:
            pass
