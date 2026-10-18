"""Riconoscimento facciale automatico (motion-triggered).

Quando il MotionDetector rileva attivita', se la home screen e' attiva e
non c'e' una chiamata in corso, AutoFaceScanner avvia uno "scan
silenzioso" usando PicamSession (modalita' face). Se in `max_seconds`
secondi trova un volto registrato che supera il voting + liveness,
pubblica l'apertura senza richiedere il tap su "Volto".

Sicurezza: per evitare false aperture indesiderate, la modalita' e'
disattivata di default. Quando attiva, richiede:
  - liveness (blink) confermato
  - voting maggioritario su finestra
  - homepage stabile (no chiamata, no schermata speciale)

Configurazione (`face_recognition.auto_recognize`):
    enabled: false
    max_seconds: 6
    cooldown_sec: 30
    require_liveness: true
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter, deque
from typing import Any, Callable, Optional


LOG = logging.getLogger(__name__)


class AutoFaceScanner:
    def __init__(self, app,
                 cfg: Optional[dict] = None) -> None:
        # `app` puo' essere l'istanza App (preferito) oppure un AppContext.
        # Risolve sm/face/mqtt/ha/record_open in modo difensivo.
        self.app = app
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.max_seconds = float(cfg.get("max_seconds", 6.0))
        self.cooldown_sec = float(cfg.get("cooldown_sec", 30.0))
        self.require_liveness = bool(cfg.get("require_liveness", True))
        # Bypass liveness su match ad alta confidenza (come la schermata
        # manuale): se la distanza e' molto bassa e il margine ampio, il
        # blink non viene richiesto. Coerente con FaceScreen._on_scan_result.
        self.liveness_skip_dist = float(cfg.get("liveness_skip_dist", 0.38))
        self.liveness_skip_margin = float(cfg.get("liveness_skip_margin", 0.18))
        self.vote_window = int(cfg.get("vote_window", 5))
        self.vote_required = int(cfg.get("vote_required", 3))
        self.vote_min_lead = int(cfg.get("vote_min_lead", 2))
        self.scan_hz = float(cfg.get("scan_hz", 4.0))
        # Secondi dedicati al solo ammiccamento dopo che l'identita' e' certa.
        # Servono perche' il ciclo di scansione, rallentato dal riconoscimento,
        # campiona gli occhi ~4 volte al secondo: troppo poco per cogliere un
        # battito di ciglia, che dura fra un decimo e mezzo secondo.
        self.blink_window_sec = float(cfg.get("blink_window_sec", 6.0))
        self._lock = threading.Lock()
        self._last_run = 0.0
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def _sm_current(self) -> str:
        try:
            return getattr(self.app.sm, "current", "")
        except Exception:
            return ""

    def trigger(self) -> bool:
        """Innesca uno scan se cooldown rispettato e contesto OK.
        Ritorna True se lo scan e' stato avviato."""
        if not self.enabled:
            return False
        now = time.time()
        with self._lock:
            if self._running:
                return False
            if now - self._last_run < self.cooldown_sec:
                return False
            cur = self._sm_current()
            if cur != "home":
                return False
            self._running = True
            self._last_run = now
        threading.Thread(target=self._run, name="auto-face", daemon=True).start()
        return True

    def _run(self) -> None:
        face = getattr(self.app, "face", None)
        if face is None or not getattr(face, "engine_name", "disabled") in ("arcface", "dlib"):
            self._running = False
            return
        sess = None
        paused_go2rtc = False
        try:
            from modules.go2rtc_control import pause_for_camera, resume_after_camera
            from modules.camera_session import PicamSession  # type: ignore
            pause_for_camera("auto_face")
            paused_go2rtc = True
            sess = PicamSession.instance()
            if not sess.acquire("face"):
                LOG.info("auto_face: PicamSession.acquire(face) FAIL")
                return
        except Exception as e:
            LOG.info("auto_face acquire err: %s", e)
            return
        LOG.info("auto_face: scan avviato (max=%.1fs liveness=%s vote_req=%d)",
                 self.max_seconds, self.require_liveness, self.vote_required)

        liveness = None
        lv = self._liveness_cfg()
        if self.require_liveness:
            try:
                from modules.liveness import LivenessChecker
                liveness = LivenessChecker(ear_threshold=lv["ear"],
                                           consec_frames=lv["consec"],
                                           min_blinks=lv["min_blinks"])
                if not liveness.is_supported():
                    liveness = None
            except Exception:
                liveness = None

        votes = deque(maxlen=self.vote_window)
        last_match = None
        deadline = time.time() + self.max_seconds
        n_frames = 0
        n_none = 0
        n_match = 0
        n_detected = 0
        try:
            while time.time() < deadline:
                rgb = sess.capture("face")
                if rgb is None:
                    n_none += 1
                    time.sleep(1.0 / max(1.0, self.scan_hz))
                    continue
                n_frames += 1
                try:
                    if liveness is not None:
                        liveness.update(rgb)
                except Exception:
                    pass
                try:
                    match = face.scan_frame(rgb)
                except Exception:
                    match = None
                if match:
                    n_detected += 1
                if match and match.get("match") is not False and match.get("nome"):
                    n_match += 1
                    votes.append(match.get("nome"))
                    last_match = match
                else:
                    votes.append(None)
                # Soglia
                c = Counter(v for v in votes if v)
                if c:
                    name, cnt = c.most_common(1)[0]
                    if cnt >= self.vote_required:
                        if self.vote_min_lead > 0 and len(c) > 1:
                            second = c.most_common(2)[1][1]
                            if cnt - second < self.vote_min_lead:
                                time.sleep(1.0 / max(1.0, self.scan_hz))
                                continue
                        target = last_match or {"nome": name}
                        dist = float(target.get("distance") or 999)
                        mrg = float(target.get("margin") or 0)
                        high_conf = (dist <= self.liveness_skip_dist
                                     and mrg >= self.liveness_skip_margin)
                        alive = (liveness is None or
                                 not self.require_liveness or
                                 high_conf or
                                 liveness.is_alive(lv["min_blinks"]))
                        if not alive:
                            # Identita' certa, manca solo la prova di vita: si
                            # smette di far girare il riconoscimento e si guarda
                            # solo l'occhio, alla velocita' della camera.
                            alive = self._attendi_blink(sess, face, liveness,
                                                        lv, name, deadline)
                        if alive:
                            LOG.info("auto_face: APRO nome=%s voti=%d/%d "
                                     "dist=%.3f margine=%.3f high_conf=%s "
                                     "frames=%d detected=%d",
                                     name, cnt, self.vote_required, dist, mrg,
                                     high_conf, n_frames, n_detected)
                            self._open_door(target)
                            return
                        else:
                            LOG.info("auto_face: %s riconosciuto (%d voti) "
                                     "dist=%.3f margine=%.3f ma liveness non "
                                     "confermata (%s)",
                                     name, cnt, dist, mrg,
                                     self._diag_liveness(liveness))
                time.sleep(1.0 / max(1.0, self.scan_hz))
            top = ""
            top_cnt = 0
            cc = Counter(v for v in votes if v)
            if cc:
                top, top_cnt = cc.most_common(1)[0]
            LOG.info("auto_face: timeout senza apertura "
                     "(frames=%d none=%d detected=%d match=%d top=%s/%d "
                     "vote_req=%d liveness_req=%s %s)",
                     n_frames, n_none, n_detected, n_match, top or "-",
                     top_cnt, self.vote_required, self.require_liveness,
                     self._diag_liveness(liveness))
        finally:
            try:
                sm = getattr(self.app, "sm", None)
                cur = getattr(sm, "current", "") if sm else ""
                if sess is not None and cur not in ("face", "calling", "conversation"):
                    try:
                        mcfg = (getattr(self.app, "cfg", {}) or {}).get("motion", {})
                        if mcfg.get("source") == "picamera":
                            sess.acquire("motion")
                        else:
                            sess.release()
                    except Exception:
                        pass
            except Exception:
                pass
            if paused_go2rtc:
                try:
                    from modules.go2rtc_control import resume_after_camera
                    resume_after_camera("auto_face")
                except Exception:
                    pass
            self._running = False

    def _liveness_cfg(self) -> dict:
        """Parametri del blink detector, riletti a ogni scan dalla config live.

        Stanno in `face_recognition`, non in `auto_recognize`: sono gli stessi
        che usa la schermata Volto, e vanno passati al checker perche' i suoi
        default (soglia 0.21, due frame consecutivi a occhi chiusi) non sono
        raggiungibili al ritmo di campionamento di questa scansione."""
        fr = {}
        try:
            fr = (getattr(self.app, "cfg", None) or {}).get(
                "face_recognition") or {}
        except Exception:
            fr = {}
        try:
            return {
                "ear": float(fr.get("liveness_ear", 0.18)),
                "consec": max(1, int(fr.get("liveness_consec", 1))),
                "min_blinks": max(1, int(fr.get("liveness_min_blinks", 1))),
            }
        except Exception:
            return {"ear": 0.18, "consec": 1, "min_blinks": 1}

    @staticmethod
    def _diag_liveness(liveness) -> str:
        if liveness is None:
            return "liveness=n/d"
        ear_min = getattr(liveness, "ear_min", None)
        return ("liveness blink=%d occhi_visti=%d ear_min=%s"
                % (getattr(liveness, "blinks", 0),
                   getattr(liveness, "frames_face", 0),
                   "-" if ear_min is None else "%.3f" % ear_min))

    def _attendi_blink(self, sess, face, liveness, lv: dict, nome: str,
                       deadline: float) -> bool:
        """Attende un ammiccamento campionando solo gli occhi.

        Ricontrolla comunque l'identita' ogni mezzo secondo: se davanti alla
        telecamera resta un'altra persona, o non resta nessuno, si rinuncia,
        altrimenti si finirebbe per aprire a nome di chi era passato prima."""
        fine = max(deadline, time.time() + self.blink_window_sec)
        LOG.info("auto_face: %s riconosciuto, attendo l'ammiccamento "
                 "(max %.1fs)", nome, fine - time.time())
        ultimo_controllo = time.time()
        persi = 0
        while time.time() < fine:
            rgb = sess.capture("face")
            if rgb is None:
                time.sleep(0.05)
                continue
            try:
                liveness.update(rgb)
            except Exception:
                pass
            if liveness.is_alive(lv["min_blinks"]):
                return True
            if time.time() - ultimo_controllo >= 0.5:
                ultimo_controllo = time.time()
                try:
                    m = face.scan_frame(rgb)
                except Exception:
                    m = None
                stesso = bool(m and m.get("nome") == nome
                              and m.get("match") is not False)
                persi = 0 if stesso else persi + 1
                if persi >= 3:
                    LOG.info("auto_face: %s non piu' inquadrato, rinuncio "
                             "all'attesa dell'ammiccamento (%s)",
                             nome, self._diag_liveness(liveness))
                    return False
        return False

    def _open_door(self, match: dict) -> None:
        nome = match.get("nome", "")
        scope = match.get("apre", "porta")
        ctx = getattr(self.app, "ctx", None)
        if ctx is not None:
            ctx.open_access(
                method="face_auto", user=nome, scope=scope,
                distance=float(match.get("distance", -1)),
            )
        LOG.info("auto_face: aperto scope=%s nome=%s", scope, nome)
        # UI feedback (deve girare sul thread di Kivy): mostra la stessa
        # schermata "Porta aperta / Cancello aperto" del flusso manuale,
        # con saluto personalizzato e TTS dopo il suono di successo.
        try:
            self._schedule_ui_feedback(nome, scope, match.get("genere", ""))
        except Exception as e:
            LOG.debug("auto_face ui feedback err: %s", e)

    def _schedule_ui_feedback(self, nome: str, scope: str, genere: str) -> None:
        try:
            from kivy.clock import Clock  # type: ignore
        except Exception:
            return
        Clock.schedule_once(
            lambda *_: self._show_result(nome, scope, genere), 0)

    def _show_result(self, nome: str, scope: str, genere: str) -> None:
        sm = getattr(self.app, "sm", None)
        if sm is None:
            return
        # Se siamo in screensaver, prima riportiamo a home (come fa il
        # wake da motion) cosi' la transizione a "result" e' coerente.
        try:
            if sm.current == "screensaver":
                sm.current = "home"
        except Exception:
            pass
        nome_h = (nome or "").replace("_", " ")
        saluto = ""
        try:
            from modules.greetings import build_greeting  # type: ignore
            saluto = build_greeting(nome_h, (genere or "").upper()) if nome_h else ""
        except Exception:
            saluto = (f"Bentornato {nome_h}" if nome_h else "")
        try:
            result = sm.get_screen("result")
            titolo = "Porta aperta" if scope == "porta" else "Cancello aperto"
            image = "assets/door_open.png" if scope == "porta" else ""
            result.mostra_risultato(success=True, titolo=titolo,
                                    dettaglio=saluto, image_source=image)
            sm.current = "result"
        except Exception as e:
            LOG.warning("auto_face transition result err: %s", e)
            return
        # Suono + TTS (saluto dopo la fine del WAV di successo)
        ctx = getattr(self.app, "ctx", None)
        sound = getattr(ctx, "sound", None) if ctx is not None else None
        tts = getattr(ctx, "tts", None) if ctx is not None else None
        try:
            if sound is not None:
                if saluto and tts is not None:
                    sound.play("success",
                               on_end=lambda t=saluto: tts.speak(t),
                               on_end_gap=0.25)
                else:
                    sound.play("success")
        except Exception as e:
            LOG.debug("auto_face sound/tts err: %s", e)
