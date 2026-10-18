"""Schermata Admin: enroll/revoca PIN, NFC, volto. Sblocco con PIN admin."""
from __future__ import annotations

import logging
import threading
from typing import List

from kivy.clock import Clock
from kivy.properties import StringProperty

from .bg_screen import BgScreen

LOG = logging.getLogger(__name__)


class AdminScreen(BgScreen):
    messaggio = StringProperty("")
    elenco = StringProperty("")

    def __init__(self, app_ctx, bg_source: str | None = None, **kw):
        super().__init__(bg_source=bg_source, **kw)
        self.app_ctx = app_ctx

    def on_pre_enter(self, *_):
        self.messaggio = ""
        self._refresh()

    def _nome(self) -> str:
        box = self.ids.get("nome")
        return (box.text if box is not None else "").strip().replace(" ", "_")[:64]

    def _pin(self) -> str:
        box = self.ids.get("pin")
        return (box.text if box is not None else "").strip()

    def _refresh(self) -> None:
        lines: List[str] = []
        try:
            for u in self.app_ctx.pin_manager.elenco_utenti():
                lines.append(f"PIN  {u.get('nome')}  ({u.get('ruolo')}, {u.get('apre')})")
        except Exception as e:
            LOG.debug("admin pin list err: %s", e)
        try:
            lib = self.app_ctx.nfc_lib
            if lib is not None:
                for uid, rec in (lib.list_tags() or {}).items():
                    lines.append(
                        f"NFC  {rec.get('nome')}  {uid[:8]}…  {rec.get('label') or rec.get('scope')}")
        except Exception as e:
            LOG.debug("admin nfc list err: %s", e)
        try:
            for u in self.app_ctx.face.list_users() or []:
                nome = u.get("nome") if isinstance(u, dict) else str(u)
                n = u.get("n_foto", "") if isinstance(u, dict) else ""
                lines.append(f"Volto  {nome}  {n}".rstrip())
        except Exception as e:
            LOG.debug("admin face list err: %s", e)
        self.elenco = "\n".join(lines) if lines else "(nessun record)"

    def go_home(self) -> None:
        self.app_ctx.activity_touch()
        self.app_ctx.go_screen("home", instant=True)

    def add_pin(self) -> None:
        self.app_ctx.activity_touch()
        nome, pin = self._nome(), self._pin()
        res = self.app_ctx.pin_manager.set_user_pin(nome, pin)
        self.messaggio = res.get("msg") or ("ok" if res.get("ok") else "errore")
        self._refresh()

    def del_pin(self) -> None:
        self.app_ctx.activity_touch()
        nome = self._nome()
        ok = self.app_ctx.pin_manager.clear_user_pin(nome)
        self.messaggio = "PIN rimosso" if ok else "utente non trovato"
        self._refresh()

    def nfc_enroll(self) -> None:
        self.app_ctx.activity_touch()
        nome = self._nome()
        nr = self.app_ctx.nfc_reader
        lib = self.app_ctx.nfc_lib
        if not nome:
            self.messaggio = "Serve un nome"
            return
        if nr is None or lib is None:
            self.messaggio = "NFC non disponibile"
            return
        self.messaggio = "Avvicina il badge…"

        def _work():
            uid = nr.enroll_next(timeout_sec=30.0)
            def _done(*_):
                if not uid:
                    self.messaggio = nr.last_error() or "timeout badge"
                    return
                lib.add(uid, nome, "porta", "")
                self.messaggio = f"Badge {uid[:8]}… associato a {nome}"
                self._refresh()
            Clock.schedule_once(_done, 0)

        threading.Thread(target=_work, daemon=True, name="admin-nfc").start()

    def nfc_delete(self) -> None:
        self.app_ctx.activity_touch()
        nome = self._nome()
        lib = self.app_ctx.nfc_lib
        if lib is None or not nome:
            self.messaggio = "Serve un nome"
            return
        n = lib.remove_user(nome)
        self.messaggio = f"Rimossi {n} badge" if n else "nessun badge"
        self._refresh()

    def face_enroll(self) -> None:
        self.app_ctx.activity_touch()
        nome = self._nome()
        if not nome:
            self.messaggio = "Serve un nome"
            return
        self.messaggio = "Scatto in corso…"

        def _work():
            msg = "errore scatto"
            try:
                from modules.camera_session import PicamSession
                from modules.go2rtc_control import pause_for_camera, resume_after_camera
                import cv2  # type: ignore
                pause_for_camera("admin_face")
                sess = PicamSession.instance()
                sess.acquire("face")
                try:
                    bgr = None
                    for _ in range(8):
                        bgr = sess.capture("face")
                        if bgr is not None:
                            break
                    if bgr is None:
                        msg = "camera assente"
                    else:
                        ok, buf = cv2.imencode(".jpg", bgr)
                        if not ok:
                            msg = "jpeg fallito"
                        else:
                            res = self.app_ctx.face.enroll_image(
                                nome, buf.tobytes(), ".jpg")
                            if isinstance(res, dict):
                                msg = res.get("msg") or (
                                    "volto iscritto" if res.get("ok")
                                    else "volto non rilevato")
                            elif isinstance(res, tuple):
                                msg = str(res[-1] if res else "errore")
                            else:
                                msg = "volto iscritto" if res else "volto non rilevato"
                finally:
                    try:
                        sess.release()
                    except Exception:
                        pass
                    resume_after_camera("admin_face")
            except Exception as e:
                LOG.warning("admin face enroll err: %s", e)
                msg = str(e)[:80]
            Clock.schedule_once(lambda *_: self._face_done(msg), 0)

        threading.Thread(target=_work, daemon=True, name="admin-face").start()

    def _face_done(self, msg: str) -> None:
        self.messaggio = msg
        self._refresh()

    def face_delete(self) -> None:
        self.app_ctx.activity_touch()
        nome = self._nome()
        ok = False
        try:
            ok = bool(self.app_ctx.face.delete_user(nome))
        except Exception as e:
            self.messaggio = str(e)[:80]
            return
        self.messaggio = "volto rimosso" if ok else "volto non trovato"
        self._refresh()
