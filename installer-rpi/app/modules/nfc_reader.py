"""Lettore NFC in background per il videocitofono.

Supporta:
- PN532 via UART/USB (driver `nfcpy`, path tipico `/dev/ttyUSB0`)
- ACR122U USB CCID (driver `nfcpy` via libusb)

Architettura:
- Un thread daemon `NfcReader` apre il device e fa polling continuo per
  tag (`clf.connect(rdwr=...)`).
- Quando un tag e' rilevato, chiama `on_tag(uid_hex)` (callback fornita
  dal main app). Il callback DEVE essere thread-safe: se vuole
  aggiornare la UI, schedulare con `Clock.schedule_once`.
- Tra una rilevazione e la successiva c'e' un `cooldown_sec` (default 2s)
  per evitare burst di eventi sullo stesso tag.
- `start()` avvia il thread, `stop()` lo ferma; `is_available()` dice se
  il driver e' caricato.
- `enroll_next(timeout_sec)` blocca per timeout secondi e ritorna l'UID
  del prossimo tag rilevato (None se timeout). Usato per iscrizione.

Library mapping (UID -> utente):
- Il mapping e' gestito esternamente in NfcLibrary (vedi sotto): un file
  JSON `data/nfc_library.json` con struttura:
    {"<UID_HEX>": {"nome": "Mario", "scope": "porta",
                    "label": "Portachiavi", "added_ts": 1234}}
- Il NfcReader NON conosce gli utenti: si limita a notificare l'UID al
  callback del main, che fa il match e l'apertura.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional

LOG = logging.getLogger(__name__)

# Bug USB BCM: attesa ~1 s o ~3 s tra close e open ritarda il primo byte
# fino a 1 s. nfcpy: a ~2 s la finestra e' buona. Non usare 3.0.
USB_REOPEN_SETTLE_SEC = 2.2
USB_RECOVER_SETTLE_SEC = 8.0
# DWC3 del CH340 fa over-current e stacca anche il touch (1a86:e5e3).
# Il recover automatico è solo UART (DTR/RTS). USB_RECOVER_MAX=0: mai hard.
USB_RECOVER_COOLDOWN_SEC = 180.0
USB_RECOVER_RETRY_SEC = 180.0
USB_RECOVER_MAX = 0
USB_RECOVER_MODES = ("hard",)
# Dopo cold-power il PN532 e' gia' a posto: troppi reset USB fanno
# cadere il touch. nfcpy va ritentato molte volte prima di un DWC3.
NFC_OPEN_FAILS_BEFORE_USB = 8
NFC_GIVE_UP_BACKOFF_SEC = 12.0
UART_MUTE_BACKOFF_SEC = 12.0

# Path nfcpy da provare in ordine (PN532 UART/I2C, ACR122U).
DEFAULT_DEVICE_CANDIDATES = (
    "tty:USB0:pn532",
    "tty:USB1:pn532",
    "i2c:1:0x24",
    "i2c:10:0x24",
    "usb",
)


def _uart_dev_from_nfcpy(path: str) -> Optional[str]:
    if not path.startswith("tty:"):
        return None
    return f"/dev/tty{path.split(':')[1]}"


def _pn532_hsu_frame(body: bytes) -> bytes:
    ln = len(body) + 1
    return (bytes([0x00, 0x00, 0xFF, ln, (-ln) & 0xFF])
            + body + bytes([(-sum(body)) & 0xFF, 0x00]))


def uart_pn532_responds(path: str) -> bool:
    """True se il PN532 risponde al GetFirmwareVersion via UART."""
    return uart_pn532_reset_and_wake(path, attempts=1, reset_lines=False)


def uart_pn532_reset_and_wake(
    path: str,
    attempts: int = 3,
    reset_lines: bool = False,
) -> bool:
    """Preamble 0x55 + GetFirmwareVersion. DTR/RTS solo se reset_lines.

    Su questo hardware il pulse DTR tiene il PN532 in reset (vedi
    nfc-usb-reset.sh). Il default e' solo ping, senza toccare le linee.
    """
    dev = _uart_dev_from_nfcpy(path)
    if not dev or not os.path.exists(dev):
        return False
    try:
        import serial  # type: ignore
    except Exception as e:
        LOG.debug("pyserial assente: %s", e)
        return False
    fw = _pn532_hsu_frame(bytes([0xD4, 0x02]))
    sam = _pn532_hsu_frame(bytes([0xD4, 0x14, 0x01, 0x00, 0x00]))
    polarities = (
        (False, False, True, True),
        (True, True, False, False),
        (False, True, True, False),
        (True, False, False, True),
    )
    last_rx = b""
    for i in range(max(1, attempts)):
        dtr0, rts0, dtr1, rts1 = polarities[i % len(polarities)]
        try:
            with serial.Serial(dev, baudrate=115200, timeout=0.4) as ser:
                if reset_lines:
                    ser.dtr = dtr0
                    ser.rts = rts0
                    time.sleep(0.25)
                    ser.dtr = dtr1
                    ser.rts = rts1
                    time.sleep(0.2)
                    try:
                        ser.send_break(duration=0.08)
                    except Exception:
                        pass
                    time.sleep(0.05)
                ser.reset_input_buffer()
                ser.write(b"\x55" * 32)
                time.sleep(0.08)
                ser.reset_input_buffer()
                ser.write(fw)
                time.sleep(0.25)
                last_rx = ser.read(64)
                if len(last_rx) >= 7 and 0xD5 in last_rx:
                    try:
                        ser.write(sam)
                        time.sleep(0.12)
                        ser.read(32)
                    except Exception:
                        pass
                    LOG.info("PN532 UART ok su %s (tentativo %d, rx=%d)",
                             path, i + 1, len(last_rx))
                    return True
        except Exception as e:
            LOG.debug("uart_pn532_reset_and_wake %s: %s", dev, e)
        time.sleep(0.35)
    LOG.info("PN532 UART muto su %s (rx=%s)",
             path, last_rx.hex() if last_rx else "0")
    return False


def disable_ch340_autosuspend() -> bool:
    """Evita autosuspend USB sul CH340 (causa timeout PN532 a riposo)."""
    try:
        for d in glob.glob("/sys/bus/usb/devices/*"):
            vf, pf = os.path.join(d, "idVendor"), os.path.join(d, "idProduct")
            if not (os.path.isfile(vf) and os.path.isfile(pf)):
                continue
            with open(vf, encoding="ascii") as f:
                v = f.read().strip()
            with open(pf, encoding="ascii") as f:
                p = f.read().strip()
            if v != "1a86" or p != "7523":
                continue
            ctrl = os.path.join(d, "power", "control")
            auto = os.path.join(d, "power", "autosuspend")
            if os.path.isfile(ctrl):
                with open(ctrl, "w", encoding="ascii") as f:
                    f.write("on")
            if os.path.isfile(auto):
                with open(auto, "w", encoding="ascii") as f:
                    f.write("-1")
            LOG.info("CH340 autosuspend off (%s)", os.path.basename(d))
            return True
    except OSError as e:
        LOG.debug("disable_ch340_autosuspend: %s", e)
    return False


def ensure_pn532_ready(path: str, attempts: int = 4) -> bool:
    """Wake UART + verifica risposta PN532 prima di aprire nfcpy."""
    disable_ch340_autosuspend()
    dev = _uart_dev_from_nfcpy(path)
    if dev and not os.path.exists(dev):
        for _ in range(20):
            if os.path.exists(dev):
                break
            time.sleep(0.5)
    if uart_pn532_reset_and_wake(path, attempts=attempts, reset_lines=False):
        time.sleep(0.4)
        return True
    LOG.info("PN532 wake UART senza risposta su %s", path)
    return False


NFC_USB_RESET_SCRIPT = "/opt/videocitofono/scripts/nfc-usb-reset.sh"
NFC_PREP_STAMP = "/run/videocitofono-nfc-ready"
NFC_PREP_STAMP_MAX_AGE = 120.0


def nfc_prep_mode() -> str:
    """'skip' se prep recente (boot systemd), altrimenti 'recover' (restart servizio)."""
    if os.path.isfile(NFC_PREP_STAMP):
        age = time.time() - os.path.getmtime(NFC_PREP_STAMP)
        if age < NFC_PREP_STAMP_MAX_AGE:
            return "skip"
    return "recover"


def nfc_recover_mode(n: int) -> str:
    """Ciclo recover (CH340) -> hard (xhci CH340) -> power (VBUS)."""
    return USB_RECOVER_MODES[int(n) % len(USB_RECOVER_MODES)]


def prepare_nfc_hardware(mode: str = "recover") -> bool:
    """Reset software del PN532 (CH340 / xhci / VBUS). Niente stacco USB."""
    if mode == "boot" and os.path.isfile(NFC_PREP_STAMP):
        age = time.time() - os.path.getmtime(NFC_PREP_STAMP)
        if age < NFC_PREP_STAMP_MAX_AGE:
            LOG.info("NFC prepare: skip reset USB (prep %.0fs fa), solo wake", age)
            return _prepare_nfc_hardware_inline()
    if os.path.isfile(NFC_USB_RESET_SCRIPT):
        try:
            r = subprocess.run(
                ["sudo", "-n", NFC_USB_RESET_SCRIPT, mode],
                capture_output=True, text=True, timeout=120, check=False)
            if r.returncode == 0:
                LOG.info("NFC prepare (%s): ok", mode)
                try:
                    with open(NFC_PREP_STAMP, "w", encoding="ascii") as f:
                        f.write(str(time.time()))
                except OSError:
                    pass
                return True
            LOG.warning("NFC prepare (%s) rc=%s: %s",
                        mode, r.returncode, (r.stderr or r.stdout or "")[-200:])
        except Exception as e:
            LOG.warning("NFC prepare script err: %s", e)
    return _prepare_nfc_hardware_inline()


def _prepare_nfc_hardware_inline() -> bool:
    """Fallback senza script systemd (solo wake UART, no libnfc)."""
    dev = "/dev/ttyUSB0"
    if not os.path.exists(dev):
        for _ in range(15):
            if os.path.exists(dev):
                break
            time.sleep(1)
    disable_ch340_autosuspend()
    return ensure_pn532_ready("tty:USB0:pn532", attempts=6) or os.path.exists(dev)


def discover_tty_pn532_paths() -> List[str]:
    """Path nfcpy per ogni /dev/ttyUSB* presente (ordine kernel)."""
    paths: List[str] = []
    for dev in sorted(glob.glob("/dev/ttyUSB*")):
        n = dev.rsplit("USB", 1)[-1]
        if n.isdigit():
            paths.append(f"tty:USB{n}:pn532")
    return paths or ["tty:USB0:pn532"]


def probe_nfc_device(candidates: tuple[str, ...] | list[str]) -> Optional[str]:
    """Restituisce il primo path nfcpy che apre (solo diagnostica manuale)."""
    try:
        import nfc  # type: ignore
    except Exception as e:
        LOG.warning("nfcpy non disponibile: %s", e)
        return None
    for path in candidates:
        try:
            clf = nfc.ContactlessFrontend(path)
            LOG.info("NFC probe OK: %s (%s)", path, clf.device)
            clf.close()
            return path
        except Exception as e:
            LOG.debug("NFC probe fail %s: %s", path, e)
    return None


class NfcReader:
    """Lettore NFC PN532/ACR122U in thread di background."""

    def __init__(
        self,
        device: str = "tty:USB0:pn532",
        cooldown_sec: float = 2.0,
        on_tag: Optional[Callable[[str], None]] = None,
        device_candidates: Optional[list[str]] = None,
        hw_prep_done: bool = False,
    ) -> None:
        # device: stringa nfcpy
        #   "tty:USB0:pn532"  -> PN532 HSU su /dev/ttyUSB0
        #   "tty:S0:pn532"    -> PN532 HSU su /dev/ttyS0
        #   "usb"             -> primo USB compatibile (ACR122U etc.)
        #   "usb:072f:2200"   -> ACR122U specifico
        cands = list(device_candidates or [])
        if device and device not in cands:
            cands.insert(0, device)
        self._configured_candidates = list(dict.fromkeys(cands))
        self.device = device or (self._configured_candidates[0]
                                 if self._configured_candidates else "tty:USB0:pn532")
        self._probe_ok = True
        self.cooldown_sec = float(cooldown_sec)
        self.on_tag = on_tag
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._clf = None
        self._last_error: Optional[str] = None
        self._last_uid: Optional[str] = None
        self._last_uid_ts: float = 0.0
        # Per enroll one-shot
        self._enroll_event = threading.Event()
        self._enroll_uid: Optional[str] = None
        self._available: Optional[bool] = None
        self._device_candidates = self._configured_candidates
        self._device_idx = 0
        self._open_failures = 0
        self._last_serial_close_ts = 0.0
        self._hw_prep_done = bool(hw_prep_done)
        self._usb_recoveries = 0
        self._last_usb_recover_ts = time.time()
        self._pending_usb_recover = False
        self._listen_ok = False
        self._recover_lock = threading.Lock()
        self._tty_was_present = True
        self._tty_lost_ts = 0.0
        self._status_cb: Optional[Callable[[], None]] = None

    def _mark_serial_closed(self) -> None:
        self._last_serial_close_ts = time.time()

    def _present_candidates(self) -> List[str]:
        """Solo path con TTY presente o fallback 'usb'. Evita rotazioni su USB1/i2c assenti."""
        present: List[str] = []
        for path in self._configured_candidates:
            if path.startswith("tty:"):
                dev = _uart_dev_from_nfcpy(path)
                if dev and os.path.exists(dev):
                    present.append(path)
            elif path == "usb" or path.startswith("usb:"):
                present.append(path)
        for path in discover_tty_pn532_paths():
            if path not in present:
                present.append(path)
        if not present:
            present = [self.device] if self.device else ["tty:USB0:pn532"]
        return present

    def _sync_device_candidates(self) -> None:
        self._device_candidates = self._present_candidates()
        if self._device_idx >= len(self._device_candidates):
            self._device_idx = 0
        self.device = self._device_candidates[self._device_idx]

    def _reset_device_primary(self) -> None:
        self._device_idx = 0
        self._sync_device_candidates()
        if self._device_candidates:
            self.device = self._device_candidates[0]

    def _wait_usb_settle(self) -> bool:
        """Attende stabilizzazione USB Pi dopo chiusura seriale."""
        elapsed = time.time() - self._last_serial_close_ts
        need = USB_REOPEN_SETTLE_SEC - elapsed
        if need <= 0:
            return True
        LOG.info("NFC: attesa %.1fs (USB Pi dopo chiusura seriale)", need)
        return not self._stop.wait(need)

    # ---- lifecycle ------------------------------------------------------

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import nfc  # noqa: F401  type: ignore
            self._available = True
        except Exception as e:
            LOG.warning("nfcpy non installato: %s", e)
            self._available = False
        return self._available

    def is_reader_ready(self) -> bool:
        """True solo quando il chip è aperto e in ascolto tag."""
        return self._ready.is_set() and self._clf is not None

    def last_error(self) -> Optional[str]:
        return self._last_error

    def on_status(self, cb: Optional[Callable[[], None]]) -> None:
        """Chiamato quando il lettore passa ready/offline (thread NFC)."""
        self._status_cb = cb

    def _emit_status(self) -> None:
        cb = self._status_cb
        if not cb:
            return
        try:
            cb()
        except Exception as e:
            LOG.debug("nfc status cb: %s", e)

    def probe_ok(self) -> bool:
        return self._probe_ok

    def start(self) -> bool:
        if not self.is_available():
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._loop, name="nfc-reader", daemon=True)
        self._thread.start()
        self._emit_status()
        LOG.info("NfcReader thread avviato (device=%s, probe_ok=%s)",
                 self.device, self._probe_ok)
        return True

    def stop(self, fast: bool = False) -> None:
        self._stop.set()
        self._ready.clear()
        clf = self._clf
        if clf is not None:
            try:
                clf.close()
            except Exception:
                pass
            self._clf = None
            self._mark_serial_closed()
        t = self._thread
        if t and t.is_alive():
            try:
                t.join(timeout=3.0)
            except Exception:
                pass
        self._thread = None
        if not fast:
            time.sleep(USB_REOPEN_SETTLE_SEC)

    # ---- enroll one-shot -----------------------------------------------

    def enroll_next(self, timeout_sec: float = 30.0) -> Optional[str]:
        """Blocca fino a quando un tag viene letto o `timeout_sec` scade.
        Ritorna l'UID hex (lowercase) o None.
        IMPORTANTE: il loop deve essere gia' avviato (start)."""
        deadline = time.time() + min(8.0, timeout_sec * 0.25)
        while not self.is_reader_ready() and time.time() < deadline:
            if self._stop.wait(0.2):
                break
        if not self.is_reader_ready():
            self._last_error = (
                f"lettore non pronto su {self.device} "
                f"({self._last_error or 'in attesa PN532'})")
            return None
        self._enroll_event.clear()
        self._enroll_uid = None
        if self._enroll_event.wait(timeout=timeout_sec):
            return self._enroll_uid
        self._last_error = "timeout: nessun tag rilevato"
        return None

    # ---- internal -------------------------------------------------------

    def _on_connect(self, tag) -> bool:
        try:
            uid = bytes(tag.identifier).hex()
        except Exception:
            uid = ""
        if not uid:
            return False
        now = time.time()
        # Soddisfa enroll one-shot
        if not self._enroll_event.is_set():
            self._enroll_uid = uid
            self._enroll_event.set()
        # Debounce sullo stesso UID
        if (uid == self._last_uid
                and (now - self._last_uid_ts) < self.cooldown_sec):
            return False
        self._last_uid = uid
        self._last_uid_ts = now
        LOG.info("NFC tag: %s", uid)
        if self.on_tag:
            try:
                self.on_tag(uid)
            except Exception as e:
                LOG.error("on_tag callback err: %s", e)
        return False  # release subito (non vogliamo entrare in NDEF rdwr)

    def _disable_pn532_sleep(self, clf) -> None:
        """nfcpy Device.close() manda il PN532 in power_down: al reopen
        il ping UART corto lo dichiara muto. Disattiva solo lo sleep."""
        try:
            clf.device.chipset.power_down = lambda *a, **k: None
        except Exception:
            pass

    def _close_clf(self) -> None:
        clf = self._clf
        self._clf = None
        if clf is None:
            return
        self._disable_pn532_sleep(clf)
        try:
            clf.close()
        except Exception:
            pass
        self._mark_serial_closed()

    def _loop(self) -> None:
        """Ascolto continuo: esce solo su stop() esplicito.

        clf.connect(rdwr=...) di nfcpy e' troppo aggressivo per i cloni
        cinesi (CZ10) con UART HSU. Usiamo clf.sense().
        Dopo spegnimento il PN532 e' gia' resettato: si ritenta nfcpy.
        Un reset DWC3 al massimo (mai VBUS: spegne anche il touch)."""
        import nfc  # type: ignore
        from nfc.clf import RemoteTarget  # type: ignore
        self._emit_status()
        backoff = 2.0
        # Solo 106A (MIFARE/NTAG): 106B/FeliCa ogni 80ms satura i cloni HSU.
        targets = [RemoteTarget("106A")]
        while not self._stop.is_set():
            try:
                self._sync_device_candidates()
                tty_now = any(
                    os.path.exists(_uart_dev_from_nfcpy(p) or "")
                    for p in self._device_candidates if p.startswith("tty:")
                ) or os.path.exists("/dev/ttyUSB0")
                if not tty_now and self._tty_was_present:
                    self._tty_lost_ts = time.time()
                if tty_now and not self._tty_was_present:
                    gone = (time.time() - self._tty_lost_ts
                            if self._tty_lost_ts else 0.0)
                    LOG.info("NFC: tty ricomparso (assente %.0fs)", gone)
                    self._open_failures = 0
                    self._listen_ok = False
                    if gone >= 60.0:
                        self._usb_recoveries = 0
                self._tty_was_present = tty_now
                now = time.time()
                if (self._listen_ok
                        and self._open_failures >= 5
                        and now - self._last_usb_recover_ts >= USB_RECOVER_RETRY_SEC):
                    self._listen_ok = False
                disable_ch340_autosuspend()
                if (not self._listen_ok
                        and self._open_failures >= NFC_OPEN_FAILS_BEFORE_USB
                        and self._usb_recoveries < USB_RECOVER_MAX
                        and now - self._last_usb_recover_ts
                        >= USB_RECOVER_COOLDOWN_SEC):
                    with self._recover_lock:
                        now = time.time()
                        if (self._usb_recoveries < USB_RECOVER_MAX
                                and now - self._last_usb_recover_ts
                                >= USB_RECOVER_COOLDOWN_SEC):
                            mode = nfc_recover_mode(self._usb_recoveries)
                            self._usb_recoveries += 1
                            self._last_usb_recover_ts = time.time()
                            LOG.warning(
                                "NFC: reset software %s (%d/%d)",
                                mode, self._usb_recoveries, USB_RECOVER_MAX)
                            prepare_nfc_hardware(mode)
                            self._mark_serial_closed()
                            self._open_failures = 0
                    self._stop.wait(USB_RECOVER_SETTLE_SEC)
                    if self._stop.is_set():
                        break
                    self._mark_serial_closed()
                    if not self._wait_usb_settle():
                        break
                if not self._wait_usb_settle():
                    break
                self._clf = nfc.ContactlessFrontend(self.device)
                self._disable_pn532_sleep(self._clf)
                self._ready.set()
                self._last_error = None
                self._open_failures = 0
                self._usb_recoveries = 0
                self._listen_ok = True
                LOG.info("NFC reader pronto: %s", self._clf.device)
                self._emit_status()
                backoff = 1.0
                consec_err = 0
                while not self._stop.is_set():
                    try:
                        tgt = self._clf.sense(*targets, iterations=1,
                                              interval=0.25)
                    except (IOError, OSError):
                        consec_err += 1
                        disable_ch340_autosuspend()
                        if consec_err > 40:
                            LOG.warning("NFC sense instabile, riapro il chip")
                            break
                        self._stop.wait(0.2)
                        continue
                    consec_err = 0
                    if tgt is not None and getattr(tgt, "sdd_res", None):
                        class _T:
                            identifier = bytes(tgt.sdd_res)
                        self._on_connect(_T())
                    self._stop.wait(0.20)
            except Exception as e:
                self._ready.clear()
                self._last_error = str(e)
                self._open_failures += 1
                self._emit_status()
                backoff = USB_REOPEN_SETTLE_SEC if self._listen_ok else min(
                    max(backoff, USB_REOPEN_SETTLE_SEC) * 1.2,
                    NFC_GIVE_UP_BACKOFF_SEC)
                LOG.warning("NFC loop err: %s (riapertura ascolto in %.1fs)",
                            e, backoff)
                self._close_clf()
                self._stop.wait(backoff)
                continue
            self._close_clf()
            backoff = 0.3
        self._close_clf()
        self._ready.clear()
        LOG.info("NfcReader thread terminato")


# ====================================================================
# NfcLibrary: mapping UID -> utente
# ====================================================================
class NfcLibrary:
    """Persiste il mapping UID -> {nome, scope, label, added_ts}."""

    def __init__(self, path: str = "/opt/videocitofono/data/nfc_tags.json"):
        self.path = path
        self._lock = threading.RLock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            try:
                if os.path.exists(self.path):
                    with open(self.path, "r", encoding="utf-8") as f:
                        self._data = json.load(f) or {}
                else:
                    self._data = {}
            except Exception as e:
                LOG.warning("nfc lib load err: %s", e)
                self._data = {}

    def _save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except Exception as e:
                LOG.error("nfc lib save err: %s", e)

    def find_by_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._data.get(uid.lower())
            return dict(rec) if rec else None

    def list_tags(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._data)

    def add(self, uid: str, nome: str, scope: str = "porta",
            label: str = "") -> bool:
        uid = (uid or "").lower()
        nome = (nome or "").strip()
        if not uid or not nome:
            return False
        with self._lock:
            self._data[uid] = {
                "nome": nome,
                "scope": scope or "porta",
                "label": label or "",
                "added_ts": int(time.time()),
            }
            self._save()
        return True

    def remove(self, uid: str) -> bool:
        uid = (uid or "").lower()
        with self._lock:
            if uid in self._data:
                del self._data[uid]
                self._save()
                return True
        return False

    def remove_user(self, nome: str) -> int:
        """Rimuove tutti i tag associati a `nome`. Ritorna il conteggio."""
        nome = (nome or "").strip()
        n = 0
        with self._lock:
            for uid in list(self._data.keys()):
                if self._data[uid].get("nome") == nome:
                    del self._data[uid]
                    n += 1
            if n:
                self._save()
        return n
