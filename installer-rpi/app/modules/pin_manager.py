"""Gestione PIN utenti con hash bcrypt e lockout dopo N tentativi falliti."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import bcrypt

from .config import data_path

LOG = logging.getLogger(__name__)

USERS_FILE = data_path("users.json")


def _load_users() -> List[Dict[str, Any]]:
    if not USERS_FILE.exists():
        return []
    try:
        return json.loads(USERS_FILE.read_text())
    except Exception as e:
        LOG.error("Errore lettura users.json: %s", e)
        return []


def _save_users(data: List[Dict[str, Any]]) -> None:
    USERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    LOG.info("users.json salvato (%d utenti)", len(data))


def bootstrap_users(cfg_pin: Dict[str, Any]) -> None:
    """Al primo avvio crea users.json hashando i PIN da config.utenti_bootstrap."""
    if USERS_FILE.exists():
        return
    bootstrap = cfg_pin.get("utenti_bootstrap", [])
    if not bootstrap:
        return
    out = []
    for u in bootstrap:
        pin_hash = bcrypt.hashpw(str(u["pin"]).encode(), bcrypt.gensalt()).decode()
        out.append({
            "nome": u["nome"],
            "pin_hash": pin_hash,
            "ruolo": u.get("ruolo", "utente"),
            "apre": u.get("apre", "porta"),
            "creato_at": time.time(),
        })
    _save_users(out)
    LOG.info("Bootstrap utenti completato: %d utenti", len(out))


class PinManager:
    """Verifica PIN + lockout incrementale."""

    def __init__(self, cfg_pin: Dict[str, Any]):
        self.cfg = cfg_pin
        self._failed_attempts = 0
        self._lockout_until = 0.0

    @property
    def in_lockout(self) -> bool:
        return time.time() < self._lockout_until

    @property
    def lockout_remaining(self) -> int:
        return max(0, int(self._lockout_until - time.time()))

    def verify(self, pin: str) -> Optional[Dict[str, Any]]:
        """Restituisce dict utente se PIN valido, None altrimenti.
        Solleva PermissionError se in lockout."""
        if self.in_lockout:
            raise PermissionError(f"Lockout attivo per {self.lockout_remaining}s")
        if not pin or len(pin) < self.cfg.get("lunghezza_min", 4):
            self._registra_fallimento()
            return None
        users = _load_users()
        for u in users:
            try:
                if bcrypt.checkpw(pin.encode(), u["pin_hash"].encode()):
                    self._failed_attempts = 0
                    LOG.info("PIN valido per utente: %s", u["nome"])
                    return u
            except Exception as e:
                LOG.warning("Errore checkpw: %s", e)
        self._registra_fallimento()
        return None

    def try_match(self, pin: str) -> Optional[Dict[str, Any]]:
        """Tentativo di match silenzioso (no registrazione fallimenti).
        Usato dall'auto-verifica del tastierino: ad ogni cifra si invoca
        try_match e si apre la porta non appena il PIN diventa valido,
        senza incrementare il contatore tentativi finche' l'utente non
        ha completato l'inserimento (chiama poi `register_failure()`).
        """
        if self.in_lockout:
            raise PermissionError(f"Lockout attivo per {self.lockout_remaining}s")
        if not pin or len(pin) < self.cfg.get("lunghezza_min", 4):
            return None
        users = _load_users()
        for u in users:
            try:
                if bcrypt.checkpw(pin.encode(), u["pin_hash"].encode()):
                    self._failed_attempts = 0
                    return u
            except Exception as e:
                LOG.warning("Errore checkpw: %s", e)
        return None

    def register_failure(self) -> None:
        """Registra un fallimento (per uso esplicito da chi usa try_match)."""
        self._registra_fallimento()

    def _registra_fallimento(self) -> None:
        self._failed_attempts += 1
        max_t = self.cfg.get("max_tentativi", 5)
        if self._failed_attempts >= max_t:
            secs = self.cfg.get("lockout_secondi", 300)
            self._lockout_until = time.time() + secs
            self._failed_attempts = 0
            LOG.warning("Lockout PIN attivato per %ds", secs)

    def aggiungi_utente(self, nome: str, pin: str, ruolo: str = "utente", apre: str = "porta") -> None:
        users = _load_users()
        pin_hash = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()
        users.append({
            "nome": nome,
            "pin_hash": pin_hash,
            "ruolo": ruolo,
            "apre": apre,
            "creato_at": time.time(),
        })
        _save_users(users)

    def elenco_utenti(self) -> List[Dict[str, Any]]:
        return [
            {k: v for k, v in u.items() if k != "pin_hash"}
            for u in _load_users()
        ]

    def rimuovi_utente(self, nome: str) -> bool:
        users = _load_users()
        new = [u for u in users if u["nome"] != nome]
        if len(new) != len(users):
            _save_users(new)
            return True
        return False

    def has_user(self, nome: str) -> bool:
        """True se esiste un record utente non-admin con quel nome."""
        if not nome:
            return False
        for u in _load_users():
            if u.get("nome") == nome and u.get("ruolo") != "admin":
                return True
        return False

    def set_user_pin(self, nome: str, pin: str, genere: Optional[str] = None,
                     apre: str = "porta") -> Dict[str, Any]:
        """Crea/aggiorna un utente non-admin con il PIN dato.
        Se l'utente esiste viene aggiornato (pin + genere + apre).
        Ritorna dict {ok, msg}.
        """
        if not nome:
            return {"ok": False, "msg": "Nome mancante"}
        if not pin or not pin.isdigit() or not (4 <= len(pin) <= 8):
            return {"ok": False, "msg": "PIN: 4-8 cifre numeriche"}
        users = _load_users()
        # Verifica che il PIN non sia gia' usato da un altro utente.
        try:
            for u in users:
                if u.get("nome") == nome:
                    continue
                if bcrypt.checkpw(pin.encode(), u["pin_hash"].encode()):
                    return {"ok": False,
                            "msg": "PIN gia' associato a un altro utente"}
        except Exception:
            pass
        pin_hash = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()
        found = False
        for u in users:
            if u.get("nome") == nome and u.get("ruolo") != "admin":
                u["pin_hash"] = pin_hash
                u["aggiornato_at"] = time.time()
                if genere is not None:
                    u["genere"] = genere
                if apre is not None:
                    u["apre"] = apre
                found = True
                break
        if not found:
            entry = {
                "nome": nome,
                "pin_hash": pin_hash,
                "ruolo": "utente",
                "apre": apre or "porta",
                "creato_at": time.time(),
            }
            if genere:
                entry["genere"] = genere
            users.append(entry)
        _save_users(users)
        return {"ok": True, "msg": "Aggiornato" if found else "Creato"}

    def clear_user_pin(self, nome: str) -> bool:
        """Rimuove l'utente non-admin con quel nome (cosi' il PIN non
        funziona piu'). Lascia l'admin intatto."""
        if not nome:
            return False
        users = _load_users()
        new = [u for u in users
               if not (u.get("nome") == nome and u.get("ruolo") != "admin")]
        if len(new) == len(users):
            return False
        _save_users(new)
        return True

    def update_user_meta(self, nome: str, *, nuovo_nome: Optional[str] = None,
                         genere: Optional[str] = None,
                         apre: Optional[str] = None) -> bool:
        """Aggiorna i metadati di un utente non-admin esistente. Se
        l'utente non esiste e nessun PIN e' impostato, no-op (ritorna
        False). Usato per propagare rename/cambio genere dai volti."""
        if not nome:
            return False
        users = _load_users()
        changed = False
        for u in users:
            if u.get("nome") == nome and u.get("ruolo") != "admin":
                if nuovo_nome and nuovo_nome != nome:
                    u["nome"] = nuovo_nome
                    changed = True
                if genere is not None and u.get("genere") != genere:
                    u["genere"] = genere
                    changed = True
                if apre is not None and u.get("apre") != apre:
                    u["apre"] = apre
                    changed = True
                if changed:
                    u["aggiornato_at"] = time.time()
                break
        if changed:
            _save_users(users)
        return changed

    def set_admin_pin(self, pin: str) -> None:
        """Crea/aggiorna l'utente 'admin' con il nuovo PIN. Apre porta+cancello."""
        if not pin or not pin.isdigit() or not (4 <= len(pin) <= 8):
            raise ValueError("PIN admin: 4-8 cifre")
        users = _load_users()
        pin_hash = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()
        found = False
        for u in users:
            if u.get("ruolo") == "admin" or u.get("nome") == "admin":
                u["pin_hash"] = pin_hash
                u["aggiornato_at"] = time.time()
                found = True
                break
        if not found:
            users.append({
                "nome": "admin",
                "pin_hash": pin_hash,
                "ruolo": "admin",
                "apre": "tutto",
                "creato_at": time.time(),
            })
        _save_users(users)
        LOG.info("Admin PIN aggiornato (utenti totali=%d)", len(users))
