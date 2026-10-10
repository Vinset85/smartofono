"""Logging strutturato JSON con rotazione su file.

Mantiene anche il logging testuale verso stdout (catturato da systemd/journald)
per non perdere la timeline canonica nel `journalctl`. Aggiunge in piu' un
RotatingFileHandler che scrive su /opt/videocitofono/logs/videocitofono.log
in formato JSON, una riga per record. Utile per:
  - audit / forensics (chi ha aperto cosa, errori riconoscimento, ecc.)
  - import in ELK / Loki / Grafana
  - debug post-mortem

Configurazione via config.yaml:
    logging:
      enabled: true
      level: INFO
      dir: /opt/videocitofono/logs
      filename: videocitofono.log
      max_bytes: 5_000_000
      backup_count: 7
      json: true
      console: true            # mantiene stdout per journald
      console_level: INFO

Uso:
    from modules.log_setup import setup_logging
    setup_logging(cfg.get("logging", {}))
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import socket
import sys
import time
from typing import Any, Dict, Optional


HOSTNAME = socket.gethostname()


class JsonFormatter(logging.Formatter):
    """Formatta ogni record come riga JSON serializzabile.

    Campi standard:
        ts        ISO8601 UTC
        level     INFO/WARNING/ERROR/...
        logger    nome del logger
        msg       messaggio formattato
        module    file py
        line      numero riga
        host      hostname
        thread    nome thread
        exc       (opzionale) traceback
    Campi extra: tutti i kwargs aggiunti via `logger.info("x", extra={...})`
    o via `logger.bind()` (compat con structlog) sono inclusi.
    """

    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
            "host": HOSTNAME,
            "thread": record.threadName,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Extra fields (non riservati) — utile per `audit_event=...` ecc.
        for k, v in record.__dict__.items():
            if k in self._RESERVED or k.startswith("_"):
                continue
            try:
                json.dumps(v)
            except (TypeError, ValueError):
                v = repr(v)
            payload[k] = v
        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            return json.dumps({
                "ts": payload["ts"],
                "level": payload["level"],
                "logger": payload["logger"],
                "msg": str(record.getMessage()),
            })


_DEFAULT_NOISY = (
    "aiortc", "aiortc.rtcrtpreceiver", "aiortc.rtcrtpsender",
    "aiortc.rtcdtlstransport", "aiortc.rtcicetransport",
    "aiortc.rtcsctptransport",
    "aioice", "aioice.ice", "aioice.stun", "aioice.turn",
    "livekit", "livekit.rtc", "livekit.rtc._proto",
    "livekit.rtc.room", "livekit.rtc.rtc",
)


def setup_logging(cfg: Optional[Dict[str, Any]] = None) -> logging.Logger:
    cfg = cfg or {}
    if not cfg.get("enabled", True):
        return logging.getLogger("videocitofono")

    level = getattr(logging, str(cfg.get("level", "INFO")).upper(), logging.INFO)
    log_dir = str(cfg.get("dir", "/opt/videocitofono/logs"))
    filename = str(cfg.get("filename", "videocitofono.log"))
    max_bytes = int(cfg.get("max_bytes", 5_000_000))
    backup_count = int(cfg.get("backup_count", 7))
    use_json = bool(cfg.get("json", True))
    console = bool(cfg.get("console", True))
    console_level = getattr(logging, str(cfg.get("console_level", "INFO")).upper(), level)

    root = logging.getLogger()
    root.setLevel(level)
    # Pulisce handler esistenti per evitare duplicati al riavvio
    for h in list(root.handlers):
        root.removeHandler(h)

    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(console_level)
        ch.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(ch)

    fh: Optional[logging.Handler] = None
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, filename)
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(JsonFormatter() if use_json else logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(fh)
    except Exception as e:
        root.warning("log_setup: impossibile scrivere su %s (%s)", log_dir, e)

    for noisy in _DEFAULT_NOISY:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    log = logging.getLogger("videocitofono")
    log.info("logging configurato",
             extra={
                 "audit_event": "log_setup",
                 "log_dir": log_dir,
                 "level": logging.getLevelName(level),
                 "json": use_json,
                 "rotate_max_mb": max_bytes / 1_000_000,
                 "backup_count": backup_count,
             })
    return log


def audit(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emette un record di livello INFO con `audit_event=<event>` e
    altri campi strutturati (es. user, method, scope, success).

    Esempio:
        audit(LOG, "door_open", user="stefania", method="face",
              scope="porta", success=True, distance=0.41)
    """
    logger.info("[audit] %s", event,
                extra={"audit_event": event, **fields})
