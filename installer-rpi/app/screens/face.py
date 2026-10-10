"""Schermata Riconoscimento Facciale.

Funzionalita':
- Apre dedicata picamera2 a 640x480@10fps SOLO mentre lo schermo e' attivo
  (al cambio screen la camera viene rilasciata cosi' LiveKit/motion possono
  riusarla senza conflitti).
- Mostra il preview della camera sotto un overlay AR: sagoma ovale per
  centrare il volto + linea di scansione orizzontale animata + 4 corner
  brackets stile fotocamera AR.
- Esegue il riconoscimento via FaceRecognizer (modulo
  face_recognition + dlib) in un thread di background a ~3 Hz, cosi' il
  rendering UI resta fluido.
- Al raggiungimento di N frame consecutivi della stessa persona apre la
  porta e mostra la schermata 'Porta aperta' con saluto personalizzato.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import math

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line
from kivy.graphics.texture import Texture
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.widget import Widget

from .bg_screen import BgScreen
from modules.greetings import build_greeting

LOG = logging.getLogger(__name__)

_PREVIEW_W = 640
_PREVIEW_H = 480
_PREVIEW_FPS = 10.0
_SCAN_HZ = 5.0  # frequenza tentativi recognition (CPU-bound)


class FaceMeshOverlay(Widget):
    """Overlay scansione minimal:
    - Ovale con contorno bianco (sagoma guida)
    - Linea orizzontale arancione che scorre lentamente top->bottom
      simulando la scansione. La linea e' lunga quanto la corda
      orizzontale dell'ovale a quella altezza, cosi' resta visivamente
      contenuta dentro la sagoma.
    L'animazione e' pilotata da `phase` (0..1, ~3.5s loop top->down).
    """

    phase = NumericProperty(0.0)  # 0 = top, 1 = bottom
    sweep = NumericProperty(0.0)  # legacy, non usato
    scanning = BooleanProperty(False)
    face_detected = BooleanProperty(False)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw,
                  phase=self._redraw,
                  scanning=self._redraw, face_detected=self._redraw)

    def _redraw(self, *_):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return
        cx, cy = self.center_x, self.center_y
        # Footprint ovale: 64% W x 64% H, centrato.
        ow, oh = self.width * 0.64, self.height * 0.64
        ox, oy = cx - ow / 2.0, cy - oh / 2.0
        a = ow / 2.0
        b = oh / 2.0

        with self.canvas:
            # Sagoma ovale: bianco se in scansione/idle, verde se rilevato
            if self.face_detected:
                Color(0.20, 0.95, 0.65, 0.95)
            else:
                Color(1.0, 1.0, 1.0, 0.85)
            Line(ellipse=(ox, oy, ow, oh), width=2.6)

            # Linea di scansione arancione (mostrata solo durante scan
            # attivo, nascosta quando il volto e' stato riconosciuto).
            if self.scanning and not self.face_detected:
                # phase 0 = top dell'ovale, 1 = bottom dell'ovale.
                yp = oy + oh * (1.0 - self.phase)
                # Larghezza della corda orizzontale dell'ellisse a quota yp:
                # x = a * sqrt(1 - ((yp - cy) / b)^2)
                t = (yp - cy) / b
                if -1.0 <= t <= 1.0:
                    half = a * math.sqrt(max(0.0, 1.0 - t * t))
                else:
                    half = 0.0
                # Riduco di 4px per non sovrapporsi al contorno.
                half = max(0.0, half - 4.0)
                if half > 1.0:
                    x1, x2 = cx - half, cx + half
                    # Glow morbido sotto la linea principale
                    Color(1.0, 0.55, 0.10, 0.18)
                    Line(points=[x1, yp, x2, yp], width=8.0)
                    # Linea principale arancione
                    Color(1.0, 0.55, 0.10, 0.95)
                    Line(points=[x1, yp, x2, yp], width=2.2)


class FaceScreen(BgScreen):
    stato = StringProperty("Inquadra il volto")
    # phase: 0..1 ciclico, ~1.6s. Pilota l'espansione degli anelli concentrici.
    phase = NumericProperty(0.0)
    # sweep: 0..1 ciclico, ~2.0s. Pilota la rotazione 360 della linea radar.
    sweep = NumericProperty(0.0)
    scanning = BooleanProperty(False)
    face_detected = BooleanProperty(False)
    # True quando il primo frame live e' stato blittato: prima di allora
    # mostriamo la cover "Avvio riconoscimento facciale" e teniamo nascosto
    # il preview (che altrimenti mostrerebbe il frame della sessione prec.).
    cam_ready = BooleanProperty(False)

    def __init__(self, app_ctx, bg_source: str | None = None, **kw):
        super().__init__(bg_source=bg_source, **kw)
        self.app_ctx = app_ctx
        self._t0 = 0.0
        self._matches = 0
        self._last_match_name: Optional[str] = None
        self._preview_ev = None
        self._scan_ev = None
        self._timeout_ev = None
        self._phase_anim: Optional[Animation] = None
        self._sweep_anim: Optional[Animation] = None
        # Camera capture in thread proprio (snapshot piu' recente esposto)
        self._cap_thread: Optional[threading.Thread] = None
        self._cap_stop: Optional[threading.Event] = None
        self._cap_lock = threading.Lock()
        self._latest_frame = None  # numpy BGR
        self._submitting = False
        # Multi-frame voting: deque degli ultimi N risultati (nome | None).
        from collections import deque
        cfg = (self.app_ctx.config.get("face_recognition", {}) or {})
        self._vote_window = int(cfg.get("vote_window", 5))
        self._vote_required = int(cfg.get("vote_required", 3))
        self._vote_min_lead = int(cfg.get("vote_min_lead", 2))
        self._votes = deque(maxlen=max(1, self._vote_window))
        self._last_match: Optional[dict] = None
        self._borderline_logged = False
        # Anti-spoofing (blink detection EAR). Se dlib o predictor mancano
        # e liveness e' richiesto, il match viene rifiutato in face.py.
        self._liveness = None
        self._liveness_required = bool(cfg.get("liveness_enabled", True))
        self._min_blinks = int(cfg.get("liveness_min_blinks", 1))
        self._init_liveness_checker(cfg)
        self._consec_unknown = 0  # frame consecutivi con volto ma non riconosciuto
        self._cam_ready_ev = None
        self._preview_tex = None
        self._startup_pulse_anim: Optional[Animation] = None

    def _init_liveness_checker(self, cfg: dict | None = None) -> None:
        cfg = cfg or (self.app_ctx.config.get("face_recognition", {}) or {})
        if not self._liveness_required:
            self._liveness = None
            return
        try:
            from modules.liveness import LivenessChecker
            self._liveness = LivenessChecker(
                ear_threshold=float(cfg.get("liveness_ear", 0.18)),
                consec_frames=int(cfg.get("liveness_consec", 1)),
                min_blinks=self._min_blinks,
            )
        except Exception as _e:
            LOG.debug("liveness init err: %s", _e)
            self._liveness = None

    # --------------------------- lifecycle ---------------------------------

    def on_pre_enter(self, *_):
        # Messaggio iniziale: mostrato nella cover sopra l'area video finche'
        # non arriva il primo frame live (vedi _on_camera_ready).
        self.stato = "Avvio riconoscimento facciale"
        self.cam_ready = False
        self.scanning = True
        self.face_detected = False
        self._prepare_startup_overlay()
        self._t0 = time.time()
        self._matches = 0
        self._last_match_name = None
        self._submitting = False
        self._latest_frame = None
        self._votes.clear()
        self._last_match = None
        self._consec_unknown = 0
        self._borderline_logged = False
        # Rileggo cfg live per supportare toggle liveness/voting da HA
        cfg = (self.app_ctx.config.get("face_recognition", {}) or {})
        try:
            self._liveness_required = bool(cfg.get("liveness_enabled", True))
            self._min_blinks = int(cfg.get("liveness_min_blinks", 1))
            self._vote_required = int(cfg.get("vote_required", 3))
            self._vote_min_lead = int(cfg.get("vote_min_lead", 2))
        except Exception:
            pass
        self._init_liveness_checker(cfg)
        if self._liveness is not None:
            try:
                self._liveness.reset()
            except Exception:
                pass
        # Prep camera in thread (non bloccare UI: motion.stop/go2rtc erano ~2-3s).
        if self._cam_ready_ev:
            self._cam_ready_ev.cancel()
            self._cam_ready_ev = None
        self._start_camera()
        self._start_scan_animation()
        # UI texture refresh @ 30Hz (light)
        self._preview_ev = Clock.schedule_interval(self._refresh_preview, 1 / 30.0)
        # Recognition tick @ _SCAN_HZ (CPU-heavy: HOG + encoding)
        self._scan_ev = Clock.schedule_interval(self._scan_tick, 1 / _SCAN_HZ)
        # Timeout assoluto (bloc se nessun match)
        cfg = self.app_ctx.config.get("face_recognition", {}) or {}
        timeout = float(cfg.get("timeout_sec", 18))
        self._timeout_ev = Clock.schedule_once(self._on_timeout, timeout)

    def _prepare_camera_for_face(self) -> None:
        """Libera libcamera da motion/go2rtc senza release() (switch veloce)."""
        try:
            mot = getattr(self.app_ctx, "motion", None)
            if mot is not None and hasattr(mot, "stop"):
                mot.stop(join_timeout=0.2)
        except Exception as e:
            LOG.warning("face: motion.stop err: %s", e)
        try:
            from modules.go2rtc_control import pause_for_camera
            pause_for_camera("face")
        except Exception as e:
            LOG.warning("face: pause go2rtc err: %s", e)

    def on_leave(self, *_):
        if self._cam_ready_ev:
            self._cam_ready_ev.cancel()
            self._cam_ready_ev = None
        self._stop_startup_pulse()
        self.cam_ready = False
        self._stop_scan_animation()
        if self._preview_ev:
            self._preview_ev.cancel()
            self._preview_ev = None
        if self._scan_ev:
            self._scan_ev.cancel()
            self._scan_ev = None
        if self._timeout_ev:
            self._timeout_ev.cancel()
            self._timeout_ev = None
        self._preview_tex = None
        self._stop_camera()
        # Ripristina go2rtc per motion snapshot (se configurato).
        try:
            from modules.go2rtc_control import resume_after_camera
            Clock.schedule_once(lambda *_: resume_after_camera("face"), 1.0)
        except Exception as e:
            LOG.warning("face: resume go2rtc err: %s", e)

    # --------------------------- camera (thread) ---------------------------

    def _start_camera(self) -> None:
        if self._cap_thread and self._cap_thread.is_alive():
            return
        self._cap_stop = threading.Event()
        self._cap_thread = threading.Thread(target=self._capture_loop, name="face-cap", daemon=True)
        self._cap_thread.start()

    def _stop_camera(self) -> None:
        if self._cap_stop:
            self._cap_stop.set()
        t = self._cap_thread
        if t and t.is_alive():
            try:
                t.join(timeout=2.0)
            except Exception:
                pass
        self._cap_thread = None
        with self._cap_lock:
            self._latest_frame = None

    def _capture_loop(self) -> None:
        """Loop di cattura: usa il singleton PicamSession in modo 'face'
        (640x480 RGB888 @ 10fps). Il singleton e' gia' aperto in modo
        'motion' ed esegue solo uno switch_mode (stop/configure/start
        sulla stessa istanza Picamera2): zero close/reopen, zero rischio
        di libcamera stuck.
        """
        try:
            from modules.camera_session import PicamSession
            import numpy as np  # noqa: F401
        except Exception as e:
            LOG.warning("camera_session/numpy non disponibili: %s", e)
            return
        sess = PicamSession.instance()
        if not sess.is_available():
            Clock.schedule_once(lambda *_: setattr(self, "stato", "Camera non disponibile"), 0)
            return
        self._prepare_camera_for_face()
        acquired = False
        for attempt in range(6):
            if sess.acquire("face"):
                acquired = True
                break
            LOG.warning("FaceScreen: acquire(face) tentativo %d/6 FAIL",
                        attempt + 1)
            if self._cap_stop and self._cap_stop.is_set():
                return
            time.sleep(0.15)
        if not acquired:
            LOG.error("FaceScreen: PicamSession.acquire(face) FAIL definitivo")
            Clock.schedule_once(lambda *_: setattr(self, "stato", "Camera non disponibile"), 0)
            return
        period = 1.0 / max(1.0, _PREVIEW_FPS)
        # Warmup: dopo lo switch di modalita' (motion->face) la picamera2
        # puo' restituire alcuni frame ancora "vecchi", rimasti nei buffer
        # della sessione motion precedente. Li scartiamo: cosi' il PRIMO
        # frame esposto alla UI (che fa scattare il reveal della cover via
        # _on_camera_ready) e' realmente fresco, e l'utente non rivede il
        # frame stale. ~0.7s di frame scartati = anche durata minima
        # percepibile della cover "Avvio riconoscimento facciale".
        warmup_left = max(3, int(_PREVIEW_FPS * 0.7))
        try:
            while self._cap_stop and not self._cap_stop.is_set():
                t0 = time.time()
                arr = sess.capture("face")
                # Picamera2 con format="RGB888" restituisce un ndarray
                # uint8 shape (H, W, 3) effettivamente in ordine BGR
                # (cfr. doc Picamera2: "RGB888 array returned in BGR
                # order"). Quindi il frame e' GIA' BGR.
                if arr is not None:
                    if warmup_left > 0:
                        warmup_left -= 1
                    else:
                        with self._cap_lock:
                            self._latest_frame = arr.copy()
                wait = max(0.0, period - (time.time() - t0))
                if wait:
                    self._cap_stop.wait(wait)
        finally:
            # Non rilascio il session: il switch verso "motion" lo fara'
            # MotionPicameraDetector.start() su screen home.
            pass

    # --------------------------- preview UI --------------------------------

    def _prepare_startup_overlay(self) -> None:
        """Stato iniziale dei layer della card video: cover visibile, preview
        e overlay AR nascosti, texture stale azzerata. Evita che compaia il
        frame "vecchio" della sessione precedente prima del primo frame live.
        """
        prev = self.ids.get("cam_preview")
        if prev is not None:
            # Nasconde il widget preview: la texture della sessione precedente
            # resta assegnata ma invisibile (opacity 0) e verra' sostituita
            # dalla nuova texture al primo frame live. Il reveal (_on_camera_
            # ready) avviene SOLO dopo il blit del frame nuovo, quindi non
            # c'e' rischio di mostrare il frame "vecchio". Non azzeriamo
            # prev.texture per non forzare il reload del placeholder.
            prev.opacity = 0.0
        ov = self.ids.get("face_overlay")
        if ov is not None:
            ov.opacity = 0.0
        startup = self.ids.get("cam_startup")
        if startup is not None:
            startup.opacity = 1.0
        status = self.ids.get("status_face")
        if status is not None:
            # Durante l'avvio il messaggio e' nella cover sopra il video:
            # nascondo il sottotitolo header per non duplicarlo.
            status.opacity = 0.0
        self._start_startup_pulse()

    def _start_startup_pulse(self) -> None:
        self._stop_startup_pulse()
        lbl = self.ids.get("cam_startup_lbl")
        if lbl is None:
            return
        lbl.opacity = 1.0
        anim = (
            Animation(opacity=0.5, duration=0.7, t="in_out_sine")
            + Animation(opacity=1.0, duration=0.7, t="in_out_sine")
        )
        anim.repeat = True
        self._startup_pulse_anim = anim
        anim.start(lbl)

    def _stop_startup_pulse(self) -> None:
        a = self._startup_pulse_anim
        if a is not None:
            try:
                a.cancel(self.ids.get("cam_startup_lbl"))
            except Exception:
                pass
        self._startup_pulse_anim = None

    def _on_camera_ready(self) -> None:
        """Primo frame live disponibile: transizione fluida dalla cover di
        avvio al video live (fade incrociato di cover/preview/overlay)."""
        if self.cam_ready:
            return
        self.cam_ready = True
        self._stop_startup_pulse()
        self.stato = "Inquadra il volto"
        prev = self.ids.get("cam_preview")
        ov = self.ids.get("face_overlay")
        startup = self.ids.get("cam_startup")
        status = self.ids.get("status_face")
        if startup is not None:
            Animation(opacity=0.0, duration=0.32, t="out_quad").start(startup)
        if prev is not None:
            Animation(opacity=1.0, duration=0.32, t="out_quad").start(prev)
        if ov is not None:
            Animation(opacity=1.0, duration=0.42, t="out_quad").start(ov)
        if status is not None:
            Animation(opacity=1.0, duration=0.32, t="out_quad").start(status)

    def _refresh_preview(self, *_):
        with self._cap_lock:
            frame = self._latest_frame
        if frame is None:
            return
        try:
            h, w = frame.shape[:2]
            tex = self._preview_tex
            if tex is None or tex.size[0] != w or tex.size[1] != h:
                tex = Texture.create(size=(w, h), colorfmt="bgr")
                tex.flip_vertical()
                self._preview_tex = tex
                prev = self.ids.get("cam_preview")
                if prev is not None:
                    prev.texture = tex
            tex.blit_buffer(frame.tobytes(), colorfmt="bgr", bufferfmt="ubyte")
        except Exception as e:
            LOG.error("face preview update err: %s", e)
            return
        # Primo frame live blittato: rivela il video con una transizione.
        if not self.cam_ready:
            self._on_camera_ready()

    def _start_scan_animation(self) -> None:
        # phase: 0 -> 1 -> 0 in ~7s totali (ping-pong, loop).
        # La linea arancione scende lentamente dall'alto verso il basso e
        # poi risale, ripetendo continuamente.
        self.phase = 0.0
        self.sweep = 0.0
        anim = (
            Animation(phase=1.0, duration=3.5, t="in_out_sine")
            + Animation(phase=0.0, duration=3.5, t="in_out_sine")
        )
        anim.repeat = True
        self._phase_anim = anim
        self._phase_anim.start(self)
        self._sweep_anim = None

    def _stop_scan_animation(self) -> None:
        for anim_attr in ("_phase_anim", "_sweep_anim"):
            try:
                a = getattr(self, anim_attr, None)
                if a is not None:
                    a.cancel(self)
            except Exception:
                pass
            setattr(self, anim_attr, None)
        self.scanning = False

    # --------------------------- recognition -------------------------------

    def _scan_tick(self, *_):
        if self._submitting:
            return
        # Scan in thread pool style: spawn one-shot thread per tick.
        # Evita di bloccare il main loop di Kivy con HOG+encoding (~150ms).
        with self._cap_lock:
            frame = None if self._latest_frame is None else self._latest_frame.copy()
        if frame is None:
            return
        threading.Thread(target=self._scan_worker, args=(frame,), name="face-scan", daemon=True).start()

    def _scan_worker(self, frame_bgr) -> None:
        face = self.app_ctx.face
        is_avail = (face is not None and (
            getattr(face, "is_available", lambda: False)() or
            getattr(face, "engine_name", "") in ("arcface", "dlib")
        ))
        if not is_avail:
            Clock.schedule_once(lambda *_: setattr(self, "stato", "Riconoscimento non configurato"), 0)
            return
        # Liveness (blink) — l'EAR si calcola su grayscale dell'RGB, ma
        # accetta anche BGR rifiutando solo il colore. Pass-through.
        try:
            if self._liveness is not None:
                # convert bgr -> rgb best-effort
                try:
                    import cv2
                    rgb_for_eye = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                except Exception:
                    rgb_for_eye = frame_bgr[..., ::-1]
                self._liveness.update(rgb_for_eye)
        except Exception:
            pass
        try:
            import cv2
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        except Exception:
            rgb = frame_bgr[..., ::-1]
        try:
            match = face.scan_frame(rgb)
        except Exception as e:
            LOG.warning("scan_frame err: %s", e)
            return
        # Embedding (solo se ArcFace) per unknown tracking.
        emb = None
        try:
            if hasattr(face, "encode_frame"):
                # encode_frame si aspetta RGB
                try:
                    import cv2
                    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                except Exception:
                    rgb = frame_bgr[..., ::-1]
                emb = face.encode_frame(rgb)
        except Exception:
            emb = None
        Clock.schedule_once(lambda *_: self._on_scan_result(match, frame_bgr, emb), 0)

    def _on_scan_result(self, match, frame_bgr=None, emb=None) -> None:
        cfg = self.app_ctx.config.get("face_recognition", {}) or {}
        # match dict possibilita':
        #   None                                 -> nessun volto
        #   {"match": True, "nome": ..., ...}    -> match (ArcFace)
        #   {"match": False, "best_user": ...}   -> volto presente, no match (ArcFace)
        #   {"nome": ..., ...}                   -> match (engine dlib legacy)
        is_match = bool(match) and (match.get("match") is not False) and ("nome" in match)
        face_present = bool(match) or emb is not None

        if match and match.get("borderline") and not self._borderline_logged:
            self._log_borderline(match)

        # ---- voting -------------------------------------------------------
        if is_match:
            self._votes.append(match.get("nome"))
            self._last_match = match
        else:
            # Sentinel None per voto "non match" (mantiene la finestra mobile).
            self._votes.append(None)
            if face_present:
                self._consec_unknown += 1
            else:
                self._consec_unknown = 0

        # Conteggi voto piu' frequente
        if is_match:
            from collections import Counter
            c = Counter(v for v in self._votes if v)
            if c:
                top_name, top_count = c.most_common(1)[0]
            else:
                top_name, top_count = None, 0
        else:
            top_name, top_count = None, 0

        if is_match:
            nome = match.get("nome", "?")
            self.face_detected = True
            self.stato = f"Identificato {nome.replace('_',' ')}"
            # Health hook
            try:
                if self.app_ctx.health is not None:
                    self.app_ctx.health.mark_face_match()
            except Exception:
                pass
            # Soglia voto + liveness + dominanza sul secondo candidato
            if top_count >= self._vote_required:
                if self._vote_min_lead > 0 and len(c) > 1:
                    second_count = c.most_common(2)[1][1]
                    if top_count - second_count < self._vote_min_lead:
                        self.stato = "Conferma identità…"
                        return
                target = self._last_match or match
                dist = float(target.get("distance") or 999)
                margin = float(target.get("margin") or 0)
                high_conf = dist <= 0.38 and margin >= 0.18
                if self._liveness_required and not high_conf:
                    if (self._liveness is None
                            or not self._liveness.is_supported()):
                        self.stato = "Verifica biometrica non disponibile"
                        return
                    if not self._liveness.is_alive(self._min_blinks):
                        self.stato = "Battiti palpebra per conferma"
                        return
                # OK: usa l'ULTIMO match (con metadata corretti)
                self._success(target)
            return

        # ---- nessun match in questo frame ---------------------------------
        if face_present:
            self.face_detected = True
            if not self.stato.startswith("Identificato"):
                self.stato = "Volto non riconosciuto"
            # Tracking unknown: dopo N frame consecutivi unknown registriamo.
            try:
                if (emb is not None and
                        self._consec_unknown >= int(cfg.get("unknown_min_frames", 3)) and
                        getattr(self.app_ctx, "unknown_tracker", None) is not None):
                    # Crop semplice: usa l'intero frame (downsampled).
                    rgb_thumb = None
                    try:
                        import cv2
                        rgb_thumb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    except Exception:
                        rgb_thumb = frame_bgr[..., ::-1] if frame_bgr is not None else None
                    self.app_ctx.unknown_tracker.observe(emb, rgb_thumb)
                    # Audit (solo una volta per scan): debounce con _consec_unknown
                    self.app_ctx.record_event(
                        "face_unknown", method="face", success=False,
                        meta={"consec": self._consec_unknown})
                    # Reset counter per non riosservare ad ogni frame
                    self._consec_unknown = 0
            except Exception as _e:
                LOG.debug("unknown observe err: %s", _e)
        else:
            self.face_detected = False
            if self.stato.startswith("Identificato") or self.stato.startswith("Volto non"):
                self.stato = "Inquadra il volto"

    def _log_borderline(self, match: dict) -> None:
        """Audit una tantum per scan quando il match e' ambiguo."""
        self._borderline_logged = True
        meta = {
            "nome": match.get("nome") or match.get("best_user"),
            "second_user": match.get("second_user"),
            "distance": match.get("distance"),
            "second_distance": match.get("second_distance"),
            "margin": match.get("margin"),
            "reject_reason": match.get("reject_reason"),
            "engine": getattr(self.app_ctx.face, "engine_name", ""),
        }
        try:
            self.app_ctx.record_event(
                "face_borderline", method="face", success=False, meta=meta)
        except Exception:
            pass
        LOG.info("face borderline audit: %s", meta)

    # --------------------------- outcomes ----------------------------------

    def _success(self, utente: dict) -> None:
        if self._submitting:
            return
        self._submitting = True
        if self._timeout_ev:
            self._timeout_ev.cancel()
            self._timeout_ev = None
        scope = utente.get("apre", "porta")
        nome = utente.get("nome", "")
        nome_h = nome.replace("_", " ")
        # Apertura via doppio canale (REST + MQTT, vedi PinScreen._apri).
        rest_ok = False
        try:
            rest_ok = (
                self.app_ctx.ha.apri_porta() if scope == "porta"
                else self.app_ctx.ha.apri_cancello()
            )
        except Exception as e:
            LOG.warning("apri (REST) face err: %s", e)
        try:
            self.app_ctx.mqtt.publish_apertura(metodo="face", utente=nome, scope=scope)
        except Exception as e:
            LOG.warning("publish_apertura face err: %s", e)
        LOG.info("face success scope=%s rest_ok=%s nome=%s dist=%.3f",
                 scope, rest_ok, nome, float(utente.get("distance", -1)))
        try:
            self.app_ctx.record_open(
                method="face", user=nome, scope=scope, success=True,
                distance=float(utente.get("distance", -1)),
                similarity=float(utente.get("similarity", 0.0)),
                engine=getattr(self.app_ctx.face, "engine_name", ""),
                liveness_blinks=(self._liveness.blinks if self._liveness else None),
            )
        except Exception:
            pass
        # Schermata Porta aperta con saluto personalizzato e variabile
        # in base alla fascia oraria (mattina/pomeriggio/sera/notte) e al
        # sesso dell'utente. Vedi modules/greetings.py.
        genere = (utente.get("genere") or "").upper()
        saluto = build_greeting(nome_h, genere) if nome_h else ""
        try:
            result = self.manager.get_screen("result")
            titolo = "Porta aperta" if scope == "porta" else "Cancello aperto"
            image = "assets/door_open.png" if scope == "porta" else ""
            result.mostra_risultato(
                success=True, titolo=titolo, dettaglio=saluto, image_source=image,
            )
            self.manager.current = "result"
        except Exception as e:
            LOG.error("transition result err: %s", e)
        # Saluto vocale (TTS) parte DOPO la fine effettiva del feedback
        # acustico di successo (durata WAV + 0.25s di gap). Usiamo il
        # callback on_end di SoundFx cosi' il delay e' calcolato sulla
        # durata reale del WAV e non su un timer statico.
        try:
            if saluto and getattr(self.app_ctx, "tts", None):
                tts = self.app_ctx.tts
                self.app_ctx.sound.play(
                    "success",
                    on_end=lambda t=saluto: tts.speak(t),
                    on_end_gap=0.25,
                )
            else:
                self.app_ctx.sound.play("success")
        except Exception as e:
            LOG.debug("tts saluto err: %s", e)

    def _on_timeout(self, *_):
        if self._submitting:
            return
        self._submitting = True
        self._stop_scan_animation()
        try:
            self.app_ctx.sound.play("error")
        except Exception:
            pass
        try:
            result = self.manager.get_screen("result")
            result.mostra_risultato(
                success=False,
                titolo="Volto non riconosciuto",
                dettaglio="Riprova o usa il PIN",
                image_source="assets/face_unknown.png",
            )
            self.manager.current = "result"
        except Exception as e:
            LOG.error("transition result err: %s", e)

    # --------------------------- nav ---------------------------------------

    def go_home(self) -> None:
        self.app_ctx.activity_touch()
        self.manager.current = "home"

    def on_touch_down(self, touch):
        self.app_ctx.activity_touch()
        return super().on_touch_down(touch)
