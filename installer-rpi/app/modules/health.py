"""Telemetria health: pubblica metriche periodiche su MQTT.

Topic: videocitofono/health (retain=true)
Payload JSON:
    {
        "ts": 1746543210,
        "uptime_sec": 12345,
        "cpu_pct": 12.4,
        "mem_pct": 35.7,
        "disk_pct": 41.2,
        "temp_c": 52.1,
        "load1": 0.8,
        "version": "1.5.1",
        "screen": "home",
        "last_face_match_ts": 1746543010,
        "last_open_ts": 1746542880,
        "mqtt_connected": true,
        "camera_status": "idle",
        "errors_last_hour": 0,
        "engine_face": "arcface"
    }

Da HA si crea un `mqtt sensor` con json_attributes_topic per
visualizzare uptime/cpu/temp/version sulla dashboard.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from typing import Any, Callable, Dict, Optional


LOG = logging.getLogger(__name__)

_BOOT_TS = time.time()


def _read_cpu_temp() -> Optional[float]:
    paths = (
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/devices/virtual/thermal/thermal_zone0/temp",
    )
    for p in paths:
        try:
            with open(p, "r") as f:
                return int(f.read().strip()) / 1000.0
        except Exception:
            pass
    return None


def _cpu_pct(prev: Dict[str, int]) -> float:
    """CPU usage percentuale tra due chiamate (legge /proc/stat)."""
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        parts = line.split()
        if parts[0] != "cpu":
            return 0.0
        nums = [int(x) for x in parts[1:8]]
        idle = nums[3] + nums[4]
        total = sum(nums)
        d_idle = idle - prev.get("idle", 0)
        d_total = total - prev.get("total", 0)
        prev["idle"] = idle
        prev["total"] = total
        if d_total <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * (1.0 - d_idle / d_total)))
    except Exception:
        return 0.0


def _mem_pct() -> float:
    try:
        with open("/proc/meminfo", "r") as f:
            d = {}
            for ln in f:
                k, _, rest = ln.partition(":")
                v = rest.strip().split()
                if v:
                    d[k] = int(v[0])
        total = d.get("MemTotal", 0)
        avail = d.get("MemAvailable", d.get("MemFree", 0))
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * (total - avail) / total))
    except Exception:
        return 0.0


def _disk_pct(path: str = "/") -> float:
    try:
        usage = shutil.disk_usage(path)
        return 100.0 * usage.used / usage.total
    except Exception:
        return 0.0


def _load1() -> float:
    try:
        return os.getloadavg()[0]
    except Exception:
        return 0.0


def usb_overcurrent_count(window_sec: float = 600.0) -> int:
    """Quanti 'over-current' nel dmesg degli ultimi `window_sec` (default 10 min).

    Il dmesg del boot intero resta pieno di eventi da enumerazione USB e
    da un eventuale recover NFC: non devono tenere l'alert acceso per ore.
    """
    try:
        import re
        import subprocess
        r = subprocess.run(
            ["dmesg"], capture_output=True, text=True, timeout=2, check=False,
        )
        txt = r.stdout or ""
        uptime = 1e12
        try:
            with open("/proc/uptime", encoding="ascii") as f:
                uptime = float(f.read().split()[0])
        except Exception:
            pass
        cutoff = max(0.0, uptime - float(window_sec))
        n = 0
        for line in txt.splitlines():
            if "over-current" not in line.lower():
                continue
            m = re.match(r"^\s*\[\s*(\d+(?:\.\d+)?)\s*\]", line)
            ts = float(m.group(1)) if m else uptime
            if ts >= cutoff:
                n += 1
        return n
    except Exception:
        return 0


def _network_info() -> Dict[str, Any]:
    """Interfaccia attiva e latenza verso gateway (ms)."""
    out: Dict[str, Any] = {"iface": "", "link": "unknown", "gw_ms": None}
    try:
        with open("/proc/net/route", "r") as f:
            for line in f.read().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    out["iface"] = parts[0]
                    h = parts[2]
                    if len(h) == 8:
                        try:
                            out["gw"] = ".".join(
                                str(int(h[i:i + 2], 16)) for i in (6, 4, 2, 0))
                        except Exception:
                            pass
                    break
    except Exception:
        pass
    iface = out["iface"]
    if iface:
        try:
            oper = f"/sys/class/net/{iface}/operstate"
            if os.path.isfile(oper):
                out["link"] = open(oper, encoding="ascii").read().strip()
        except Exception:
            pass
    try:
        import subprocess
        gw = str(out.get("gw") or "")
        if not gw:
            return out
        r = subprocess.run(
            ["ping", "-c", "1", "-W", "1", gw],
            capture_output=True, timeout=3, check=False,
        )
        if r.returncode == 0:
            txt = (r.stdout or b"").decode("utf-8", errors="ignore")
            for tok in txt.replace("=", " ").split():
                if tok.endswith("ms") and tok[:-2].replace(".", "").isdigit():
                    out["gw_ms"] = float(tok[:-2])
                    break
    except Exception:
        pass
    return out


class HealthReporter:
    """Pubblica periodicamente lo stato del sistema su MQTT."""

    def __init__(
        self,
        mqtt_publish: Callable[[str, str, bool], Any],
        topic: str = "videocitofono/health",
        interval_sec: float = 30.0,
        version: str = "",
        get_screen: Optional[Callable[[], str]] = None,
        get_camera_status: Optional[Callable[[], str]] = None,
        get_engine_face: Optional[Callable[[], str]] = None,
        get_subsystems: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        self._publish = mqtt_publish
        self.topic = topic
        self.interval = max(5.0, float(interval_sec))
        self.version = version or "dev"
        self._get_screen = get_screen or (lambda: "")
        self._get_camera_status = get_camera_status or (lambda: "unknown")
        self._get_engine_face = get_engine_face or (lambda: "")
        self._get_subsystems = get_subsystems or (lambda: {})
        self._stop = threading.Event()
        self._th: Optional[threading.Thread] = None
        self._cpu_prev: Dict[str, int] = {"idle": 0, "total": 0}
        # Eventi e contatori esterni
        self.last_face_match_ts: Optional[float] = None
        self.last_open_ts: Optional[float] = None
        self.errors_last_hour = 0
        self._error_buf = []  # lista di timestamp errori, finestra mobile 1h

    def mark_face_match(self) -> None:
        self.last_face_match_ts = time.time()

    def mark_open(self) -> None:
        self.last_open_ts = time.time()

    def mark_error(self) -> None:
        now = time.time()
        self._error_buf.append(now)
        cutoff = now - 3600
        self._error_buf = [t for t in self._error_buf if t >= cutoff]
        self.errors_last_hour = len(self._error_buf)

    def start(self) -> None:
        if self._th and self._th.is_alive():
            return
        self._th = threading.Thread(target=self._loop, name="health", daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> Dict[str, Any]:
        # finestra rolling 1h sugli errori
        now = time.time()
        cutoff = now - 3600
        self._error_buf = [t for t in self._error_buf if t >= cutoff]
        self.errors_last_hour = len(self._error_buf)
        subs = self._get_subsystems() or {}
        payload = {
            "ts": int(now),
            "uptime_sec": int(now - _BOOT_TS),
            "cpu_pct": round(_cpu_pct(self._cpu_prev), 1),
            "mem_pct": round(_mem_pct(), 1),
            "disk_pct": round(_disk_pct("/"), 1),
            "temp_c": (round(_read_cpu_temp(), 1) if _read_cpu_temp() is not None else None),
            "load1": round(_load1(), 2),
            "version": self.version,
            "screen": self._get_screen(),
            "camera_status": self._get_camera_status(),
            "engine_face": self._get_engine_face(),
            "last_face_match_ts": (int(self.last_face_match_ts) if self.last_face_match_ts else None),
            "last_open_ts": (int(self.last_open_ts) if self.last_open_ts else None),
            "errors_last_hour": self.errors_last_hour,
        }
        net = _network_info()
        payload["net_iface"] = net.get("iface", "")
        payload["net_link"] = net.get("link", "")
        if net.get("gw_ms") is not None:
            payload["net_gw_ms"] = net["gw_ms"]
        if isinstance(subs, dict):
            payload.update(subs)
        oc = usb_overcurrent_count()
        payload["usb_overcurrent"] = oc
        payload["usb_overcurrent_status"] = "warn" if oc else "ok"
        return payload

    def _loop(self) -> None:
        # warmup CPU stats (la prima lettura ritorna 0.0)
        _cpu_pct(self._cpu_prev)
        while not self._stop.is_set():
            try:
                payload = self.snapshot()
                self._publish(self.topic, json.dumps(payload), True)
            except Exception as e:
                LOG.debug("health publish err: %s", e)
            self._stop.wait(self.interval)
