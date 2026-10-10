"""Gestione PIN ospite con scadenza e numero massimo di usi.

Persistenza: file JSON in `data/guest_pins.json`. Ogni record:
    {
        "code_hash": "<bcrypt>",
        "created_ts": 1746400000,
        "expires_ts": 1746500000,
        "max_uses": 5,
        "uses": 1,
        "label": "Pizza domenica sera",
        "scope": "porta",
        "active": true
    }

API:
    GuestPinManager.create(label, valid_hours, max_uses, scope) -> (id, plain_pin)
    GuestPinManager.try_match(plain_pin) -> dict | None
    GuestPinManager.list() -> [dict, ...]
    GuestPinManager.revoke(id_) -> bool
    GuestPinManager.purge_expired() -> int

I PIN ospite sono distinti dai PIN normali: hanno l'attributo
`apre` configurabile e `metodo_label` = "guest" nei log MQTT.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import string
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


LOG = logging.getLogger(__name__)


def _hash_pin(pin: str) -> str:
    """Hash bcrypt se disponibile, altrimenti SHA256 (compat)."""
    try:
        import bcrypt
        return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")
    except Exception:
        return "sha256$" + hashlib.sha256(pin.encode("utf-8")).hexdigest()


def _verify_pin(pin: str, h: str) -> bool:
    if not h:
        return False
    if h.startswith("sha256$"):
        return hashlib.sha256(pin.encode("utf-8")).hexdigest() == h[len("sha256$"):]
    try:
        import bcrypt
        return bcrypt.checkpw(pin.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False


def _gen_pin(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _gen_id() -> str:
    return secrets.token_urlsafe(8)


class GuestPinManager:
    def __init__(self, path: str = "data/guest_pins.json",
                 length: int = 6) -> None:
        self.path = path
        self.length = max(4, min(8, int(length)))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = threading.RLock()
        self._records: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _save(self) -> None:
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            LOG.warning("guest_pin save err: %s", e)

    # ---- API ------------------------------------------------------------

    def create(self, label: str = "",
               valid_hours: float = 24.0,
               max_uses: int = 1,
               scope: str = "porta",
               pin_length: Optional[int] = None) -> Tuple[str, str]:
        pin = _gen_pin(int(pin_length or self.length))
        rec_id = _gen_id()
        rec = {
            "code_hash": _hash_pin(pin),
            "created_ts": int(time.time()),
            "expires_ts": int(time.time() + max(0.0, valid_hours * 3600)),
            "max_uses": max(1, int(max_uses)),
            "uses": 0,
            "label": str(label or "")[:64],
            "scope": scope if scope in ("porta", "cancello") else "porta",
            "active": True,
        }
        with self._lock:
            self._records[rec_id] = rec
            self._save()
        LOG.info("guest_pin creato id=%s label=%r expires=%s uses=0/%d",
                 rec_id, rec["label"], rec["expires_ts"], rec["max_uses"])
        return rec_id, pin

    def revoke(self, rec_id: str) -> bool:
        with self._lock:
            if rec_id not in self._records:
                return False
            self._records[rec_id]["active"] = False
            self._save()
            return True

    def delete(self, rec_id: str) -> bool:
        with self._lock:
            if rec_id not in self._records:
                return False
            del self._records[rec_id]
            self._save()
            return True

    def purge_expired(self) -> int:
        now = int(time.time())
        n = 0
        with self._lock:
            for k in list(self._records.keys()):
                r = self._records[k]
                if (not r.get("active") or
                        r.get("expires_ts", 0) < now or
                        r.get("uses", 0) >= r.get("max_uses", 1)):
                    n += 1
                    # Mantengo storicamente ma flag inattivo
                    r["active"] = False
            self._save()
        return n

    def list(self, include_inactive: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            out: List[Dict[str, Any]] = []
            for rid, r in self._records.items():
                if not include_inactive and not r.get("active", True):
                    continue
                out.append({
                    "id": rid,
                    "created_ts": r.get("created_ts", 0),
                    "expires_ts": r.get("expires_ts", 0),
                    "max_uses": r.get("max_uses", 1),
                    "uses": r.get("uses", 0),
                    "label": r.get("label", ""),
                    "scope": r.get("scope", "porta"),
                    "active": bool(r.get("active", True)),
                })
            return out

    def try_match(self, pin: str,
                  consume: bool = True) -> Optional[Dict[str, Any]]:
        """Cerca un PIN ospite che corrisponde. Se trova match valido
        (attivo, non scaduto, sotto max_uses) e consume=True, incrementa
        `uses` e ritorna il record. Altrimenti None."""
        if not pin:
            return None
        now = int(time.time())
        with self._lock:
            for rid, r in self._records.items():
                if not r.get("active", True):
                    continue
                if r.get("expires_ts", 0) < now:
                    continue
                if r.get("uses", 0) >= r.get("max_uses", 1):
                    continue
                if _verify_pin(pin, r.get("code_hash", "")):
                    if consume:
                        r["uses"] = r.get("uses", 0) + 1
                        if r["uses"] >= r.get("max_uses", 1):
                            r["active"] = False
                        self._save()
                    return {
                        "id": rid,
                        "label": r.get("label", ""),
                        "scope": r.get("scope", "porta"),
                        "uses": r.get("uses", 0),
                        "max_uses": r.get("max_uses", 1),
                        "expires_ts": r.get("expires_ts", 0),
                    }
        return None
