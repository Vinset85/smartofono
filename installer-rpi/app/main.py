"""Videocitofono - Postazione Esterna RPi5 (Kivy GUI).

Avvio:
    python3 main.py

Variabili ambiente utili:
    VC_CONFIG=/path/to/config.yaml   # percorso config alternativo
    KIVY_NO_CONSOLELOG=1             # silenzia log Kivy in produzione
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

# In ambiente kiosk senza X potresti voler forzare backend (decommentare):
# os.environ.setdefault("KIVY_GL_BACKEND", "gl")
# os.environ.setdefault("KIVY_WINDOW", "sdl2")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kivy.app import App
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.uix.screenmanager import ScreenManager, NoTransition, FadeTransition
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle


def _register_symbol_font():
    """Registra Symbola come font 'Symbola' per i Label che usano simboli/emoji.
    Su RPi OS: pacchetto fonts-symbola → /usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf
    Se mancante, ignora (i glyph appariranno come tofu '□')."""
    candidates = [
        "/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf",
        "/usr/share/fonts/truetype/symbola/Symbola.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                LabelBase.register(name="Symbola", fn_regular=p)
                logging.getLogger("videocitofono").info("Font Symbola registrato: %s", p)
                return
            except Exception as e:
                logging.getLogger("videocitofono").warning("Symbola register err: %s", e)


_register_symbol_font()

from modules.config import load_config, _deep_merge
from modules.access_icons import bundled_icon_filenames
from modules.mqtt_client import MqttPublisher
from modules.ha_client import HaClient
from modules.pin_manager import PinManager, bootstrap_users
from modules.face_recognition_stub import FaceRecognizer
from modules.face_engine import FaceEngineFacade, migrate_legacy_face_storage
from modules.camera import CameraPreview
from modules.brightness import BrightnessController
from modules.motion_detector import MotionDetector, MotionSnapshotDetector, MotionPicameraDetector
from modules.cmd_auth import CmdAuthGuard
from modules.fingerprint_reader import FingerprintReader
from modules.audio_backchannel import AudioBackchannel
from modules.webrtc_audio import WebRTCAudioController
from modules.sound_fx import SoundFx
from modules.tts import Tts
from modules.log_setup import setup_logging, audit
from modules.watchdog_systemd import (
    WatchdogPinger, watchdog_interval_from_env,
    notify_ready, notify_status,
)
from modules.touch_controller import TouchController
from modules.backup import BackupRunner
from modules.audit_db import AuditDB
from modules.guest_pin import GuestPinManager
from modules.face_unknowns import UnknownFaceTracker
from modules.anomaly import AnomalyDetector
from modules.health import HealthReporter
from modules.auto_enroll import AutoEnroller
from modules.connectivity import ConnectivityMonitor
from modules.voice_id import VoiceId
from modules.cloud_storage import CloudUploader
from modules.nfc_reader import NfcReader, NfcLibrary
from modules.go2rtc_control import pause_for_camera, resume_after_camera, set_idle_go2rtc_allowed

# Widget riutilizzabili (registrati prima del KV)
from screens.widgets import (
    RoundButton, CallButton, IconAccessButton, PlaceholderScreenBase,
    GlassNumButton, PinActionButton,
)  # noqa: F401
from screens.icons import VectorIcon  # noqa: F401  registrato per uso in KV

# Schermate
from screens.home import HomeScreen
from screens.calling import CallingScreen
from screens.conversation import ConversationScreen
from screens.pin import PinScreen
from screens.face import FaceScreen, FaceMeshOverlay  # noqa: F401  registrato per uso in KV
from screens.nfc import NfcScreen
from screens.placeholders import (
    FingerScreen,
    ResultScreen,
    ScreensaverScreen,
    PlaceholderScreen,  # noqa: F401  registrato per kv
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for _noisy in (
    "aiortc",
    "aiortc.rtcrtpreceiver",
    "aiortc.rtcrtpsender",
    "aiortc.rtcdtlstransport",
    "aiortc.rtcicetransport",
    "aiortc.rtcsctptransport",
    "aioice",
    "aioice.ice",
    "aioice.stun",
    "aioice.turn",
    "livekit",
    "livekit.rtc",
    "livekit.rtc._proto",
    "livekit.rtc.room",
    "livekit.rtc.rtc",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
LOG = logging.getLogger("videocitofono")


class DimOverlay(Widget):
    """Overlay nero fullscreen per software brightness dim.
    NON intercetta touch (lascia passare al ScreenManager sotto)."""
    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas:
            self._color = Color(0, 0, 0, 0)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)
        Window.bind(size=lambda *_: self._sync())

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def set_alpha(self, alpha: float) -> None:
        self._color.a = max(0.0, min(0.95, float(alpha)))

    def on_touch_down(self, touch):
        return False  # passa il touch ai widget sotto

    def on_touch_move(self, touch):
        return False

    def on_touch_up(self, touch):
        return False


class AppContext:
    """Container condiviso tra le schermate."""
    def __init__(self, app: "VideocitofonoApp"):
        self.app = app
        self.config = app.cfg
        self.mqtt = app.mqtt
        self.ha = app.ha
        self.pin_manager = app.pin_manager
        self.face = app.face
        self.camera = app.camera
        self.sound = app.sound
        self.tts = app.tts
        # Nuovi servizi (Fase 1-3): possono essere None se non inizializzati.
        self.audit_db = getattr(app, "audit_db", None)
        self.guest_pins = getattr(app, "guest_pins", None)
        self.auto_enroller = getattr(app, "auto_enroller", None)
        self.unknown_tracker = getattr(app, "unknown_tracker", None)
        self.anomaly_det = getattr(app, "anomaly_det", None)
        self.voice_id = getattr(app, "voice_id", None)
        self.cloud = getattr(app, "cloud", None)
        self.health = None  # set dopo HealthReporter.start()
        self.touch = TouchController(cooldown_sec=0.45)

    def go_screen(self, name: str, *, instant: bool = False) -> None:
        self.app.go_screen(name, instant=instant)

    @property
    def nfc_lib(self):
        return getattr(self.app, "nfc_lib", None)

    @property
    def nfc_reader(self):
        return getattr(self.app, "nfc_reader", None)

    @property
    def connectivity(self):
        return getattr(self.app, "connectivity", None)

    def activity_touch(self, source: str = "touch") -> None:
        self.app.on_activity(source)

    def record_open(self, method: str, user: str = "",
                    scope: str = "porta", success: bool = True,
                    **meta) -> None:
        """Audit centralizzato di un evento di apertura porta/cancello.
        Chiama audit_db, health, anomaly_det e logger strutturato.
        """
        try:
            if self.audit_db is not None:
                self.audit_db.add_event(
                    "open" if success else "open_fail",
                    method=method, user=user, scope=scope,
                    success=success, meta=meta or None,
                )
        except Exception:
            pass
        try:
            if success and self.health is not None:
                self.health.mark_open()
        except Exception:
            pass
        try:
            if success and user and self.anomaly_det is not None:
                self.anomaly_det.maybe_emit(user)
        except Exception:
            pass
        try:
            log = logging.getLogger("videocitofono.audit")
            audit(log, "door_open", method=method, user=user,
                  scope=scope, success=success, **(meta or {}))
        except Exception:
            pass

    def record_event(self, kind: str, **kw) -> None:
        try:
            if self.audit_db is not None:
                self.audit_db.add_event(kind, **kw)
        except Exception:
            pass


class VideocitofonoApp(App):
    title = "Videocitofono"
    # Lasciamo l'auto-load del KV (file accanto al main.py con stesso nome
    # della classe in lowercase). NON caricarlo anche manualmente con
    # Builder.load_file: causerebbe duplicazione delle rule e widget doppi.

    def build(self):
        # Touch capacitivo RPi: meno ghost point, risposta piu' diretta.
        try:
            Window.multitouch_on_demand = True
        except Exception:
            pass

        self.cfg = load_config(os.environ.get("VC_CONFIG"))

        # Re-inizializza il logging in base alla config (JSON + rotazione)
        # sostituendo il basicConfig fatto a import time.
        try:
            setup_logging(self.cfg.get("logging", {}))
        except Exception as _e:
            logging.getLogger(__name__).warning("setup_logging err: %s", _e)

        # Inizializza moduli
        self.mqtt = MqttPublisher(self.cfg["mqtt"])
        self.cmd_auth = CmdAuthGuard(self.cfg.get("mqtt") or {})
        if not self.cmd_auth.enabled:
            LOG.warning(
                "mqtt.cmd_secret vuoto: i comandi su videocitofono/cmd "
                "vengono accettati senza token")
        self.mqtt.on_connected(lambda: Clock.schedule_once(
            lambda *_: self._mqtt_republish_idle(), 0.4))
        self.mqtt.start()
        self.ha = HaClient(self.cfg["home_assistant"])
        bootstrap_users(self.cfg["pin"])
        self.pin_manager = PinManager(self.cfg["pin"])
        # Engine facciale: facade che sceglie tra ArcFace e dlib in base
        # a config (`face_recognition.engine`). Manteniamo dlib come
        # fallback runtime per non rompere installazioni esistenti.
        self._dlib_face = FaceRecognizer(self.cfg.get("face_recognition", {}))
        migrate_legacy_face_storage(self._dlib_face.storage_dir)
        self.face = FaceEngineFacade(self.cfg.get("face_recognition", {}),
                                     dlib_recognizer=self._dlib_face)
        self._dlib_face.reload_library()
        if getattr(self.face, "reload_library", None):
            self.face.reload_library()
        self.camera = CameraPreview(self.cfg.get("camera", {}))
        ui_cfg = self.cfg.get("ui", {}) or {}
        self.sound = SoundFx(
            volume=float(ui_cfg.get("feedback_volume", 0.10)),
            enabled=bool(ui_cfg.get("feedback_enabled", True)),
        )
        tts_cfg = self.cfg.get("tts", {}) or {}
        self.tts = Tts(
            enabled=bool(tts_cfg.get("enabled", True)),
            lang=str(tts_cfg.get("lang", "it")),
            wpm=int(tts_cfg.get("wpm", 140)),
            volume=float(tts_cfg.get("volume", 1.0)),
            voice=str(tts_cfg.get("voice", "")),
            pitch=int(tts_cfg.get("pitch", 50)),
            word_gap_ms=int(tts_cfg.get("word_gap_ms", 50)),
            engine=str(tts_cfg.get("engine", "auto")),
            piper_voice=str(tts_cfg.get("piper_voice", "")),
            length_scale=float(tts_cfg.get("length_scale", 1.10)),
            noise_scale=float(tts_cfg.get("noise_scale", 0.667)),
            noise_w=float(tts_cfg.get("noise_w", 0.8)),
            edge_voice=str(tts_cfg.get("edge_voice", "")),
            edge_rate=str(tts_cfg.get("edge_rate", "+0%")),
            cache_dir=str(tts_cfg.get("cache_dir", "")),
            # Fuori chiamata si parla diretti all'altoparlante; in chiamata no,
            # o l'interlocutore sentirebbe l'eco del saluto.
            in_call=lambda: (getattr(self.ctx, "lk_session", None) is not None
                             or getattr(self.ctx, "lk_preview", None) is not None),
        )

        # ---- Audit DB (sqlite) per audit trail / unknowns / anomaly ----
        try:
            audit_path = str(self.cfg.get("audit", {}).get(
                "db_path", "/opt/videocitofono/data/audit.sqlite"))
            self.audit_db = AuditDB(audit_path)
        except Exception as _e:
            LOG.warning("AuditDB init err: %s", _e)
            self.audit_db = None

        # ---- Guest PINs ----
        try:
            self.guest_pins = GuestPinManager(
                path=str((self.cfg.get("pin") or {}).get(
                    "guest_db", "/opt/videocitofono/data/guest_pins.json")),
                length=int((self.cfg.get("pin") or {}).get("guest_length", 6)),
            )
        except Exception as _e:
            LOG.warning("GuestPinManager init err: %s", _e)
            self.guest_pins = None

        # ---- Auto-enroll dopo apertura PIN ----
        self.auto_enroller = AutoEnroller(
            cfg=(self.cfg.get("face_recognition") or {}).get("auto_enroll", {}),
            storage_dir=self._dlib_face.storage_dir,
        )

        # ---- Auto face recognition (motion-triggered, opzionale) ----
        try:
            from modules.auto_face import AutoFaceScanner
            self.auto_face = AutoFaceScanner(
                self,
                cfg=(self.cfg.get("face_recognition") or {}).get(
                    "auto_recognize", {}) or {},
            )
        except Exception as _e:
            LOG.debug("AutoFaceScanner init err: %s", _e)
            self.auto_face = None

        # ---- Riconoscimento visitatore durante chiamata (CallingScreen) ----
        try:
            from modules.call_visitor_recognition import CallVisitorRecognizer
            cr_cfg = dict(self.cfg.get("call_recognition", {}) or {})
            cam_rot = int((self.cfg.get("camera") or {}).get("rotation", 0))
            if cam_rot and "camera_rotation" not in cr_cfg:
                cr_cfg["camera_rotation"] = cam_rot
            self.call_visitor_recog = CallVisitorRecognizer(
                self.face,
                self.mqtt,
                cfg=cr_cfg,
            )
        except Exception as _e:
            LOG.debug("CallVisitorRecognizer init err: %s", _e)
            self.call_visitor_recog = None

        # ---- Unknown face tracker + anomaly detector ----
        self.unknown_tracker = None
        self.anomaly_det = None
        if self.audit_db is not None:
            try:
                u_cfg = (self.cfg.get("face_recognition") or {}).get(
                    "unknown_tracking", {}) or {}
                self.unknown_tracker = UnknownFaceTracker(
                    audit_db=self.audit_db,
                    storage_dir=str(u_cfg.get(
                        "storage_dir", "/opt/videocitofono/data/unknowns")),
                    cooldown_sec=int(u_cfg.get("cooldown_sec", 300)),
                    notify_threshold=int(u_cfg.get("notify_threshold", 3)),
                    notify_window_days=int(u_cfg.get("notify_window_days", 7)),
                    dist_threshold=float(u_cfg.get("dist_threshold", 0.4)),
                    mqtt_publish=lambda t, p, r=False: self.mqtt.publish(t, p, retain=r),
                )
            except Exception as _e:
                LOG.warning("UnknownTracker init err: %s", _e)

            try:
                a_cfg = (self.cfg.get("audit") or {}).get("anomaly", {}) or {}
                self.anomaly_det = AnomalyDetector(
                    audit_db=self.audit_db,
                    mqtt_publish=lambda t, p, r=False: self.mqtt.publish(t, p, retain=r),
                    window_days=int(a_cfg.get("window_days", 60)),
                    z_threshold=float(a_cfg.get("z_threshold", 2.5)),
                    min_samples=int(a_cfg.get("min_samples", 15)),
                )
            except Exception as _e:
                LOG.warning("AnomalyDetector init err: %s", _e)

        # ---- Voice ID + Cloud uploader (scaffold opzionali) ----
        try:
            self.voice_id = VoiceId(self.cfg.get("voice_recognition", {}))
        except Exception as _e:
            LOG.debug("VoiceId disabled: %s", _e)
            self.voice_id = None
        try:
            self.cloud = CloudUploader(self.cfg.get("cloud_storage", {}))
        except Exception as _e:
            LOG.debug("CloudUploader disabled: %s", _e)
            self.cloud = None

        self._config_pending: dict = {}
        self._config_pending_persist = False
        self._config_debounce_ev = None
        self._CONFIG_DEBOUNCE_SEC = 10.0

        # ---- Fingerprint (stub hardware) -------------------------------
        self.fingerprint_reader = None
        fp_cfg = self.cfg.get("fingerprint") or {}
        if fp_cfg.get("enabled", False):
            self.fingerprint_reader = FingerprintReader(fp_cfg)

        # ---- NFC reader + library --------------------------------
        self.nfc_lib = None
        self.nfc_reader = None
        self._nfc_cfg_active = None
        # Avvio NFC ritardato: su cold boot il prep USB e' gia' in stamp;
        # su restart servizio _init_nfc_from_cfg fa recover prima del thread.
        Clock.schedule_once(lambda *_: self._init_nfc_from_cfg(), 8.0)

        # ---- Backup automatico ----
        try:
            self.backup_runner = BackupRunner(
                self.cfg.get("backup", {}),
                root="/opt/videocitofono",
            )
            self.backup_runner.start()
        except Exception as _e:
            LOG.warning("BackupRunner err: %s", _e)
            self.backup_runner = None

        # ---- Watchdog systemd ----
        try:
            self.watchdog = WatchdogPinger(
                interval_sec=watchdog_interval_from_env(default=10.0))
            self.watchdog.start()
        except Exception as _e:
            LOG.debug("Watchdog err: %s", _e)
            self.watchdog = None

        # ---- Health reporter (avviato a fine build dopo che self.sm esiste) ----
        self.health = None

        # Brightness + Motion
        ui = self.cfg.get("ui", {})
        self.brightness = BrightnessController(
            idle_pct=ui.get("brightness_idle_pct", 20),
            active_pct=ui.get("brightness_active_pct", 100),
            prefer_software_dim=ui.get("prefer_software_dim", True),
        )

        mcfg = self.cfg.get("motion", {})
        self.motion = None
        eco_cfg = self.cfg.get("eco") or {}
        set_idle_go2rtc_allowed(
            not eco_cfg.get("enabled", True)
            or mcfg.get("source") == "snapshot")
        if mcfg.get("enabled", True):
            # Default 'picamera': architettura LiveKit-direct senza go2rtc
            # locale, la camera e' libera tra una chiamata e l'altra.
            #   picamera: apre direttamente libcamera a bassa risoluzione
            #             (motion va sospeso prima/durante la chiamata).
            #   snapshot: polling JPEG da go2rtc (legacy, richiede go2rtc up).
            #   camera  : MotionDetector basato su CameraPreview Kivy (legacy).
            source = mcfg.get("source", "picamera")
            if source == "picamera":
                self.motion = MotionPicameraDetector(
                    width=mcfg.get("picam_width", 320),
                    height=mcfg.get("picam_height", 240),
                    fps=mcfg.get("tick_hz", 2),
                    pixel_thresh=mcfg.get("pixel_thresh", 18),
                    area_thresh_pct=mcfg.get("area_thresh_pct", 1.0),
                    cooldown_sec=mcfg.get("cooldown_sec", 2.0),
                    debug_log_every=mcfg.get("debug_log_every", 30),
                )
                self.motion.on_motion(lambda: Clock.schedule_once(
                    lambda *_: self.on_activity("motion_picam"), 0))
                if self._should_start_motion("home"):
                    self.motion.start()
                else:
                    LOG.info("Motion picamera pronto (avvio su screensaver, eco)")
                LOG.info("MotionPicameraDetector attivo (%dx%d@%dfps)",
                         mcfg.get("picam_width", 320),
                         mcfg.get("picam_height", 240),
                         int(mcfg.get("tick_hz", 2)))
            elif source == "snapshot":
                self.motion = MotionSnapshotDetector(
                    snapshot_url=mcfg.get(
                        "snapshot_url",
                        "http://localhost:1984/api/frame.jpeg?src=pi5cam_h264",
                    ),
                    pixel_thresh=mcfg.get("pixel_thresh", 25),
                    area_thresh_pct=mcfg.get("area_thresh_pct", 1.5),
                    cooldown_sec=mcfg.get("cooldown_sec", 1.5),
                    thumb_size=mcfg.get("thumb_size", 160),
                    timeout_sec=mcfg.get("timeout_sec", 1.5),
                    tick_hz=mcfg.get("tick_hz", 2),
                    debug_log_every=mcfg.get("debug_log_every", 30),
                )
                self.motion.on_motion(lambda: Clock.schedule_once(
                    lambda *_: self.on_activity("motion_snapshot"), 0))
                if self._should_start_motion("home"):
                    self.motion.start()
                else:
                    LOG.info("Motion snapshot pronto (avvio su screensaver, eco)")
                LOG.info("MotionSnapshotDetector attivo su %s", mcfg.get("snapshot_url"))
            elif self.camera.is_available():
                self.motion = MotionDetector(
                    camera=self.camera,
                    pixel_thresh=mcfg.get("pixel_thresh", 25),
                    area_thresh_pct=mcfg.get("area_thresh_pct", 1.5),
                    cooldown_sec=mcfg.get("cooldown_sec", 1.5),
                    downsample=mcfg.get("downsample", 8),
                )
                self.motion.on_motion(lambda: self.on_activity("motion"))

        # Soglie idle
        self._idle_dim_sec = ui.get("idle_dim_sec", 20)
        self._screensaver_timeout = ui.get("screensaver_timeout_sec", 60)
        self._display_off_sec = ui.get("display_off_sec", 180)
        self._wake_screensaver_on_motion = mcfg.get("wake_screensaver", True)

        if ui.get("fullscreen", True):
            Window.fullscreen = "auto"
        else:
            Window.size = (ui.get("width", 1920), ui.get("height", 1080))
        if not ui.get("cursor", False):
            try:
                Window.show_cursor = False
            except Exception:
                pass

        # KV: l'auto-load di Kivy lo carica già (file videocitofono.kv accanto
        # al modulo). Non chiamare Builder.load_file qui o le rule vengono
        # registrate due volte e i widget appaiono duplicati.

        ctx = AppContext(self)
        self.ctx = ctx
        # LiveKit session shared (None quando fuori chiamata). Vedi
        # CallingScreen.on_enter (start) e _on_screen_changed (stop).
        ctx.lk_session = None
        # Sessione LiveKit dell'anteprima on-demand da HA, tenuta separata da
        # lk_session: quella e' governata dai cambi di schermata (calling ->
        # conversation -> home), questa da un comando MQTT e da un timeout.
        # Non sono mai attive insieme: userebbero la stessa identity 'rpi' e la
        # seconda espellerebbe la prima dalla room.
        ctx.lk_preview = None

        self._fade_transition = FadeTransition(duration=0.12)
        sm = ScreenManager(transition=self._fade_transition)
        sfondo_init = ui.get("sfondo", "default") or "default"
        bg_init = ""
        if sfondo_init and sfondo_init != "default":
            cand = os.path.join(self.SFONDI_DIR, sfondo_init)
            if not os.path.exists(cand):
                ha_url = (self.cfg.get("home_assistant", {}) or {}).get("base_url", "").rstrip("/")
                if ha_url:
                    self._download_sfondo(ha_url + "/local/vc-sfondi/" + sfondo_init, sfondo_init)
            if os.path.exists(cand):
                bg_init = cand
        # Precarica icone da HA prima della Home (evita flash icona vettoriale).
        try:
            self._sync_icons_from_config(refresh_ui=False)
        except Exception as e:
            LOG.warning("sync icone pre-home err: %s", e)
        sm.add_widget(HomeScreen(name="home", app_ctx=ctx, bg_source=bg_init))
        sm.add_widget(CallingScreen(name="calling", app_ctx=ctx, bg_source=bg_init))
        sm.add_widget(ConversationScreen(name="conversation", app_ctx=ctx, bg_source=bg_init))
        sm.add_widget(PinScreen(name="pin", app_ctx=ctx, bg_source=bg_init))
        sm.add_widget(FaceScreen(name="face", app_ctx=ctx, bg_source=bg_init))
        sm.add_widget(FingerScreen(name="finger", app_ctx=ctx, bg_source=bg_init))
        sm.add_widget(NfcScreen(name="nfc", app_ctx=ctx, bg_source=bg_init))
        sm.add_widget(ResultScreen(name="result", app_ctx=ctx, bg_source=bg_init))
        sm.add_widget(ScreensaverScreen(
            name="screensaver", app_ctx=ctx,
            indirizzo=ui.get("indirizzo", "Via Roma 1"),
            bg_source=bg_init,
        ))
        self.sm = sm
        # Cleanup centralizzato del LiveKit session quando si esce
        # dal ciclo chiamata. Evita di replicare lo stop in ogni
        # path di terminazione (annullata/porta_aperta/terminata/timeout/
        # touch chiudi).
        sm.bind(current=lambda inst, val: self._on_screen_changed(val))

        # Root con overlay per software dim (sopra ScreenManager, sotto eventi touch)
        root = FloatLayout()
        root.add_widget(sm)
        self.dim_overlay = DimOverlay()
        root.add_widget(self.dim_overlay)
        self.brightness.set_overlay_setter(self.dim_overlay.set_alpha)
        self.brightness.active()  # avvio in piena luminosità (alpha=0)

        # MQTT subscribe handlers (wake da HA, comandi remoti)
        self.mqtt.on_wake(lambda payload: Clock.schedule_once(
            lambda *_: self.on_activity("mqtt_wake"), 0))
        self.mqtt.on_cmd(lambda payload: Clock.schedule_once(
            lambda *_: self._handle_cmd(payload), 0))
        # Video uplink dal browser HA (rispondi con videocamera): "on"
        # apre la ConversationScreen che pulla rtsp://HA:8554/responder_av,
        # "off" torna alla schermata appropriata.
        self.mqtt.on_responder_video(lambda raw: Clock.schedule_once(
            lambda *_: self._handle_responder_video(raw), 0))
        # Audio uplink dal browser HA (rispondi audio-only): "on" avvia
        # WebRTCAudioController per consumare m=audio Opus da go2rtc HA
        # (responder_av) e suonarlo via PulseAudio. RPi resta su
        # CallingScreen/ConversationScreen senza cambiare schermata.
        self.mqtt.on_responder_audio(lambda raw: Clock.schedule_once(
            lambda *_: self._handle_responder_audio(raw), 0))
        # Stato chiamata: se HA pubblica "annullata" (utente preme chiudi
        # nel popup, timeout HA, browser_mod.close_popup) torniamo a home
        # subito, senza aspettare il timeout interno di CallingScreen.
        self.mqtt.on_chiamata(lambda stato: Clock.schedule_once(
            lambda *_: self._handle_chiamata(stato), 0))

        try:
            self.connectivity = ConnectivityMonitor(
                mqtt_client=self.mqtt,
                ha_cfg=self.cfg.get("home_assistant") or {},
                on_mode_change=lambda mode: Clock.schedule_once(
                    lambda *_: self._on_connectivity_mode_change(mode), 0),
            )
            self.connectivity.start()
        except Exception as _e:
            LOG.warning("ConnectivityMonitor err: %s", _e)
            self.connectivity = None

        # Player audio HA -> RPi (riproduce frame WebRTC via ffmpeg+pulse)
        self.talkback = AudioBackchannel(self.mqtt, self.cfg.get("audio", {}))
        self.talkback.start()
        # Consumer audio-only WebRTC (modalita' "Risposta audio")
        self.webrtc_audio = WebRTCAudioController(self.talkback)

        # Pulsante chiamata fisico GPIO (opzionale, solo se installato gpiozero)
        self.button = None
        self._setup_physical_button()

        # Trigger di test/debug: SIGUSR1 simula pressione campanello.
        # Uso: kill -USR1 <pid videocitofono>. Utile per QA quando il Pi
        # gira in Wayland (xdotool/wlrctl non sempre disponibili) e non
        # c'e' accesso fisico al pulsante.
        self._setup_test_signals()

        # Watcher idle (luminosità + screensaver)
        self.last_activity = Clock.get_time()
        Clock.schedule_interval(self._check_idle, 1)

        # Motion tick (solo per detector LOCALE basato su camera; il
        # MotionSnapshotDetector ha il proprio thread interno, niente Clock).
        if self.motion and isinstance(self.motion, MotionDetector):
            tick_hz = max(1, mcfg.get("tick_hz", 5))
            Clock.schedule_interval(lambda *_: self.motion.tick(), 1.0 / tick_hz)

        self.mqtt.publish_evento("boot", {"versione": "0.1.0",
                                          "brightness_backend": self.brightness.backend,
                                          "motion": bool(self.motion)})

        # Pubblica retain libreria volti su MQTT (a +2s, dopo che broker
        # ha registrato la connessione). Cosi' HA legge lo stato anche a
        # freddo (sensore videocitofono_volti).
        Clock.schedule_once(lambda *_: self._publish_volti_library(), 2.0)
        from kivy.clock import Clock as _ClkNfc  # noqa: E501
        _ClkNfc.schedule_once(lambda *a: self._publish_nfc_library(), 2.5)
        _ClkNfc.schedule_once(lambda *a: self._publish_nfc_status(), 3.0)
        nfc_iv = float((self.cfg.get("eco") or {}).get("nfc_status_sec", 30 if self._eco_enabled() else 15))
        _ClkNfc.schedule_interval(lambda *a: self._publish_nfc_status(), nfc_iv)
        # Retry icone se HA non era raggiungibile al boot (applica_config ~14s).
        _ClkNfc.schedule_once(lambda *a: self._sync_icons_from_config(), 5.0)
        _ClkNfc.schedule_once(lambda *a: self._sync_icons_from_config(), 20.0)
        if mcfg.get("enabled", True) and mcfg.get("source") == "snapshot":
            _ClkNfc.schedule_once(
                lambda *a: self._ensure_go2rtc_for_motion(), 5.0)
        elif self._eco_enabled() and not self._go2rtc_for_motion():
            from modules.go2rtc_control import stop_idle_service
            _ClkNfc.schedule_once(lambda *a: stop_idle_service(), 3.0)

        # Ripristina volumi audio chiamata persistiti in config.override.yaml.
        # Schedulato a +4s per attendere videocitofono-mic-volume.service che
        # carica module-echo-cancel e setta i default 100% / 140% al boot.
        # Senza questo delay pactl set-sink-volume ec_sink fallisce perche'
        # il sink non esiste ancora.
        def _restore_audio_volumes(*_):
            audio_cfg = self.cfg.get("audio", {}) or {}
            keys = {k: audio_cfg[k] for k in ("volume_speaker_pct", "volume_mic_pct")
                    if k in audio_cfg}
            if keys:
                LOG.info("Restore volumi audio da config: %s", keys)
                self._apply_audio_live(keys)
            ui_cfg = self.cfg.get("ui", {}) or {}
            if "feedback_volume" in ui_cfg and getattr(self, "sound", None):
                v = float(ui_cfg["feedback_volume"])
                self.sound.set_volume(max(0.0, min(1.0, v)))
                LOG.info("Restore feedback_volume da config: %.2f", v)
            tts_cfg = self.cfg.get("tts", {}) or {}
            if "volume" in tts_cfg and getattr(self, "tts", None):
                self.tts.set_volume(float(tts_cfg["volume"]))
        Clock.schedule_once(_restore_audio_volumes, 4)
        Clock.schedule_once(_restore_audio_volumes, 12)

        # ---- Health reporter (avviato qui perche' usa self.sm) ----
        try:
            health_cfg = self.cfg.get("health", {}) or {}
            eco_cfg = self.cfg.get("eco") or {}
            interval = float(health_cfg.get("interval_sec", 30))
            if eco_cfg.get("enabled", True):
                interval = float(eco_cfg.get("health_interval_sec", interval))
            ver_path = ROOT / "version.txt"
            version = ver_path.read_text().strip() if ver_path.exists() else "dev"
            self.health = HealthReporter(
                mqtt_publish=lambda t, p, r=False: self.mqtt.publish(t, p, retain=r),
                topic=str(health_cfg.get("topic", "videocitofono/health")),
                interval_sec=interval,
                version=version,
                get_screen=lambda: (self.sm.current if hasattr(self, "sm") else ""),
                get_camera_status=self._health_camera_status,
                get_engine_face=lambda: getattr(self.face, "engine_name", ""),
                get_subsystems=self._health_subsystems,
            )
            self.ctx.health = self.health
            self.health.start()
        except Exception as _e:
            LOG.warning("HealthReporter err: %s", _e)

        # ---- Notifica systemd: READY ----
        try:
            notify_ready()
            notify_status("running")
        except Exception:
            pass
        try:
            audit(LOG, "app_start",
                  engine_face=getattr(self.face, "engine_name", ""))
        except Exception:
            pass

        return root

    def _setup_physical_button(self) -> None:
        """Pulsante chiamata fisico via GPIO. Premuto -> trigger campanello default.

        Config (config.yaml):
            button:
              enabled: true
              gpio_pin: 17           # BCM
              pull_up: true          # con pull-up il pulsante chiude verso GND
              bounce_time_ms: 100
              campanello_id: famiglia_rossi   # quale campanello "premere"
        """
        bcfg = self.cfg.get("button", {}) or {}
        if not bcfg.get("enabled", False):
            return
        try:
            from gpiozero import Button
        except Exception as e:
            LOG.warning("gpiozero non disponibile, pulsante GPIO disattivo: %s", e)
            return

        pin = int(bcfg.get("gpio_pin", 17))
        pull_up = bool(bcfg.get("pull_up", True))
        bounce = float(bcfg.get("bounce_time_ms", 100)) / 1000.0
        camp_id = bcfg.get("campanello_id") or "default"
        camp_nome = "Pulsante esterno"
        for c in self.cfg.get("campanelli", []) or []:
            if c.get("id") == camp_id:
                camp_nome = c.get("nome", camp_nome)
                break
        try:
            self.button = Button(pin, pull_up=pull_up, bounce_time=bounce)
            self.button.when_pressed = lambda: Clock.schedule_once(
                lambda *_: self._on_physical_button(camp_id, camp_nome), 0
            )
            LOG.info("Pulsante GPIO%d attivo -> campanello '%s'", pin, camp_id)
        except Exception as e:
            LOG.error("Init pulsante GPIO%d fallito: %s", pin, e)
            self.button = None

    def _setup_test_signals(self) -> None:
        import signal
        def _handler(signum, frame):
            campanelli = self.cfg.get("campanelli", []) or []
            if not campanelli:
                LOG.warning("SIGUSR1: nessun campanello configurato, skip")
                return
            c = campanelli[0]
            cid = c.get("id", "default")
            cnome = c.get("nome", "Test")
            LOG.info("SIGUSR1 ricevuto -> simulo press campanello '%s'", cid)
            Clock.schedule_once(
                lambda *_: self._on_physical_button(cid, cnome), 0
            )
        try:
            signal.signal(signal.SIGUSR1, _handler)
            LOG.info("SIGUSR1 handler attivo (test campanello)")
        except Exception as e:
            LOG.warning("SIGUSR1 handler init err: %s", e)

    def _on_physical_button(self, camp_id: str, camp_nome: str) -> None:
        LOG.info("Pulsante fisico premuto -> chiamata %s (%s)", camp_id, camp_nome)
        self.on_activity("button")
        if self.sm.current in ("calling", "conversation"):
            return
        try:
            self.sm.get_screen("home")._chiama(camp_id, camp_nome)
        except Exception as e:
            LOG.error("Avvio chiamata da pulsante fallito: %s", e)

    def _motion_stop_fast(self) -> None:
        mot = self.motion
        if mot and hasattr(mot, "stop"):
            try:
                mot.stop(join_timeout=0.25)
            except TypeError:
                mot.stop()

    def go_screen(self, name: str, *, instant: bool = False) -> None:
        sm = self.sm
        if not sm.has_screen(name):
            return
        if instant:
            sm.transition = NoTransition()
            sm.current = name
            Clock.schedule_once(
                lambda *_: setattr(sm, "transition", self._fade_transition), 0)
        else:
            sm.current = name

    def _eco_cfg(self) -> dict:
        return self.cfg.get("eco") or {}

    def _eco_enabled(self) -> bool:
        return bool(self._eco_cfg().get("enabled", True))

    def _go2rtc_for_motion(self) -> bool:
        return (self.cfg.get("motion") or {}).get("source") == "snapshot"

    def _motion_on_home_allowed(self) -> bool:
        if not self._eco_enabled():
            return True
        return not bool(self._eco_cfg().get("motion_only_on_screensaver", True))

    def _screen_dimmed(self) -> bool:
        if self.brightness.is_off:
            return True
        pct = self.brightness.current_pct
        return 0 <= pct < self.brightness.active_pct

    def _should_start_motion(self, screen: str) -> bool:
        if screen == "screensaver":
            return True
        if screen == "home":
            if self._motion_on_home_allowed():
                return True
            # Eco: camera solo quando serve wake (schermo smorzato).
            if self._eco_enabled() and self._screen_dimmed():
                return True
        return False

    def _motion_thread_alive(self) -> bool:
        mot = self.motion
        if mot is None:
            return False
        t = getattr(mot, "_thread", None)
        if t is not None:
            return t.is_alive()
        return isinstance(mot, MotionDetector)

    def _sync_motion_state(self) -> None:
        """Avvia/ferma motion in base a schermata e luminosità (idempotente)."""
        if not self.motion:
            return
        mcfg = self.cfg.get("motion") or {}
        if not mcfg.get("enabled", True):
            return
        screen = self.sm.current
        if screen in ("calling", "conversation", "face"):
            return
        want = self._should_start_motion(screen)
        alive = self._motion_thread_alive()
        if want and not alive:
            LOG.info("Motion start (sync screen=%s dim=%s)", screen,
                     self._screen_dimmed())
            self.motion.start()
        elif not want and alive and hasattr(self.motion, "stop"):
            LOG.debug("Motion stop (sync screen=%s)", screen)
            self._motion_stop_fast()

    def _should_exit_screensaver(self, source: str) -> bool:
        if source == "touch":
            return True
        if source.startswith("motion"):
            return self._wake_screensaver_on_motion
        return True

    def on_activity(self, source: str = "touch") -> None:
        """Chiamato su tocco o motion. Ripristina luminosità piena e resetta timer idle.
        Se la motion arriva durante lo screensaver, riporta la UI a home.
        Il motion in home già luminosa non resetta il timer (evita falsi positivi
        da artefatti JPEG negli snapshot go2rtc)."""
        waking = (
            self.sm.current == "screensaver"
            or self._screen_dimmed()
        )
        if not source.startswith("motion") or waking:
            self.last_activity = Clock.get_time()
        self.brightness.active()
        if self.sm.current == "screensaver":
            if self._should_exit_screensaver(source):
                LOG.info("Wake da screensaver (source=%s)", source)
                if source.startswith("motion"):
                    try:
                        audit(LOG, "motion_wake", source=source,
                              screen="screensaver")
                    except Exception:
                        pass
                self.go_screen("home", instant=True)
        Clock.schedule_once(lambda *_: self._sync_motion_state(), 0)
        # Auto face: solo su home (evita contesa camera durante wake).
        try:
            if (source.startswith("motion")
                    and getattr(self, "auto_face", None)
                    and self.sm.current == "home"):
                Clock.schedule_once(
                    lambda *_: self.auto_face.trigger(), 0.25)
        except Exception:
            pass

    def _on_screen_changed(self, current: str) -> None:
        """Hook screen-change: lavoro pesante (motion/camera) differito di 1 frame."""
        prev = getattr(self, "_last_screen", "")
        self._last_screen = current
        Clock.schedule_once(
            lambda *_: self._on_screen_changed_work(current, prev), 0)

    def _on_screen_changed_work(self, current: str, prev: str) -> None:
        """Cleanup risorse fuori-chiamata (non bloccare la transizione UI)."""
        call_screens = ("calling", "conversation")
        entering_call = (
            current in call_screens and prev not in call_screens
        )
        leaving_call = prev in call_screens and current not in call_screens

        # L'anteprima remota cede la camera al riconoscimento volti locale
        # (libcamera e' esclusiva). Per la chiamata ci pensa
        # _enter_call_camera_mode, che deve fermarla prima di avviare la
        # propria sessione LiveKit.
        if current == "face" and getattr(self.ctx, "lk_preview", None) is not None:
            self._stop_preview_livekit("schermata volto", riavvia_go2rtc=False)

        try:
            if entering_call:
                self._enter_call_camera_mode(current)
            elif leaving_call:
                self._motion_stop_fast()
                self._release_call_camera()
                self._schedule_post_call_camera(current)
            elif self.motion:
                if current in ("calling", "conversation", "face"):
                    LOG.info("Motion stop (screen=%s)", current)
                    self._motion_stop_fast()
                elif self._should_start_motion(current):
                    Clock.schedule_once(
                        lambda *_: self._sync_motion_state(), 0.35)
                else:
                    LOG.debug("Motion idle (screen=%s, eco)", current)
                    self._motion_stop_fast()
        except Exception as e:
            LOG.warning("motion/go2rtc screen-hook err: %s", e)

        if current in ("calling", "conversation"):
            return
        if prev in ("calling", "conversation"):
            return
        self.stop_call_visitor_recognition()
        lk = getattr(self.ctx, "lk_session", None)
        if lk is None:
            return
        try:
            LOG.info("LiveKit session stop (screen=%s)", current)
            lk.stop()
        except Exception as e:
            LOG.warning("LiveKit session stop err: %s", e)
        self.ctx.lk_session = None

    def start_call_visitor_recognition(self) -> None:
        rec = getattr(self, "call_visitor_recog", None)
        lk = getattr(self.ctx, "lk_session", None)
        if rec is None or lk is None:
            return
        try:
            rec.start(lk)
        except Exception as e:
            LOG.warning("start_call_visitor_recognition err: %s", e)

    def stop_call_visitor_recognition(self) -> None:
        rec = getattr(self, "call_visitor_recog", None)
        if rec is None:
            return
        try:
            rec.stop()
        except Exception as e:
            LOG.warning("stop_call_visitor_recognition err: %s", e)

    def _enter_call_camera_mode(self, screen: str) -> None:
        """Libera libcamera: ferma go2rtc (rpicam-vid) e motion."""
        # Anteprima remota eventualmente in corso: va chiusa qui, prima che
        # _start_call_livekit crei la sessione della chiamata. Entrambe usano
        # identity 'rpi', quindi la seconda espellerebbe la prima dalla room e
        # il rispondente resterebbe senza video. riavvia_go2rtc=False perche'
        # la chiamata vuole comunque libcamera libera.
        if getattr(self.ctx, "lk_preview", None) is not None:
            self._stop_preview_livekit("chiamata in arrivo", riavvia_go2rtc=False)
        if self.motion:
            LOG.info("Motion stop (screen=%s)", screen)
            self._motion_stop_fast()
        pause_for_camera("call")
        try:
            from modules.camera_session import PicamSession
            PicamSession.instance().release()
            LOG.info("PicamSession released for LiveKit (screen=%s)", screen)
        except Exception as e:
            LOG.warning("PicamSession.release err: %s", e)
        # LiveKit dopo pausa go2rtc (on_enter CallingScreen puo' correre prima).
        Clock.schedule_once(lambda *_: self._start_call_livekit(), 0.8)

    def _start_call_livekit(self) -> None:
        """Avvia LiveKit + riconoscimento visitatore quando libcamera e' libera."""
        if self.sm.current not in ("calling", "conversation"):
            return
        lk = getattr(self.ctx, "lk_session", None)
        if lk is not None:
            Clock.schedule_once(
                lambda *_: self.start_call_visitor_recognition(), 1.5)
            return
        try:
            import os
            from modules.livekit_client import (
                LiveKitSubscribeClient,
                livekit_publish_kwargs_from_config,
            )
            _LK_PUBLISH = os.environ.get("VC_LK_PUBLISH", "0") == "1"
            lk = LiveKitSubscribeClient(
                audio_backchannel=self.talkback,
                on_video_frame=None,
                publish_av=_LK_PUBLISH,
                **livekit_publish_kwargs_from_config(self.cfg),
            )
            lk.start()
            self.ctx.lk_session = lk
            LOG.info(
                "LiveKit session avviata post go2rtc pause (publish_av=%s)",
                _LK_PUBLISH,
            )
            Clock.schedule_once(
                lambda *_: self.start_call_visitor_recognition(), 2.5)
        except Exception as e:
            LOG.warning("LiveKit start post-pause err: %s", e)

    def _release_call_camera(self) -> None:
        """Ferma LiveKit e rilascia libcamera prima di riavviare go2rtc."""
        self.stop_call_visitor_recognition()
        lk = getattr(self.ctx, "lk_session", None)
        if lk is not None:
            try:
                lk.stop(timeout=8.0)
            except Exception as e:
                LOG.warning("LiveKit stop err: %s", e)
            self.ctx.lk_session = None
        try:
            from modules.camera_session import PicamSession
            PicamSession.instance().release()
        except Exception as e:
            LOG.warning("PicamSession.release post-call err: %s", e)

    def _schedule_post_call_camera(self, target_screen: str,
                                   ref: str = "call") -> None:
        """Dopo chiamata: attendi libcamera libera, riavvia go2rtc, poi motion.

        `ref` deve combaciare col tag passato a pause_for_camera: il modulo
        go2rtc_control conta i riferimenti, e rilasciarne uno con un tag diverso
        lascerebbe il contatore appeso (go2rtc non ripartirebbe piu'). Lo usa
        anche l'anteprima on-demand, con tag "preview".
        """
        def _resume_go2rtc(_dt):
            from modules.go2rtc_control import (
                wait_camera_free, resume_after_camera,
                ensure_running_for_motion,
            )
            if not wait_camera_free(timeout=10.0):
                LOG.warning("libcamera ancora occupata post-chiamata, retry go2rtc")
            on_camera_screen = self.sm.current in ("face", "pin", "nfc")
            resume_after_camera(ref)
            if on_camera_screen:
                LOG.debug(
                    "go2rtc post-chiamata: ref call rilasciato, "
                    "motion skip (screen=%s)", self.sm.current)
                return
            if self._go2rtc_for_motion():
                ensure_running_for_motion(wait_rpicam=True)

            def _start_motion(_dt2):
                if self.sm.current in ("face", "pin", "nfc", "calling", "conversation"):
                    LOG.debug("Motion post-chiamata skip (screen=%s)",
                              self.sm.current)
                    return
                if (self.motion
                        and self._should_start_motion(self.sm.current)
                        and self.sm.current in ("home", "screensaver", "result")):
                    LOG.info("Motion start post-chiamata (screen=%s)",
                             self.sm.current)
                    self.motion.start()

            Clock.schedule_once(_start_motion, 2.0)

        Clock.schedule_once(_resume_go2rtc, 1.5)

    def _ensure_go2rtc_for_motion(self) -> None:
        try:
            from modules.go2rtc_control import ensure_running_for_motion, is_paused
            if not is_paused():
                ensure_running_for_motion()
        except Exception as e:
            LOG.warning("ensure go2rtc for motion err: %s", e)

    # ---------------------------------------------------------------- #
    # Anteprima live on-demand richiesta da Home Assistant
    # ---------------------------------------------------------------- #
    # La card `vc-livekit-preview` in dashboard chiede di vedere l'ingresso
    # fuori chiamata: il Pi entra nella room LiveKit e pubblica camera+mic per
    # un tempo limitato, poi smette da solo.
    #
    # Non e' un flusso permanente per un motivo fisico: libcamera e' esclusiva.
    # Mentre l'anteprima e' attiva, rilevamento movimento e riconoscimento volti
    # locali non possono usare il sensore, ed e' fermo anche go2rtc (rpicam-vid).
    # Da qui il timeout, l'unico modo per garantire che il citofono torni alle
    # sue funzioni anche se la dashboard resta aperta o il browser sparisce
    # senza chiudere la sessione.
    PREVIEW_TTL_DEFAULT = 120
    PREVIEW_TTL_MAX = 600

    def _handle_livekit_preview(self, payload: dict) -> None:
        """{"action":"livekit_preview","on":true,"ttl":120}"""
        if not bool(payload.get("on", True)):
            self._stop_preview_livekit("richiesta di HA")
            return
        try:
            ttl = int(payload.get("ttl") or self.PREVIEW_TTL_DEFAULT)
        except (TypeError, ValueError):
            ttl = self.PREVIEW_TTL_DEFAULT
        self._start_preview_livekit(max(10, min(ttl, self.PREVIEW_TTL_MAX)))

    def _preview_stato(self, stato: str, **extra) -> None:
        """Pubblica lo stato dell'anteprima con retain.

        Retain perche' la card, aprendosi, deve sapere subito se c'e' gia'
        un'anteprima in corso (avviata da un altro dispositivo) invece di
        chiederne una seconda.
        """
        try:
            import json as _json
            topic = (self.cfg.get("mqtt", {}) or {}).get(
                "topic_preview", "videocitofono/preview")
            self.mqtt.publish(
                topic, _json.dumps({"stato": stato, **extra}),
                retain=True, qos=1,
            )
        except Exception as e:
            LOG.warning("preview stato publish err: %s", e)

    def _start_preview_livekit(self, ttl_sec: int) -> None:
        if self.sm.current in ("calling", "conversation"):
            # Durante la chiamata il video del visitatore e' gia' nella room,
            # pubblicato da lk_session: una seconda sessione con identity 'rpi'
            # espellerebbe la prima.
            LOG.info("anteprima ignorata: chiamata in corso")
            self._preview_stato("in_chiamata")
            return
        if self.sm.current == "face":
            LOG.info("anteprima ignorata: riconoscimento volto in corso")
            self._preview_stato("occupato", motivo="riconoscimento volto")
            return
        if getattr(self.ctx, "lk_preview", None) is not None:
            # Gia' attiva: la richiesta vale come rinnovo del tempo residuo.
            self._arm_preview_timeout(ttl_sec)
            self._preview_stato("on", scade_in=ttl_sec)
            LOG.info("anteprima prolungata (%ds)", ttl_sec)
            return

        LOG.info("anteprima: libero libcamera (ttl=%ds)", ttl_sec)
        if self.motion:
            self._motion_stop_fast()
        pause_for_camera("preview")
        self._preview_camera_held = True
        try:
            from modules.camera_session import PicamSession
            PicamSession.instance().release()
        except Exception as e:
            LOG.warning("PicamSession.release preview err: %s", e)
        self._preview_stato("avvio", scade_in=ttl_sec)
        # Stesso ritardo usato per la chiamata: rpicam-vid deve aver mollato
        # libcamera, altrimenti il publisher LiveKit non apre il sensore.
        Clock.schedule_once(lambda *_: self._preview_connect(ttl_sec), 0.8)

    def _preview_connect(self, ttl_sec: int) -> None:
        if self.sm.current in ("calling", "conversation"):
            # Campanello suonato durante gli 800 ms di attesa: vince la chiamata.
            LOG.info("anteprima annullata: chiamata arrivata durante l'avvio")
            self._stop_preview_livekit("chiamata in arrivo", riavvia_go2rtc=False)
            return
        try:
            from modules.livekit_client import LiveKitSubscribeClient
            # Anteprima piu' leggera della chiamata (che pubblica 1080p a
            # 6 Mbps): qui serve capire chi c'e' alla porta, spesso guardando da
            # rete mobile, quindi 720p a 12 fps. Meno banda e meno lavoro per il
            # Pi, che intanto ha comunque fermato go2rtc e il motion.
            lkcfg = (self.cfg.get("livekit") or {})
            lk = LiveKitSubscribeClient(
                # Nessun backchannel audio: la card chiede un token senza
                # diritto di pubblicare, quindi non c'e' voce in arrivo da
                # riprodurre sull'altoparlante del citofono.
                audio_backchannel=None,
                on_video_frame=None,
                # Forzato a True e non legato a VC_LK_PUBLISH: senza publish
                # l'anteprima non avrebbe nulla da mostrare.
                publish_av=True,
                publish_video_size=(
                    int(lkcfg.get("preview_width", 1280)),
                    int(lkcfg.get("preview_height", 720)),
                ),
                publish_video_fps=int(lkcfg.get("preview_fps", 12)),
                publish_video_bitrate=int(lkcfg.get("preview_bitrate", 2_000_000)),
            )
            lk.start()
            self.ctx.lk_preview = lk
            self._arm_preview_timeout(ttl_sec)
            self._preview_stato("on", scade_in=ttl_sec)
            LOG.info("anteprima attiva (ttl=%ds)", ttl_sec)
        except Exception as e:
            LOG.warning("anteprima start err: %s", e)
            self._preview_stato("errore", motivo=str(e)[:120])
            self._stop_preview_livekit("errore di avvio")

    def _arm_preview_timeout(self, ttl_sec: int) -> None:
        ev = getattr(self, "_preview_timer", None)
        if ev is not None:
            ev.cancel()
        self._preview_timer = Clock.schedule_once(
            lambda *_: self._stop_preview_livekit("tempo scaduto"), ttl_sec)

    def _stop_preview_livekit(self, motivo: str = "",
                             riavvia_go2rtc: bool = True) -> None:
        """Chiude l'anteprima e restituisce la camera alle funzioni locali.

        `riavvia_go2rtc=False` quando subentra qualcosa che vuole libcamera
        libera (chiamata, schermata volto): il riferimento su go2rtc va
        rilasciato comunque, altrimenti il contatore resta appeso e rpicam-vid
        non ripartirebbe piu' nemmeno a citofono inattivo.
        """
        ev = getattr(self, "_preview_timer", None)
        if ev is not None:
            ev.cancel()
            self._preview_timer = None

        lk = getattr(self.ctx, "lk_preview", None)
        if lk is not None:
            try:
                lk.stop(timeout=4.0)
            except Exception as e:
                LOG.warning("anteprima stop err: %s", e)
            self.ctx.lk_preview = None
            LOG.info("anteprima fermata (%s)", motivo or "-")

        if not getattr(self, "_preview_camera_held", False):
            self._preview_stato("off", motivo=motivo)
            return
        self._preview_camera_held = False
        try:
            from modules.camera_session import PicamSession
            PicamSession.instance().release()
        except Exception as e:
            LOG.warning("PicamSession.release post-anteprima err: %s", e)
        if riavvia_go2rtc:
            self._schedule_post_call_camera(self.sm.current, ref="preview")
        else:
            try:
                from modules.go2rtc_control import resume_after_camera
                resume_after_camera("preview", start_service=False)
            except Exception as e:
                LOG.warning("resume_after_camera preview err: %s", e)
        self._preview_stato("off", motivo=motivo)

    def _mqtt_republish_idle(self) -> None:
        """Dopo reconnect: se non siamo in chiamata, HA non deve restare ON."""
        cur = ""
        if getattr(self, "sm", None) is not None:
            cur = str(getattr(self.sm, "current", "") or "")
        if cur in ("calling", "conversation"):
            return
        try:
            self.mqtt.publish_chiamata("terminata", "")
            LOG.info("MQTT chiamata idle retain (screen=%s)", cur or "n/a")
        except Exception as e:
            LOG.warning("MQTT idle publish err: %s", e)

    def _handle_chiamata(self, stato: str) -> None:
        """MQTT `videocitofono/chiamata`:
          - "annullata"          -> torna subito a home (chiusura
            iniziata dal RPi stesso, niente feedback)
          - "risposto" / "risposto_video" -> rispondente HA ha risposto
            con video: transition CallingScreen -> ConversationScreen.
          - "risposto_audio"     -> risposta solo audio: RPi resta su
            CallingScreen (video visitatore gia' trasmesso via LiveKit).
          - "porta_aperta"       -> overlay "Porta aperta" 3s -> home
            (su CallingScreen e ConversationScreen)
          - "terminata"          -> overlay "Chiamata terminata" 3s ->
            home (su CallingScreen e ConversationScreen)

        Idempotente: se il messaggio e' eco del nostro stesso publish
        (RPi pubblica annullata e riceve la propria copia), il
        transition e' no-op (siamo gia' a home).
        """
        LOG.info("chiamata stato=%r (current=%s)", stato, self.sm.current)
        # Qualsiasi terminazione/transizione chiamata (annullata,
        # porta_aperta, terminata) ferma il consumer audio-only WebRTC
        # se attivo: il rispondente ha chiuso o aperto porta -> nessuna
        # voce piu' in arrivo. Idempotente.
        try:
            if stato in ("annullata", "porta_aperta", "terminata"):
                if getattr(self, "webrtc_audio", None) and self.webrtc_audio.active:
                    self.webrtc_audio.stop()
        except Exception:
            pass
        try:
            if stato == "annullata":
                if self.sm.current in ("calling", "conversation"):
                    self.sm.current = "home"
                return
            if stato == "chiamata_in_corso":
                # Trigger MQTT da HA (es. script test_chiamata) o eco
                # del nostro stesso publish dal _on_physical_button.
                # Idempotente: se siamo gia' in calling/conversation,
                # ignoriamo (e' eco). Altrimenti apriamo CallingScreen
                # leggendo il campanello dall'ultimo payload JSON.
                if self.sm.current in ("calling", "conversation"):
                    return
                camp_id = (getattr(self.mqtt, "last_campanello", "") or "").strip()
                if not camp_id:
                    cmps = self.cfg.get("campanelli", []) or []
                    camp_id = (cmps[0].get("id") if cmps else "") or "default"
                # Ricava il nominativo dall'elenco campanelli configurato.
                camp_nome = camp_id
                for c in (self.cfg.get("campanelli", []) or []):
                    if c.get("id") == camp_id:
                        camp_nome = c.get("nome", camp_id) or camp_id
                        break
                try:
                    if self.sm.has_screen("calling"):
                        calling = self.sm.get_screen("calling")
                        if hasattr(calling, "imposta_chiamata"):
                            calling.imposta_chiamata(camp_id, camp_nome)
                        self.on_activity("mqtt_chiamata")
                        self.sm.current = "calling"
                except Exception as e:
                    LOG.error("transizione a calling da MQTT err: %s", e)
                return
            if stato in ("risposto", "risposto_video"):
                # Rispondente HA ha risposto con video: mostriamo la
                # ConversationScreen (video del rispondente). Solo se
                # eravamo in calling: se siamo gia' in conversation
                # (eco/duplicato o upgrade audio->video) NOP.
                if self.sm.current == "calling" and self.sm.has_screen("conversation"):
                    self.sm.current = "conversation"
                return
            if stato == "risposto_audio":
                if self.sm.current == "calling":
                    try:
                        calling = self.sm.get_screen("calling")
                        if hasattr(calling, "mostra_risposto_audio"):
                            calling.mostra_risposto_audio()
                    except Exception as e:
                        LOG.warning("mostra_risposto_audio err: %s", e)
                return
            # Mappa payload -> metodo da invocare sulla schermata corrente.
            # Le screens implementano lo stesso contract:
            # mostra_porta_aperta() / mostra_chiamata_terminata().
            metodo_per_stato = {
                "porta_aperta": "mostra_porta_aperta",
                "terminata": "mostra_chiamata_terminata",
            }
            metodo = metodo_per_stato.get(stato)
            if not metodo:
                return
            if self.sm.current not in ("calling", "conversation"):
                return
            screen = self.sm.get_screen(self.sm.current)
            fn = getattr(screen, metodo, None)
            if callable(fn):
                fn()
            else:
                # Screen non implementa l'overlay (compat): fallback home.
                self.sm.current = "home"
        except Exception as e:
            LOG.error("handle_chiamata err: %s", e)

    def _handle_responder_video(self, raw: str) -> None:
        """Trigger MQTT da HA: il browser ha avviato/chiuso il WHIP
        publish del video del rispondente.

        on  -> mostra ConversationScreen (pulla RTSP responder_av da HA).
        off -> il video del rispondente si e' chiuso. Comportamento:
            * se siamo in conversation con un overlay attivo
              (porta_aperta / chiamata terminata gia' in corso), NON
              fare alcuna transition: il _hold_e_chiudi gestira' il
              ritorno a home dopo HOLD_SEC. Senza questo guard, il
              cleanup uplink eseguito da HA dopo apri_porta/chiudi
              farebbe sparire l'overlay a meta'.
            * altrimenti torna a "home" (la chiamata e' finita lato
              rispondente, non vogliamo riaprire CallingScreen che
              ri-pubblicherebbe chiamata_in_corso).
        """
        LOG.info("responder_video=%s (current=%s)", raw, self.sm.current)
        try:
            if raw == "on":
                if self.sm.has_screen("conversation"):
                    # Upgrade audio->video: ferma il consumer audio-only
                    # standalone per evitare doppio sink ffmpeg/PulseAudio.
                    # ConversationScreen apre il proprio pc audio+video.
                    try:
                        if getattr(self, "webrtc_audio", None) and self.webrtc_audio.active:
                            LOG.info("upgrade audio->video: stop WebRTCAudioController")
                            self.webrtc_audio.stop()
                    except Exception:
                        pass
                    self.on_activity("responder_video_on")
                    self.sm.current = "conversation"
            elif raw == "off":
                if self.sm.current == "conversation":
                    try:
                        screen = self.sm.get_screen("conversation")
                        if getattr(screen, "overlay_text", ""):
                            LOG.info("responder_video=off ignorato: overlay '%s' attivo",
                                     screen.overlay_text)
                            return
                    except Exception:
                        pass
                    self.sm.current = "home"
        except Exception as e:
            LOG.error("handle_responder_video err: %s", e)

    def _handle_responder_audio(self, raw: str) -> None:
        """Trigger MQTT da HA: il browser ha avviato/chiuso il WHIP
        publish audio-only (modalita' "Risposta audio", senza video del
        rispondente).

        on  -> avvia WebRTCAudioController (consumer aiortc audio Opus
               da go2rtc HA stream responder_av). RPi resta su
               CallingScreen e sente la voce del rispondente.
        off -> ferma il consumer e chiude il player ffmpeg.

        Se nel frattempo il rispondente fa upgrade a video
        (responder_video=on), ConversationScreen apre il proprio pc
        audio+video; per evitare doppio sink ffmpeg fermiamo qui il
        consumer audio-only quando entra in conversation.
        """
        LOG.info("responder_audio=%s (current=%s)", raw, self.sm.current)
        try:
            if raw == "on":
                if self.sm.current == "conversation":
                    LOG.info("responder_audio=on ma siamo in conversation, "
                             "audio gia' gestito li, skip controller standalone")
                    return
                self.on_activity("responder_audio_on")
                self.webrtc_audio.start()
            elif raw == "off":
                self.webrtc_audio.stop()
        except Exception as e:
            LOG.error("handle_responder_audio err: %s", e)

    def _handle_cmd(self, payload: dict) -> None:
        """Gestisce comandi remoti via MQTT 'videocitofono/cmd'.

        Azioni supportate:
          {"action":"wake"}                                  - sveglia schermo
          {"action":"show","screen":"home"}                  - cambia screen
          {"action":"restart_app"}                           - systemctl restart videocitofono
          {"action":"reboot"}                                - systemctl reboot
          {"action":"set_config","config":{...}}             - merge in config.override.yaml + restart
          {"action":"enroll_face"}                           - avvia iscrizione volto
          {"action":"enroll_fingerprint"}                    - avvia iscrizione impronta (stub)
          {"action":"set_admin_pin","pin":"1234"}            - cambia PIN admin
          {"action":"set_sfondi_library","files":[...],"base_url":"/local/vc-sfondi/"}
              - HA notifica nuova lista sfondi: il RPi pre-scarica i file (best-effort).
          {"action":"livekit_preview","on":true,"ttl":120}
              - anteprima live on-demand: pubblica camera+mic in LiveKit fuori
                chiamata per `ttl` secondi (on:false chiude subito).
        """
        import subprocess
        try:
            if not isinstance(payload, dict):
                return
            if not self.cmd_auth.verify(payload):
                self.mqtt.publish_evento("cmd_rejected", {"reason": "auth"})
                return
            action = payload.get("action")
            if action and not self.cmd_auth.allow_dangerous(str(action)):
                self.mqtt.publish_evento(
                    "cmd_rejected", {"reason": "rate_limit", "action": action})
                return
            if action == "simulate_doorbell":
                # Trigger di test/QA: simula la pressione del pulsante
                # campanello. Pubblicato dal pulsante "Simula campanello"
                # nella dashboard HA (view Videocitofono). Equivalente a
                # SIGUSR1 ma raggiungibile da qualunque client HA.
                camp_id = payload.get("campanello") or ""
                campanelli = self.cfg.get("campanelli", []) or []
                target = None
                if camp_id:
                    target = next((c for c in campanelli if c.get("id") == camp_id), None)
                if target is None and campanelli:
                    target = campanelli[0]
                if not target:
                    LOG.warning("simulate_doorbell: nessun campanello disponibile")
                    return
                LOG.info("MQTT simulate_doorbell -> %s", target.get("id"))
                self._on_physical_button(target.get("id", "default"),
                                         target.get("nome", "Test"))
            elif action == "wake":
                self.on_activity("mqtt_cmd")
            elif action == "show" and payload.get("screen") in self.sm.screen_names:
                self.on_activity("mqtt_cmd")
                self.sm.current = payload["screen"]
            elif action == "restart_app":
                LOG.warning("restart_app via MQTT")
                self.mqtt.publish_evento("restart_app_request")
                # esegue dopo 1s in thread separato per dare tempo a publish/MQTT
                def _restart():
                    import time as _t
                    _t.sleep(1.0)
                    subprocess.run(["sudo", "/bin/systemctl", "restart", "videocitofono.service"],
                                   check=False)
                threading.Thread(target=_restart, daemon=True).start()
            elif action == "reboot":
                LOG.warning("reboot via MQTT")
                self.mqtt.publish_evento("reboot_request")
                def _reboot():
                    import time as _t
                    _t.sleep(1.0)
                    subprocess.run(["sudo", "/sbin/reboot"], check=False)
                threading.Thread(target=_reboot, daemon=True).start()
            elif action == "livekit_preview":
                self._handle_livekit_preview(payload)
            elif action == "install_deps":
                self._handle_install_deps(payload)
            elif action == "set_config":
                self._queue_config_override(
                    payload.get("config", {}),
                    persist_default=bool(payload.get("persist_default")),
                )
            elif action == "set_sfondi_library":
                self._sync_sfondi_library(
                    payload.get("files") or [],
                    payload.get("base_url") or "/local/vc-sfondi/",
                )
            elif action == "set_icone_library":
                self._sync_icone_library(
                    payload.get("files") or [],
                    payload.get("base_url") or "/local/vc-icone/",
                )
            elif action == "enroll_face":
                self._handle_enroll_face(payload)
            elif action == "delete_face":
                self._handle_delete_face(payload)
            elif action == "update_face":
                self._handle_update_face(payload)
            elif action == "rename_face":
                self._handle_rename_face(payload)
            elif action == "set_face_pin":
                self._handle_set_face_pin(payload)
            elif action == "list_faces":
                self._publish_volti_library()
            elif action == "list_auto_faces":
                self._publish_auto_faces_list(payload.get("nome", ""))
            elif action == "delete_auto_face":
                self._handle_delete_auto_face(payload)
            elif action == "purge_auto_faces":
                self._handle_purge_auto_faces(payload)
            elif action == "enroll_fingerprint":
                fp = getattr(self, "fingerprint_reader", None)
                if fp is None or not fp.is_available():
                    self.mqtt.publish_evento(
                        "enroll_fingerprint_error",
                        {"error": fp.last_error() if fp else "modulo disabilitato"})
                    return
                self.mqtt.publish_evento("enroll_fingerprint_started")
            elif action == "guest_pin_create":
                self._handle_guest_pin_create(payload)
            elif action == "guest_pin_revoke":
                self._handle_guest_pin_revoke(payload)
            elif action == "guest_pin_list":
                self._publish_guest_pin_list()
            elif action == "nfc_enroll":
                self._handle_nfc_enroll(payload)
            elif action == "nfc_delete":
                self._handle_nfc_delete(payload)
            elif action == "nfc_list":
                self._publish_nfc_library()
            elif action == "set_admin_pin":
                pin = str(payload.get("pin", "")).strip()
                if pin and pin.isdigit() and 4 <= len(pin) <= 8:
                    try:
                        self.pin_manager.set_admin_pin(pin)
                        self.mqtt.publish_evento("admin_pin_changed")
                        LOG.info("Admin PIN aggiornato (len=%d)", len(pin))
                    except Exception as e:
                        LOG.error("set_admin_pin err: %s", e)
                        self.mqtt.publish_evento("admin_pin_error", {"error": str(e)})
                else:
                    LOG.warning("PIN non valido (4-8 cifre): %r", pin)
            else:
                LOG.warning("cmd MQTT ignorato: %s", payload)
        except Exception as e:
            LOG.error("cmd handler err: %s", e)

    def _nfc_cfg_snapshot(self) -> dict:
        """Snapshot normalizzato della sezione nfc per confronti idempotenti."""
        nfc_cfg = self.cfg.get("nfc", {}) or {}
        cands = nfc_cfg.get("device_candidates") or ()
        if isinstance(cands, list):
            cands = tuple(cands)
        return {
            "enabled": bool(nfc_cfg.get("enabled", False)),
            "device": str(nfc_cfg.get("device", "tty:USB0:pn532")),
            "library_path": str(nfc_cfg.get(
                "library_path", "/opt/videocitofono/data/nfc_tags.json")),
            "cooldown_sec": float(nfc_cfg.get("cooldown_sec", 2.0)),
            "device_candidates": cands,
        }

    def _init_nfc_from_cfg(self) -> None:
        """Avvia lettore NFC + library da self.cfg['nfc']."""
        snap = self._nfc_cfg_snapshot()
        if not snap["enabled"]:
            self._nfc_cfg_active = None
            return
        try:
            from modules.nfc_reader import (
                prepare_nfc_hardware, nfc_prep_mode, USB_REOPEN_SETTLE_SEC,
                ensure_pn532_ready, disable_ch340_autosuspend,
            )
            prep_mode = nfc_prep_mode()
            if prep_mode != "skip":
                LOG.info("NFC prep pre-start (%s)", prep_mode)
                prepare_nfc_hardware(prep_mode)
            else:
                LOG.info("NFC prep: skip reset USB (ExecStartPre recente), wake UART")
                disable_ch340_autosuspend()
                if not ensure_pn532_ready(snap["device"], attempts=4):
                    LOG.warning("NFC: wake UART fallito, reset USB completo")
                    prepare_nfc_hardware("recover")
            time.sleep(USB_REOPEN_SETTLE_SEC)
            self.nfc_lib = NfcLibrary(path=snap["library_path"])
            self.nfc_reader = NfcReader(
                device=snap["device"],
                cooldown_sec=snap["cooldown_sec"],
                device_candidates=list(snap["device_candidates"]) or None,
                hw_prep_done=True,
                on_tag=lambda uid: Clock.schedule_once(
                    lambda *_: self._on_nfc_tag(uid), 0),
            )
            if self.nfc_reader.is_available():
                self.nfc_reader.start()
                self._nfc_cfg_active = snap
                LOG.info("NFC reader avviato (device=%s)",
                         self.nfc_reader.device)
            else:
                LOG.warning("nfcpy non installato; NFC disattivato")
                self.nfc_reader = None
                self._nfc_cfg_active = None
        except Exception as _e:
            LOG.warning("NFC init err: %s", _e)
            self.nfc_reader = None
            self._nfc_cfg_active = None

    def _stop_nfc(self) -> None:
        if self.nfc_reader is not None:
            try:
                self.nfc_reader.stop(fast=True)
            except Exception:
                pass
            self.nfc_reader = None
        self._nfc_cfg_active = None
        try:
            from modules.nfc_reader import NFC_PREP_STAMP
            if os.path.isfile(NFC_PREP_STAMP):
                os.remove(NFC_PREP_STAMP)
        except OSError:
            pass

    def _apply_nfc_live(self) -> None:
        """Riavvia il lettore NFC solo se la config hardware e' cambiata."""
        snap = self._nfc_cfg_snapshot()
        if not snap["enabled"]:
            self._stop_nfc()
            self.nfc_lib = None
            LOG.info("NFC disabilitato via config live")
            return
        if (self.nfc_reader is not None
                and getattr(self, "_nfc_cfg_active", None) == snap):
            thr = getattr(self.nfc_reader, "_thread", None)
            if thr and thr.is_alive():
                LOG.info("NFC live: skip restart (config invariata)")
                if self.nfc_lib is None:
                    try:
                        self.nfc_lib = NfcLibrary(path=snap["library_path"])
                    except Exception as e:
                        LOG.warning("NFC lib reload err: %s", e)
                return

        def _restart() -> None:
            self._stop_nfc()
            time.sleep(1.0)
            Clock.schedule_once(lambda *_: self._init_nfc_from_cfg(), 0)

        threading.Thread(
            target=_restart, name="nfc-restart", daemon=True).start()

    def _apply_motion_live(self, motion_cfg: dict | None = None) -> None:
        """Aggiorna motion senza restart del servizio (soglie, enabled)."""
        if motion_cfg is not None:
            if not isinstance(motion_cfg, dict):
                return
            cur = self.cfg.get("motion", {}) or {}
            cur.update({k: v for k, v in motion_cfg.items() if v is not None})
            self.cfg["motion"] = cur
        mcfg = self.cfg.get("motion", {}) or {}
        if "wake_screensaver" in mcfg:
            self._wake_screensaver_on_motion = bool(
                mcfg.get("wake_screensaver", True))
        enabled = mcfg.get("enabled", True)
        mot = self.motion
        if not enabled:
            if mot and hasattr(mot, "stop"):
                mot.stop()
            self.motion = None
            LOG.info("motion disabilitato via config live")
            return
        if mot is None:
            LOG.info("motion live: abilitato ma detector non attivo "
                     "(verra' avviato al prossimo ingresso home)")
            return
        for key, cast in (
            ("area_thresh_pct", float),
            ("pixel_thresh", int),
            ("cooldown_sec", float),
        ):
            if key in mcfg:
                try:
                    setattr(mot, key, cast(mcfg[key]))
                except Exception as e:
                    LOG.warning("motion live %s err: %s", key, e)
        LOG.info("motion live aggiornato: enabled=%s area=%s",
                 enabled, getattr(mot, "area_thresh_pct", "?"))

    def _handle_install_deps(self, payload: dict) -> None:
        """pip install nel venv locale (es. nfcpy dopo deploy config)."""
        import subprocess as _sp
        pkgs = payload.get("packages")
        if not pkgs:
            pkgs = ["nfcpy>=1.0.4", "pyusb>=1.2"]
        elif isinstance(pkgs, str):
            pkgs = [pkgs]
        pip = "/opt/videocitofono/venv/bin/pip"
        if not os.path.isfile(pip):
            pip = "pip3"
        cmd = [pip, "install", "--upgrade"] + list(pkgs)
        LOG.info("install_deps: %s", " ".join(cmd))

        def _run():
            try:
                r = _sp.run(cmd, capture_output=True, text=True, timeout=600,
                            check=False)
                ok = r.returncode == 0
                self.mqtt.publish_evento(
                    "install_deps_done" if ok else "install_deps_error",
                    {"returncode": r.returncode,
                     "stderr": (r.stderr or "")[-500:]})
                if ok:
                    self._apply_nfc_live()
            except Exception as e:
                self.mqtt.publish_evento("install_deps_error", {"error": str(e)})

        threading.Thread(target=_run, daemon=True, name="install-deps").start()

    def _queue_config_override(self, override: dict,
                               persist_default: bool = False) -> None:
        """Accoda override HA e applica una sola volta dopo debounce."""
        if not isinstance(override, dict) or not override:
            LOG.warning("set_config: override vuoto o non valido")
            return
        pending = getattr(self, "_config_pending", None) or {}
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(pending.get(k), dict):
                pending[k] = _deep_merge(pending[k], v)
            else:
                pending[k] = v
        self._config_pending = pending
        if persist_default:
            self._config_pending_persist = True
        if self._config_debounce_ev is not None:
            return
        sec = float(getattr(self, "_CONFIG_DEBOUNCE_SEC", 10.0))
        LOG.info("set_config accodato (%d chiavi), apply tra %.0fs",
                 len(override), sec)
        self._config_debounce_ev = Clock.schedule_once(
            self._flush_config_override, sec)

    def _flush_config_override(self, *_dt) -> None:
        self._config_debounce_ev = None
        pending = getattr(self, "_config_pending", {}) or {}
        persist = bool(getattr(self, "_config_pending_persist", False))
        self._config_pending = {}
        self._config_pending_persist = False
        if not pending:
            return
        LOG.info("set_config debounce: apply %d chiavi", len(pending))
        self._apply_config_override(pending, persist_default=persist)

    def _on_connectivity_mode_change(self, mode: str) -> None:
        try:
            home = self.sm.get_screen("home")
            home.set_service_mode(mode)
        except Exception:
            pass
        if mode != "online":
            return
        conn = getattr(self, "connectivity", None)
        if conn is None:
            return
        for camp_id, nome in conn.pop_pending_calls():
            try:
                LOG.info("flush chiamata accodata: %s (%s)", camp_id, nome)
                self.sm.get_screen("home")._chiama(camp_id, nome)
            except Exception as e:
                LOG.warning("flush pending call err: %s", e)

    def _health_camera_status(self) -> str:
        cur = getattr(self.sm, "current", "") if getattr(self, "sm", None) else ""
        if cur in ("calling", "conversation", "face"):
            return cur
        try:
            from modules.go2rtc_control import _service_active, _rpicam_running, is_paused
            if is_paused():
                return "paused"
            if _service_active() and _rpicam_running():
                return "go2rtc"
        except Exception:
            pass
        return cur or "idle"

    def _health_subsystems(self) -> dict:
        """Stato sintetico sottosistemi per health MQTT / alert HA."""
        subs: dict = {}
        nfc_cfg = (self.cfg.get("nfc") or {})
        nr = getattr(self, "nfc_reader", None)
        if nfc_cfg.get("enabled", False):
            if nr and nr.is_reader_ready():
                subs["nfc_status"] = "ok"
            else:
                subs["nfc_status"] = "down"
                err = nr.last_error() if nr is not None else "no_reader"
                if err:
                    subs["nfc_error"] = str(err)[:160]
        else:
            subs["nfc_status"] = "off"
        try:
            from modules.go2rtc_control import (
                _service_active, _rpicam_running, is_paused,
            )
            if is_paused():
                subs["go2rtc_status"] = "paused"
            elif _service_active() and _rpicam_running():
                subs["go2rtc_status"] = "ok"
            elif self._eco_enabled() and not self._go2rtc_for_motion():
                subs["go2rtc_status"] = "idle"
            else:
                subs["go2rtc_status"] = "down"
        except Exception:
            subs["go2rtc_status"] = "unknown"
        eng = getattr(self.face, "engine_name", "disabled")
        subs["face_engine_status"] = eng if eng != "disabled" else "off"
        mcfg = (self.cfg.get("motion") or {})
        mot = getattr(self, "motion", None)
        screen = getattr(self.sm, "current", "home") if hasattr(self, "sm") else "home"
        if not mcfg.get("enabled", True):
            subs["motion_status"] = "off"
        elif isinstance(mot, MotionDetector):
            subs["motion_status"] = "ok"
        else:
            th = getattr(mot, "_thread", None) if mot is not None else None
            running = bool(mot is not None and th and th.is_alive())
            if running:
                subs["motion_status"] = "ok"
            elif screen == "screensaver":
                subs["motion_status"] = "down"
            else:
                subs["motion_status"] = "idle"
        fp_cfg = (self.cfg.get("fingerprint") or {})
        fp = getattr(self, "fingerprint_reader", None)
        if not fp_cfg.get("enabled", False):
            subs["fingerprint_status"] = "off"
        elif fp and fp.is_reader_ready():
            subs["fingerprint_status"] = "ok"
        else:
            # enabled ma stub/assente: non "idle", altrimenti HA crede che
            # il lettore sia in ascolto.
            subs["fingerprint_status"] = "down"
        lk = getattr(self.ctx, "lk_session", None)
        if lk:
            subs["livekit_status"] = "active"
        elif getattr(self.ctx, "lk_preview", None) is not None:
            subs["livekit_status"] = "preview"
        else:
            subs["livekit_status"] = "idle"
        subs["mqtt_connected"] = bool(self.mqtt.is_connected())
        conn = getattr(self, "connectivity", None)
        if conn is not None:
            subs["service_mode"] = conn.service_mode
            subs["pending_calls"] = conn.pending_calls_count
        else:
            subs["service_mode"] = "online" if subs["mqtt_connected"] else "limited"
            subs["pending_calls"] = 0
        if lk and getattr(lk, "active", False):
            try:
                lk_stats = lk.get_call_stats() if hasattr(lk, "get_call_stats") else {}
                if lk_stats.get("rtt_ms") is not None:
                    subs["lk_rtt_ms"] = lk_stats["rtt_ms"]
                if lk_stats.get("connection_quality"):
                    subs["lk_quality"] = lk_stats["connection_quality"]
                if lk_stats.get("packet_loss") is not None:
                    subs["lk_packet_loss"] = lk_stats["packet_loss"]
            except Exception:
                pass
        down = [k for k, v in subs.items()
                if k.endswith("_status") and v == "down"]
        if down:
            subs["status_summary"] = (
                "down" if len(down) >= 2 else "degraded")
            subs["status_down"] = ",".join(down)
        else:
            subs["status_summary"] = "ok"
            subs["status_down"] = ""
        return subs

    def _apply_config_override(self, override: dict,
                               persist_default: bool = False) -> None:
        """Salva override in /opt/videocitofono/app/config/config.override.yaml.

        Per le chiavi 'live' (es. campanelli) applica subito senza restart.
        Per altre chiavi schedula restart del servizio.
        Se persist_default=True, le stesse chiavi vengono scritte anche in
        config.yaml (default di fabbrica al prossimo boot senza override).
        """
        if not isinstance(override, dict) or not override:
            LOG.warning("set_config: override vuoto o non valido")
            return
        import yaml as _yaml, threading as _th, subprocess as _sp, time as _t
        path = "/opt/videocitofono/app/config/config.override.yaml"
        try:
            existing = {}
            if os.path.exists(path):
                with open(path) as f:
                    existing = _yaml.safe_load(f) or {}
            for k, v in override.items():
                if isinstance(v, dict) and isinstance(existing.get(k), dict):
                    existing[k].update(v)
                else:
                    existing[k] = v
            with open(path, "w") as f:
                _yaml.safe_dump(existing, f, allow_unicode=True, sort_keys=False)
            LOG.info("config.override.yaml aggiornato: keys=%s", list(override.keys()))
            if persist_default:
                self._persist_config_defaults(existing, override.keys())
            self.mqtt.publish_evento("config_updated", {"keys": list(override.keys()),
                                                        "persist_default": persist_default})

            # Applica live le chiavi gestibili a caldo. I flag enabled di
            # pin/face_recognition/fingerprint/nfc sono live perche'
            # influenzano solo la visibilita' dei pulsanti su HomeScreen.
            live_keys = {"campanelli", "ui", "audio", "access_icons", "tts",
                         "motion", "pin", "face_recognition", "fingerprint", "nfc"}
            method_keys = {"pin", "face_recognition", "fingerprint", "nfc"}
            applied_live = set()
            for k in list(override.keys()):
                if k not in live_keys:
                    continue
                # Merge live in self.cfg cosi' i live-applier leggono
                # i valori aggiornati senza dover ricaricare il file.
                if k in method_keys:
                    cur = self.cfg.get(k, {}) or {}
                    if isinstance(cur, dict) and isinstance(override[k], dict):
                        cur.update(override[k])
                        self.cfg[k] = cur
                    else:
                        self.cfg[k] = override[k]
                if k == "campanelli":
                    self._apply_campanelli_live(override[k])
                elif k == "ui":
                    self._apply_ui_live(override[k])
                elif k == "audio":
                    self._apply_audio_live(override[k])
                elif k == "access_icons":
                    self._apply_access_icons_live(override[k])
                elif k == "tts":
                    self._apply_tts_live(override[k])
                elif k == "motion":
                    self._apply_motion_live(override[k])
                elif k == "face_recognition":
                    self._apply_face_recognition_live(override[k])
                    self._apply_access_methods_live()
                elif k == "nfc":
                    self._apply_nfc_live()
                    self._apply_access_methods_live()
                elif k in method_keys:
                    self._apply_access_methods_live()
                applied_live.add(k)

            if {"campanelli", "access_icons"} & applied_live:
                Clock.schedule_once(
                    lambda *_: self._sync_icons_from_config(), 0)

            remaining = set(override.keys()) - applied_live
            if not remaining:
                LOG.info("Override applicato live, nessun restart necessario")
                return

            LOG.info("Restart richiesto per chiavi: %s", sorted(remaining))
            def _restart():
                _t.sleep(1.5)
                _sp.run(["sudo", "/bin/systemctl", "restart", "videocitofono.service"], check=False)
            _th.Thread(target=_restart, daemon=True).start()
        except Exception as e:
            LOG.error("apply_config_override err: %s", e)
            self.mqtt.publish_evento("config_error", {"error": str(e)})

    def _persist_config_defaults(self, merged_override: dict,
                                 keys) -> None:
        """Scrive in config.yaml le sezioni inviate da HA (default RPi)."""
        import yaml as _yaml
        from modules.config import _deep_merge
        base_path = "/opt/videocitofono/app/config/config.yaml"
        try:
            base = {}
            if os.path.exists(base_path):
                with open(base_path, encoding="utf-8") as f:
                    base = _yaml.safe_load(f) or {}
            patch = {k: merged_override[k] for k in keys if k in merged_override}
            if not patch:
                return
            updated = _deep_merge(base, patch)
            tmp = base_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _yaml.safe_dump(updated, f, allow_unicode=True, sort_keys=False)
            os.replace(tmp, base_path)
            LOG.info("config.yaml default aggiornato: keys=%s", list(patch.keys()))
            self.mqtt.publish_evento("config_defaults_saved",
                                     {"keys": list(patch.keys())})
        except Exception as e:
            LOG.warning("persist_config_defaults err: %s", e)

    def _apply_access_methods_live(self) -> None:
        """Forza ricostruzione bottoniera home dopo cambio dei flag
        enabled di pin/face_recognition/fingerprint/nfc. Il merge dei
        valori in self.cfg e' gia' avvenuto via _apply_config_override.
        """
        def _refresh(*_):
            try:
                if self.sm.has_screen("home"):
                    home = self.sm.get_screen("home")
                    if hasattr(home, "_apply_access_methods"):
                        home._apply_access_methods()
            except Exception as e:
                LOG.error("refresh home access_methods err: %s", e)
        Clock.schedule_once(_refresh, 0)

    def _apply_access_icons_live(self, icons: dict) -> None:
        """Aggiorna access_icons in memoria + forza refresh HomeScreen.

        Le chiavi attese sono pin/face/fingerprint/nfc -> filename in
        app/assets/avatars/ (vuoto = ripristina VectorIcon di default).
        """
        if not isinstance(icons, dict):
            LOG.warning("access_icons live: payload non dict: %r", icons)
            return
        cur = self.cfg.get("access_icons", {}) or {}
        cur.update({k: (v or "") for k, v in icons.items()})
        self.cfg["access_icons"] = cur
        LOG.info("access_icons live aggiornati: %s", cur)
        Clock.schedule_once(lambda *_: self._sync_icons_from_config(), 0)

    def _refresh_icon_screens(self) -> None:
        """Ricarica texture icone su Home e schermata NFC."""
        try:
            if getattr(self, "sm", None) and self.sm.has_screen("home"):
                home = self.sm.get_screen("home")
                if hasattr(home, "_popola_campanelli"):
                    home._popola_campanelli()
                if hasattr(home, "_apply_access_icons"):
                    home._apply_access_icons()
            if getattr(self, "sm", None) and self.sm.has_screen("nfc"):
                nfc_sc = self.sm.get_screen("nfc")
                if hasattr(nfc_sc, "refresh_icon"):
                    nfc_sc.refresh_icon()
        except Exception as e:
            LOG.warning("refresh icon screens err: %s", e)

    def _apply_campanelli_live(self, campanelli: list) -> None:
        """Aggiorna lista campanelli in memoria + ricarica HomeScreen se attiva.

        Schedulato sul main thread Kivy (Clock) per safe-update dei widget.
        """
        if not isinstance(campanelli, list):
            LOG.warning("campanelli live: payload non lista: %r", campanelli)
            return
        clean = []
        for c in campanelli:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id", "")).strip()
            if not cid:
                continue
            clean.append({"id": cid, "nome": str(c.get("nome", cid)).strip() or cid,
                          "icona": c.get("icona", "")})
        self.cfg["campanelli"] = clean
        LOG.info("campanelli live aggiornati: %d items", len(clean))

        def _refresh(*_):
            try:
                if self.sm.has_screen("home"):
                    home = self.sm.get_screen("home")
                    if hasattr(home, "_popola_campanelli"):
                        home._popola_campanelli()
            except Exception as e:
                LOG.error("refresh home post-campanelli err: %s", e)
        Clock.schedule_once(_refresh, 0)

    # ---------- UI live ----------
    SFONDI_DIR = "/opt/videocitofono/app/assets/sfondi"
    AVATARS_DIR = "/opt/videocitofono/app/assets/avatars"

    def _apply_ui_live(self, ui_dict: dict) -> None:
        """Aggiorna a caldo: indirizzo screensaver, brightness, idle/screensaver
        timeout, language, sfondo. Per `sfondo` scarica il file da HA via HTTP
        se non gia' presente nella cache locale."""
        if not isinstance(ui_dict, dict):
            return
        cur_ui = self.cfg.get("ui", {}) or {}
        cur_ui.update({k: v for k, v in ui_dict.items() if v is not None})
        self.cfg["ui"] = cur_ui
        try:
            if "indirizzo" in ui_dict:
                ind = str(ui_dict["indirizzo"]).strip() or "Via Roma 1"
                if self.sm.has_screen("screensaver"):
                    sc = self.sm.get_screen("screensaver")
                    Clock.schedule_once(lambda *_: setattr(sc, "indirizzo", ind), 0)
            if "brightness_idle_pct" in ui_dict or "brightness_active_pct" in ui_dict:
                try:
                    self.brightness.idle_pct = int(cur_ui.get("brightness_idle_pct", 20))
                    self.brightness.active_pct = int(cur_ui.get("brightness_active_pct", 100))
                    self.brightness.active()
                except Exception as e:
                    LOG.warning("brightness live update err: %s", e)
            if "idle_dim_sec" in ui_dict:
                self._idle_dim_sec = int(ui_dict["idle_dim_sec"])
            if "screensaver_timeout_sec" in ui_dict:
                self._screensaver_timeout = int(ui_dict["screensaver_timeout_sec"])
            if "display_off_sec" in ui_dict:
                self._display_off_sec = int(ui_dict["display_off_sec"])
            if "sfondo" in ui_dict:
                sfondo = str(ui_dict["sfondo"]).strip() or "default"
                self._set_sfondo_live(sfondo)
            if "feedback_volume" in ui_dict and getattr(self, "sound", None):
                # HA invia 0..1 (gia' normalizzato dal template); accettiamo
                # anche valori 0..100 per robustezza (backcompat).
                v = float(ui_dict["feedback_volume"])
                if v > 1.0:
                    v = v / 100.0
                self.sound.set_volume(max(0.0, min(1.0, v)))
            if "feedback_enabled" in ui_dict and getattr(self, "sound", None):
                self.sound.enabled = bool(ui_dict["feedback_enabled"])
            LOG.info("[ui live aggiornati] keys=%s", list(ui_dict.keys()))
        except Exception as e:
            LOG.error("apply_ui_live err: %s", e)

    def _apply_tts_live(self, tts_dict: dict) -> None:
        """Aggiornamento live di parametri TTS: volume, enabled,
        length_scale (velocita') e noise_*. Modifiche prendono effetto
        al prossimo `speak()`."""
        if not isinstance(tts_dict, dict):
            return
        cur = self.cfg.get("tts", {}) or {}
        cur.update({k: v for k, v in tts_dict.items() if v is not None})
        self.cfg["tts"] = cur
        tts = getattr(self, "tts", None)
        if tts is None:
            return
        try:
            if "volume" in tts_dict:
                v = float(tts_dict["volume"])
                if v > 2.5:           # backcompat: HA potrebbe inviare 0..100
                    v = v / 100.0
                tts.set_volume(v)
            if "enabled" in tts_dict:
                tts.set_enabled(bool(tts_dict["enabled"]))
            if "length_scale" in tts_dict:
                tts.length_scale = float(tts_dict["length_scale"])
            if "noise_scale" in tts_dict:
                tts.noise_scale = float(tts_dict["noise_scale"])
            if "noise_w" in tts_dict:
                tts.noise_w = float(tts_dict["noise_w"])
            LOG.info("[tts live aggiornati] keys=%s", list(tts_dict.keys()))
        except Exception as e:
            LOG.error("apply_tts_live err: %s", e)

    def _apply_face_recognition_live(self, fr_dict: dict) -> None:
        """Live update di feature face recognition (auto_recognize, liveness).
        `enabled` e' gia' applicato a livello di metodi accesso da
        _apply_access_methods_live."""
        if not isinstance(fr_dict, dict):
            return
        # Auto-recognize: aggiorna lo scanner runtime senza restart.
        ar = fr_dict.get("auto_recognize")
        if isinstance(ar, dict) and getattr(self, "auto_face", None):
            try:
                if "enabled" in ar:
                    self.auto_face.enabled = bool(ar["enabled"])
                    LOG.info("auto_face.enabled = %s",
                             self.auto_face.enabled)
                if "max_seconds" in ar:
                    self.auto_face.max_seconds = float(ar["max_seconds"])
                if "cooldown_sec" in ar:
                    self.auto_face.cooldown_sec = float(ar["cooldown_sec"])
                if "require_liveness" in ar:
                    self.auto_face.require_liveness = bool(ar["require_liveness"])
            except Exception as e:
                LOG.warning("auto_face live err: %s", e)
        # Liveness toggle: lo screen face rilegge cfg ad ogni on_pre_enter,
        # niente da fare qui oltre al merge in self.cfg gia' avvenuto.
        if "liveness_enabled" in fr_dict:
            LOG.info("liveness_enabled (al prossimo accesso face) = %s",
                     fr_dict["liveness_enabled"])

    def _apply_audio_live(self, audio_dict: dict) -> None:
        if not isinstance(audio_dict, dict):
            return
        cur = self.cfg.get("audio", {}) or {}
        cur.update({k: v for k, v in audio_dict.items() if v is not None})
        self.cfg["audio"] = cur
        try:
            import subprocess as _sp
            # Volume casse chiamata: agisce sul sink PulseAudio ec_sink
            # (loopback dell'AEC). Range 0-100%. Persistito su disco da
            # _apply_config_override (si trova in audio.volume_speaker_pct
            # del config.override.yaml).
            if "volume_speaker_pct" in audio_dict:
                v = int(audio_dict["volume_speaker_pct"])
                v = max(0, min(100, v))
                _sp.run(["pactl", "set-sink-volume", "ec_sink", f"{v}%"], check=False)
                LOG.info("pactl set-sink-volume ec_sink %d%%", v)
            # Volume mic chiamata: agisce sul source PulseAudio ec_source.
            # Range 0-200% (140% e' il default ottimale per il MEMS i2s).
            if "volume_mic_pct" in audio_dict:
                v = int(audio_dict["volume_mic_pct"])
                v = max(0, min(200, v))
                _sp.run(["pactl", "set-source-volume", "ec_source", f"{v}%"], check=False)
                LOG.info("pactl set-source-volume ec_source %d%%", v)
            LOG.info("[audio live aggiornati] keys=%s", list(audio_dict.keys()))
        except Exception as e:
            LOG.warning("apply_audio_live err: %s", e)

    def _sync_sfondi_library(self, files: list, base_url: str) -> None:
        """Sync della libreria HA: ri-scarica SEMPRE i file presenti (così
        sostituzioni con stesso nome vengono colte) e cancella gli orfani."""
        if not isinstance(files, list):
            return
        try:
            os.makedirs(self.SFONDI_DIR, exist_ok=True)
        except Exception as e:
            LOG.warning("mkdir sfondi err: %s", e)
            return
        ha_url = (self.cfg.get("home_assistant", {}) or {}).get("base_url", "").rstrip("/")
        if not ha_url:
            LOG.warning("sync sfondi: home_assistant.base_url mancante")
            return
        existing = set()
        try:
            existing = {fn for fn in os.listdir(self.SFONDI_DIR)
                        if not fn.startswith(".")}
        except Exception:
            pass
        # Scarica/aggiorna TUTTI i file della libreria (cache-busting per
        # sostituzioni con stesso filename)
        for fn in files:
            if not fn or fn == "default":
                continue
            self._download_sfondo(ha_url + base_url + fn, fn)
        # Pulisci file orfani (non più presenti nella libreria HA)
        keep = set(files)
        for fn in existing:
            if fn not in keep:
                try:
                    os.remove(os.path.join(self.SFONDI_DIR, fn))
                    LOG.info("sfondo orfano rimosso: %s", fn)
                except Exception as e:
                    LOG.warning("rimozione orfano %s err: %s", fn, e)
        # Se lo sfondo selezionato è stato (ri)scaricato, forza refresh dello
        # screensaver in modo che ricarichi la texture dal disco.
        cur_sfondo = (self.cfg.get("ui", {}) or {}).get("sfondo", "")
        if cur_sfondo and cur_sfondo != "default" and cur_sfondo in keep:
            self._set_sfondo_live(cur_sfondo)

    def _download_sfondo(self, url: str, filename: str) -> str | None:
        """Scarica un file da HA in /opt/videocitofono/app/assets/sfondi/.
        Tenta l'URL fornito e, in caso di errore di connessione, fallback
        automatico http<->https (HA puo' essere solo HTTPS)."""
        import urllib.request, ssl, urllib.error
        os.makedirs(self.SFONDI_DIR, exist_ok=True)
        dst = os.path.join(self.SFONDI_DIR, filename)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        urls = [url]
        if url.startswith("http://"):
            urls.append("https://" + url[len("http://"):])
        elif url.startswith("https://"):
            urls.append("http://" + url[len("https://"):])
        last_err = None
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "videocitofono/1.0"})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                    data = r.read()
                if len(data) > 16 * 1024 * 1024:
                    LOG.warning("download sfondo %s: troppo grande", filename)
                    return None
                with open(dst, "wb") as f:
                    f.write(data)
                LOG.info("sfondo scaricato: %s (%d bytes) <- %s", filename, len(data), u)
                return dst
            except Exception as e:
                last_err = e
                continue
        LOG.warning("download sfondo %s err: %s", filename, last_err)
        return None

    def _sync_icons_from_config(self, refresh_ui: bool = True) -> None:
        """Scarica da HA le icone referenziate in campanelli e access_icons."""
        names: set[str] = set(bundled_icon_filenames())
        for c in self.cfg.get("campanelli", []) or []:
            if isinstance(c, dict):
                fn = (c.get("icona") or "").strip()
                if fn and fn != "default":
                    names.add(os.path.basename(fn))
        for fn in (self.cfg.get("access_icons", {}) or {}).values():
            fn = (fn or "").strip()
            if fn and fn != "default":
                names.add(os.path.basename(fn))
        if not names:
            return
        self._sync_icone_library(sorted(names), "/local/vc-icone/", refresh_ui=refresh_ui)

    def _sync_icone_library(self, files: list, base_url: str,
                            refresh_ui: bool = True) -> None:
        """Analogo di _sync_sfondi_library ma per le icone campanelli.
        Scarica/aggiorna i file in AVATARS_DIR; rimuove gli orfani; al
        termine forza refresh della HomeScreen cosi' i pulsanti
        ricaricano la texture.
        """
        if not isinstance(files, list):
            return
        try:
            os.makedirs(self.AVATARS_DIR, exist_ok=True)
        except Exception as e:
            LOG.warning("mkdir avatars err: %s", e)
            return
        ha_url = (self.cfg.get("home_assistant", {}) or {}).get("base_url", "").rstrip("/")
        if not ha_url:
            LOG.warning("sync icone: home_assistant.base_url mancante")
            return
        existing = set()
        try:
            existing = {fn for fn in os.listdir(self.AVATARS_DIR)
                        if not fn.startswith(".")}
        except Exception:
            pass
        for fn in files:
            if not fn or fn == "default":
                continue
            self._download_icona(ha_url + base_url + fn, fn)
        # Pulisci orfani (preserva default.png e PNG bundled di default).
        keep = set(files) | {"default.png"} | set(bundled_icon_filenames())
        for fn in existing:
            if fn not in keep:
                try:
                    os.remove(os.path.join(self.AVATARS_DIR, fn))
                    LOG.info("icona orfana rimossa: %s", fn)
                except Exception as e:
                    LOG.warning("rimozione orfano icona %s err: %s", fn, e)
        try:
            if refresh_ui:
                Clock.schedule_once(lambda *_: self._refresh_icon_screens(), 0)
        except Exception as e:
            LOG.warning("refresh home post-icone err: %s", e)

    def _download_icona(self, url: str, filename: str) -> str | None:
        """Scarica un file icona da HA in AVATARS_DIR. Stessa logica di
        _download_sfondo (fallback http<->https, ssl no-verify, 16MB max)."""
        import urllib.request, ssl
        os.makedirs(self.AVATARS_DIR, exist_ok=True)
        dst = os.path.join(self.AVATARS_DIR, filename)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        urls = [url]
        if url.startswith("http://"):
            urls.append("https://" + url[len("http://"):])
        elif url.startswith("https://"):
            urls.append("http://" + url[len("https://"):])
        last_err = None
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "videocitofono/1.0"})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                    data = r.read()
                if len(data) > 16 * 1024 * 1024:
                    LOG.warning("download icona %s: troppo grande", filename)
                    return None
                with open(dst, "wb") as f:
                    f.write(data)
                LOG.info("icona scaricata: %s (%d bytes) <- %s", filename, len(data), u)
                return dst
            except Exception as e:
                last_err = e
                continue
        LOG.warning("download icona %s err: %s", filename, last_err)
        return None

    # ----------------------- gestione volti (face) -----------------------

    def _handle_enroll_face(self, payload: dict) -> None:
        """Registra una nuova foto del volto. Payload atteso:
            {"action":"enroll_face", "nome":"Anna", "image_b64":"...",
             "ext":".jpg"}
        """
        nome = (payload.get("nome") or "").strip()
        image_b64 = payload.get("image_b64") or ""
        ext = (payload.get("ext") or ".jpg").lower()
        genere = (payload.get("genere") or "").strip() or None
        if not nome or not image_b64:
            LOG.warning("enroll_face: parametri mancanti (nome=%r len_b64=%d)",
                        nome, len(image_b64))
            self.mqtt.publish_evento("enroll_face_error",
                                     {"error": "parametri mancanti"})
            return
        try:
            import base64
            raw = base64.b64decode(image_b64, validate=True)
        except Exception as e:
            LOG.warning("enroll_face: base64 invalido: %s", e)
            self.mqtt.publish_evento("enroll_face_error",
                                     {"error": "base64 invalido"})
            return
        face = getattr(self, "face", None) or getattr(self.ctx, "face", None)
        if face is None:
            self.mqtt.publish_evento("enroll_face_error",
                                     {"error": "modulo face non disponibile"})
            return
        try:
            res = face.enroll_image(nome, raw, ext, genere=genere)
        except Exception as e:
            LOG.error("enroll_image err: %s", e)
            self.mqtt.publish_evento("enroll_face_error", {"error": str(e)})
            return
        LOG.info("enroll_face %s -> %s", nome, res)
        self.mqtt.publish_evento("enroll_face_done", {"nome": nome, "result": res})
        self._publish_volti_library()

    def _handle_delete_face(self, payload: dict) -> None:
        """Elimina tutte le foto di una persona. Payload: {"nome": "Anna"}."""
        nome = (payload.get("nome") or "").strip()
        if not nome:
            return
        face = getattr(self, "face", None) or getattr(self.ctx, "face", None)
        if face is None:
            return
        try:
            res = face.delete_user(nome)
        except Exception as e:
            LOG.error("delete_user err: %s", e)
            return
        LOG.info("delete_face %s -> %s", nome, res)
        # Rimuove anche eventuale PIN associato all'utente (record non-admin
        # in users.json) cosi' eliminando un volto se ne cancella ogni
        # forma di accesso (volto + PIN abbinato).
        try:
            sanitized = face._sanitize_name(nome)
            if self.pin_manager.clear_user_pin(sanitized):
                LOG.info("delete_face: rimosso anche PIN utente %s", sanitized)
        except Exception as e:
            LOG.warning("clear_user_pin err: %s", e)
        self.mqtt.publish_evento("delete_face_done", {"nome": nome, "result": res})
        self._publish_volti_library()

    def _handle_rename_face(self, payload: dict) -> None:
        """Rinomina una persona registrata. Payload:
            {"nome": "Anna", "nuovo_nome": "Anna_Rossi"}
        """
        old = (payload.get("nome") or "").strip()
        new = (payload.get("nuovo_nome") or "").strip()
        if not old or not new:
            return
        face = getattr(self, "face", None) or getattr(self.ctx, "face", None)
        if face is None:
            return
        try:
            res = face.rename_user(old, new)
        except Exception as e:
            LOG.error("rename_user err: %s", e)
            return
        LOG.info("rename_face %s -> %s", old, res)
        # Propaga il rename anche al record PIN se esiste.
        if isinstance(res, dict) and res.get("ok"):
            try:
                old_safe = face._sanitize_name(old)
                new_safe = face._sanitize_name(new)
                if old_safe != new_safe and self.pin_manager.has_user(old_safe):
                    if self.pin_manager.update_user_meta(
                            old_safe, nuovo_nome=new_safe):
                        LOG.info("rename_face: rinominato anche record PIN %s -> %s",
                                 old_safe, new_safe)
            except Exception as e:
                LOG.warning("rename PIN propagation err: %s", e)
        self.mqtt.publish_evento("rename_face_done",
                                 {"nome": old, "nuovo_nome": new, "result": res})
        self._publish_volti_library()

    def _handle_update_face(self, payload: dict) -> None:
        """Aggiorna i metadati di una persona registrata. Payload:
            {"nome": "Anna", "genere": "F"}
        """
        nome = (payload.get("nome") or "").strip()
        genere = (payload.get("genere") or "").strip()
        if not nome:
            return
        face = getattr(self, "face", None) or getattr(self.ctx, "face", None)
        if face is None:
            return
        try:
            res = face.update_user(nome, genere=genere)
        except Exception as e:
            LOG.error("update_user err: %s", e)
            return
        LOG.info("update_face %s -> %s", nome, res)
        # Propaga eventualmente il genere anche al record PIN.
        try:
            sanitized = face._sanitize_name(nome)
            if self.pin_manager.has_user(sanitized):
                self.pin_manager.update_user_meta(sanitized, genere=genere)
        except Exception as e:
            LOG.warning("update genere PIN propagation err: %s", e)
        self.mqtt.publish_evento("update_face_done", {"nome": nome, "result": res})
        self._publish_volti_library()

    def _handle_set_face_pin(self, payload: dict) -> None:
        """Imposta o rimuove il PIN associato a un utente registrato per
        il riconoscimento facciale. Payload:
            {"nome": "Stefania", "pin": "1234"}    -> set/update
            {"nome": "Stefania", "pin": ""}         -> clear
        Genere e apre vengono ereditati dal meta.json del volto se
        presenti; se l'utente PIN non esiste viene creato.
        """
        nome = (payload.get("nome") or "").strip()
        pin = str(payload.get("pin") or "").strip()
        if not nome:
            return
        face = getattr(self, "face", None) or getattr(self.ctx, "face", None)
        if face is None:
            return
        sanitized = face._sanitize_name(nome)
        # Cartella volto deve esistere (no PIN orfani).
        face_dir = os.path.join(face.storage_dir, sanitized)
        if not os.path.isdir(face_dir):
            self.mqtt.publish_evento("set_face_pin_error",
                                     {"error": "volto non trovato",
                                      "nome": sanitized})
            return
        meta = face.get_user_meta(sanitized)
        genere = meta.get("genere") or None
        if not pin:
            # Clear
            removed = self.pin_manager.clear_user_pin(sanitized)
            try:
                face.update_user(sanitized, pin_set=False)
            except Exception:
                pass
            LOG.info("set_face_pin clear %s removed=%s", sanitized, removed)
            self.mqtt.publish_evento("set_face_pin_done",
                                     {"nome": sanitized, "pin_set": False})
        else:
            res = self.pin_manager.set_user_pin(
                sanitized, pin, genere=genere, apre="porta")
            if not res.get("ok"):
                self.mqtt.publish_evento("set_face_pin_error",
                                         {"error": res.get("msg"),
                                          "nome": sanitized})
                return
            try:
                face.update_user(sanitized, pin_set=True)
            except Exception:
                pass
            LOG.info("set_face_pin %s -> %s", sanitized, res)
            self.mqtt.publish_evento("set_face_pin_done",
                                     {"nome": sanitized, "pin_set": True})
        self._publish_volti_library()

    # ------------------- Guest PIN handlers -----------------------------
    def _handle_guest_pin_create(self, payload: dict) -> None:
        gp = getattr(self, "guest_pins", None)
        if gp is None:
            self.mqtt.publish_evento("guest_pin_error",
                                     {"error": "guest_pins disabled"})
            return
        try:
            label = str(payload.get("label", ""))
            valid_h = float(payload.get("valid_hours", 24))
            max_u = int(payload.get("max_uses", 1))
            scope = str(payload.get("scope", "porta"))
            rid, pin = gp.create(label=label, valid_hours=valid_h,
                                 max_uses=max_u, scope=scope)
            import time as _t
            exp_h = _t.strftime("%Y-%m-%d %H:%M",
                                _t.localtime(_t.time() + valid_h * 3600))
            self.mqtt.publish(
                "videocitofono/guest_pins/created",
                json.dumps({"id": rid, "pin": pin, "label": label,
                            "scope": scope, "max_uses": max_u,
                            "expires_human": exp_h}),
                retain=False,
            )
            self._publish_guest_pin_list()
            try:
                self.ctx.record_event("guest_created", method="guest",
                                      user="ospite",
                                      meta={"id": rid, "label": label,
                                            "valid_hours": valid_h,
                                            "max_uses": max_u})
            except Exception:
                pass
        except Exception as e:
            LOG.error("guest_pin_create err: %s", e)
            self.mqtt.publish_evento("guest_pin_error", {"error": str(e)})

    def _handle_guest_pin_revoke(self, payload: dict) -> None:
        gp = getattr(self, "guest_pins", None)
        if gp is None:
            return
        rid = str(payload.get("id", ""))
        ok = gp.revoke(rid)
        self._publish_guest_pin_list()
        try:
            self.ctx.record_event("guest_revoked", method="guest",
                                  meta={"id": rid, "ok": ok})
        except Exception:
            pass

    def _publish_guest_pin_list(self) -> None:
        gp = getattr(self, "guest_pins", None)
        if gp is None:
            return
        try:
            items = gp.list(include_inactive=True)
            self.mqtt.publish(
                "videocitofono/guest_pins/list",
                json.dumps({"items": items}),
                retain=True,
            )
        except Exception as e:
            LOG.warning("publish guest_pin_list err: %s", e)

    def _publish_volti_library(self) -> None:
        """Pubblica con retain la lista volti registrati su
        videocitofono/volti/library cosi' HA ne ha sempre lo stato."""
        face = getattr(self, "face", None) or getattr(self.ctx, "face", None)
        if face is None:
            return
        try:
            import json
            users = face.list_users()
            payload = json.dumps({"volti": users})
            # Pub con retain = HA li puo' leggere a freddo
            self.mqtt._client.publish("videocitofono/volti/library", payload,
                                      qos=1, retain=True)
            LOG.info("volti library pubblicata: %d persone", len(users))
        except Exception as e:
            LOG.warning("publish volti library err: %s", e)

    def _publish_auto_faces_list(self, nome: str) -> None:
        face = getattr(self, "face", None) or getattr(self.ctx, "face", None)
        if face is None or not nome:
            return
        try:
            samples = face.list_auto_samples(nome) if hasattr(face, "list_auto_samples") else []
            payload = json.dumps({"nome": nome, "samples": samples})
            self.mqtt.publish("videocitofono/volti/auto_list", payload, retain=False)
        except Exception as e:
            LOG.warning("publish auto_faces list err: %s", e)

    def _handle_delete_auto_face(self, payload: dict) -> None:
        nome = (payload.get("nome") or "").strip()
        filename = (payload.get("filename") or payload.get("file") or "").strip()
        face = getattr(self, "face", None)
        if not nome or not filename or face is None:
            return
        ok = False
        if hasattr(face, "delete_auto_sample"):
            ok = face.delete_auto_sample(nome, filename)
        self.mqtt.publish_evento(
            "auto_face_deleted" if ok else "auto_face_delete_error",
            {"nome": nome, "filename": filename})
        if ok:
            self._publish_volti_library()
            self._publish_auto_faces_list(nome)

    def _handle_purge_auto_faces(self, payload: dict) -> None:
        nome = (payload.get("nome") or "").strip()
        face = getattr(self, "face", None)
        if not nome or face is None:
            return
        n = 0
        if hasattr(face, "purge_auto_samples"):
            n = face.purge_auto_samples(nome)
        self.mqtt.publish_evento("auto_faces_purged", {"nome": nome, "removed": n})
        self._publish_volti_library()
        self._publish_auto_faces_list(nome)

    def _on_nfc_tag(self, uid: str) -> None:
        """Callback quando NfcReader rileva un tag (main thread Kivy).
        - Se la screen attiva e' 'nfc' delega a quella schermata.
        - Altrimenti matcha contro NfcLibrary e apre porta/cancello.
        - Pubblica evento MQTT sempre."""
        try:
            self.mqtt.publish_evento("nfc_tag", {"uid": uid})
            audit(LOG, "nfc_tag", uid=uid, screen=self.sm.current)
        except Exception:
            pass
        try:
            if self.sm.current == "nfc":
                sc = self.sm.get_screen("nfc")
                handler = getattr(sc, "on_nfc_tag", None)
                if callable(handler):
                    handler(uid)
                    return
        except Exception:
            pass
        if not self.nfc_lib:
            return
        rec = self.nfc_lib.find_by_uid(uid)
        if not rec:
            LOG.info("NFC tag %s sconosciuto", uid)
            try:
                if self.sm.current in ("home", "screensaver", "nfc"):
                    if self.sm.current != "nfc":
                        self.sm.current = "nfc"
                    sc = self.sm.get_screen("nfc")
                    h = getattr(sc, "show_unknown_tag", None)
                    if callable(h):
                        h(uid)
            except Exception:
                pass
            return
        scope = rec.get("scope", "porta")
        nome = rec.get("nome", "")
        rest_ok = False
        try:
            rest_ok = (self.ha.apri_porta() if scope == "porta"
                       else self.ha.apri_cancello())
        except Exception as e:
            LOG.warning("nfc REST err: %s", e)
        try:
            self.mqtt.publish_apertura(metodo="nfc", utente=nome,
                                       scope=scope)
        except Exception:
            pass
        try:
            self.ctx.record_open(method="nfc", user=nome, scope=scope,
                                 success=True,
                                 label=rec.get("label", ""))
        except Exception:
            pass
        LOG.info("NFC apri scope=%s rest_ok=%s utente=%s uid=%s",
                 scope, rest_ok, nome, uid)
        try:
            af = getattr(self, "auto_face", None)
            if af is not None:
                af._show_result(nome, scope, "")
        except Exception as e:
            LOG.debug("nfc ui feedback err: %s", e)

    def _handle_nfc_enroll(self, payload: dict) -> None:
        """Iscrive il prossimo tag rilevato all'utente indicato.
        Payload: nome (req), scope, label, timeout_sec."""
        nome = (payload.get("nome") or "").strip()
        if not nome:
            self.mqtt.publish_evento("nfc_enroll_error",
                                     {"error": "nome mancante"})
            return
        if self.nfc_reader is None or self.nfc_lib is None:
            self.mqtt.publish_evento("nfc_enroll_error",
                                     {"error": "NFC non disponibile"})
            return
        scope = payload.get("scope") or "porta"
        label = payload.get("label") or ""
        timeout_sec = float(payload.get("timeout_sec", 30.0))

        def _worker():
            self.mqtt.publish_evento(
                "nfc_enroll_started",
                {"nome": nome, "timeout_sec": timeout_sec})
            uid = self.nfc_reader.enroll_next(timeout_sec=timeout_sec)
            if not uid:
                err = (self.nfc_reader.last_error()
                       or "timeout: nessun tag rilevato")
                self.mqtt.publish_evento("nfc_enroll_error",
                                         {"error": err, "nome": nome})
                return
            ok = self.nfc_lib.add(uid, nome, scope, label)
            self.mqtt.publish_evento(
                "nfc_enroll_done",
                {"nome": nome, "uid": uid, "ok": ok, "label": label})
            self._publish_nfc_library()

        threading.Thread(target=_worker, daemon=True,
                         name="nfc-enroll").start()

    def _handle_nfc_delete(self, payload: dict) -> None:
        """Cancella un tag (per uid) o tutti i tag di un utente."""
        if self.nfc_lib is None:
            return
        uid = (payload.get("uid") or "").strip().lower()
        nome = (payload.get("nome") or "").strip()
        n = 0
        if uid:
            if self.nfc_lib.remove(uid):
                n = 1
        elif nome:
            n = self.nfc_lib.remove_user(nome)
        self.mqtt.publish_evento("nfc_delete_done",
                                 {"uid": uid, "nome": nome,
                                  "removed": n})
        self._publish_nfc_library()

    def _publish_nfc_status(self) -> None:
        """Stato lettore su videocitofono/nfc/status (retain)."""
        if self.mqtt is None or getattr(self.mqtt, "_client", None) is None:
            return
        try:
            import json
            if self.nfc_reader is None:
                payload = {"state": "disabled"}
            elif self.nfc_reader.is_reader_ready():
                payload = {
                    "state": "ready",
                    "device": self.nfc_reader.device,
                }
            else:
                payload = {
                    "state": "offline",
                    "device": self.nfc_reader.device,
                    "probe_ok": self.nfc_reader.probe_ok(),
                    "error": self.nfc_reader.last_error(),
                }
            self.mqtt._client.publish(
                "videocitofono/nfc/status",
                json.dumps(payload), qos=1, retain=True)
        except Exception as e:
            LOG.debug("publish nfc status err: %s", e)

    def _publish_nfc_library(self) -> None:
        """Pubblica retain la lista tag NFC su
        videocitofono/nfc/library."""
        if self.nfc_lib is None:
            return
        try:
            import json
            tags = self.nfc_lib.list_tags()
            items = [
                {"uid": uid, "nome": rec.get("nome", ""),
                 "scope": rec.get("scope", "porta"),
                 "label": rec.get("label", ""),
                 "added_ts": rec.get("added_ts", 0)}
                for uid, rec in tags.items()
            ]
            payload = json.dumps({"items": items})
            self.mqtt._client.publish("videocitofono/nfc/library",
                                      payload, qos=1, retain=True)
            LOG.info("nfc library pubblicata: %d tag", len(items))
        except Exception as e:
            LOG.warning("publish nfc library err: %s", e)

    def _set_sfondo_live(self, name: str) -> None:
        """Applica live lo sfondo selezionato sullo screensaver."""
        path = ""
        if name and name != "default":
            local = os.path.join(self.SFONDI_DIR, name)
            if not os.path.exists(local):
                ha_url = (self.cfg.get("home_assistant", {}) or {}).get("base_url", "").rstrip("/")
                if ha_url:
                    self._download_sfondo(ha_url + "/local/vc-sfondi/" + name, name)
            if os.path.exists(local):
                path = local
        if self.sm.has_screen("screensaver"):
            sc = self.sm.get_screen("screensaver")
            def _apply(*_):
                # Se il path coincide, on_bg_source non scatta da solo:
                # forziamo riapplicazione esplicita.
                if sc.bg_source == path:
                    sc._apply_bg_to_image()
                else:
                    sc.bg_source = path
            Clock.schedule_once(_apply, 0)
        # Propaga lo sfondo a TUTTE le altre schermate (Home, Calling, Pin,
        # Face, Finger, Nfc, Result) per uno stile coerente.
        for sname in ("home", "calling", "pin", "face", "finger", "nfc", "result"):
            if self.sm.has_screen(sname):
                scr = self.sm.get_screen(sname)
                def _apply_screen(*_, _scr=scr):
                    if _scr.bg_source == path:
                        _scr.on_bg_source()
                    else:
                        _scr.bg_source = path
                Clock.schedule_once(_apply_screen, 0)
        LOG.info("sfondo live: %s -> %r", name, path)

    def _check_idle(self, *_):
        # Sospendi idle dim + screensaver durante l'intero ciclo chiamata
        # (calling = "sta squillando/in attesa di risposta", conversation
        # = "rispondente in video"). Forza luminosita' piena e reset
        # last_activity cosi' al ritorno a home il timer parte da zero.
        if self.sm.current in ("calling", "conversation"):
            self.brightness.active()
            self.last_activity = Clock.get_time()
            return
        idle = Clock.get_time() - self.last_activity
        # 1) Dimming progressivo
        if self._idle_dim_sec > 0 and idle >= self._idle_dim_sec:
            if not self.brightness.is_off:
                self.brightness.idle()
        # 2) Screensaver
        if (
            self._screensaver_timeout > 0
            and idle >= self._screensaver_timeout
            and self.sm.current != "screensaver"
        ):
            LOG.info("Screensaver dopo %ds idle", int(idle))
            self.sm.current = "screensaver"
        # 3) Spegnimento HDMI: OLED a zero, niente burn-in da indirizzo fisso
        if (
            self._display_off_sec > 0
            and idle >= self._display_off_sec
            and not self.brightness.is_off
        ):
            LOG.info("Display off dopo %ds idle", int(idle))
            self.brightness.off()
        try:
            self._sync_motion_state()
        except Exception as e:
            LOG.debug("sync motion idle err: %s", e)
        # Watchdog go2rtc per motion snapshot (solo se source=snapshot).
        try:
            if self._go2rtc_for_motion() and self.sm.current in ("home", "screensaver"):
                mcfg = (self.cfg.get("motion") or {})
                if mcfg.get("enabled", True) and mcfg.get("source") == "snapshot":
                    from modules.go2rtc_control import (
                        ensure_running_for_motion, is_paused,
                        recover_stale_pause,
                    )
                    auto_face = getattr(self, "auto_face", None)
                    af_busy = bool(
                        auto_face and auto_face.is_running())
                    # Anche l'anteprima on-demand tiene libcamera: senza questo
                    # il watchdog rimetterebbe in piedi rpicam-vid e i due si
                    # contenderebbero il sensore.
                    lk_busy = (
                        getattr(self.ctx, "lk_session", None) is not None
                        or getattr(self.ctx, "lk_preview", None) is not None
                    )
                    cam_busy = af_busy or lk_busy
                    now = time.time()
                    last = getattr(self, "_go2rtc_watch_t", 0.0)
                    if now - last >= 20.0:
                        self._go2rtc_watch_t = now
                        if is_paused():
                            recover_stale_pause(
                                idle_screen=True,
                                camera_consumer_active=cam_busy)
                        elif not is_paused() and not cam_busy:
                            ensure_running_for_motion()
        except Exception as e:
            LOG.debug("go2rtc watchdog err: %s", e)

    def on_stop(self):
        try:
            if getattr(self, "webrtc_audio", None):
                self.webrtc_audio.stop()
        except Exception:
            pass
        try:
            if self.talkback:
                self.talkback.stop()
        except Exception:
            pass
        try:
            if self.button:
                self.button.close()
        except Exception:
            pass
        try:
            self.mqtt.publish_evento("shutdown")
            self.mqtt.stop()
        except Exception:
            pass
        try:
            if self.motion and hasattr(self.motion, "stop"):
                self.motion.stop()
        except Exception:
            pass
        try:
            self._stop_nfc()
        except Exception:
            pass
        try:
            if self.camera:
                self.camera.stop()
        except Exception:
            pass
        try:
            self.brightness.idle()
        except Exception:
            pass


if __name__ == "__main__":
    VideocitofonoApp().run()
