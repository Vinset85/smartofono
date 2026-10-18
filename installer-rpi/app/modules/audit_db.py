"""SQLite locale per audit trail, volti sconosciuti, statistiche orarie.

Schema:
    events
        id INTEGER PRIMARY KEY
        ts INTEGER NOT NULL          (epoch s)
        kind TEXT NOT NULL           (open | open_fail | face_match
                                       | face_unknown | pin_fail
                                       | error | guest_used | guest_expired)
        method TEXT                  (face | pin | nfc | remote | guest)
        user TEXT                    (nome utente o 'unknown')
        scope TEXT                   (porta | cancello | -)
        success INTEGER              (0/1)
        meta TEXT                    (JSON con dettagli arbitrari)

    unknowns
        face_id TEXT PRIMARY KEY     (hash dell'encoding o thumb path)
        first_seen INTEGER
        last_seen INTEGER
        count INTEGER
        thumb_path TEXT              (path opzionale a immagine miniatura)

L'append e' append-only e idempotente. Il file db sta in
`<root>/data/audit.sqlite` e viene incluso nel backup.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple


LOG = logging.getLogger(__name__)


_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL,
    method TEXT,
    user TEXT,
    scope TEXT,
    success INTEGER DEFAULT 1,
    meta TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user);

CREATE TABLE IF NOT EXISTS unknowns (
    face_id TEXT PRIMARY KEY,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    thumb_path TEXT
);
"""


class AuditDB:
    """Wrapper sqlite3 thread-safe con lock interno."""

    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
        with self._conn:
            self._conn.executescript(_SCHEMA)

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            finally:
                cur.close()

    # ---- Eventi ---------------------------------------------------------

    def add_event(self, kind: str, *,
                  method: str = "",
                  user: str = "",
                  scope: str = "",
                  success: bool = True,
                  meta: Optional[Dict[str, Any]] = None,
                  ts: Optional[int] = None) -> int:
        ts = int(ts or time.time())
        meta_s = json.dumps(meta, ensure_ascii=False) if meta else None
        try:
            with self._cursor() as cur:
                cur.execute(
                    "INSERT INTO events (ts,kind,method,user,scope,success,meta) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (ts, kind, method, user, scope,
                     1 if success else 0, meta_s),
                )
                return int(cur.lastrowid or 0)
        except Exception as e:
            LOG.warning("audit add_event err: %s", e)
            return 0

    def recent_events(self, limit: int = 50,
                      kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        try:
            q = ("SELECT id,ts,kind,method,user,scope,success,meta "
                 "FROM events")
            args: Tuple[Any, ...] = ()
            if kinds:
                q += " WHERE kind IN (" + ",".join(["?"] * len(kinds)) + ")"
                args = tuple(kinds)
            q += " ORDER BY id DESC LIMIT ?"
            args = args + (int(limit),)
            with self._cursor() as cur:
                cur.execute(q, args)
                rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                out.append({
                    "id": r[0], "ts": r[1], "kind": r[2], "method": r[3],
                    "user": r[4], "scope": r[5],
                    "success": bool(r[6]),
                    "meta": (json.loads(r[7]) if r[7] else None),
                })
            return out
        except Exception as e:
            LOG.warning("audit recent_events err: %s", e)
            return []

    def hourly_open_stats(self, days: int = 30) -> List[Tuple[int, int]]:
        """Ritorna lista (hour 0-23, count) sugli ultimi `days` giorni."""
        since = int(time.time() - days * 86400)
        try:
            with self._cursor() as cur:
                cur.execute(
                    "SELECT strftime('%H', ts, 'unixepoch', 'localtime') AS h, "
                    "COUNT(*) FROM events "
                    "WHERE kind='open' AND success=1 AND ts >= ? GROUP BY h",
                    (since,),
                )
                rows = cur.fetchall()
            return [(int(r[0]), int(r[1])) for r in rows]
        except Exception as e:
            LOG.warning("hourly stats err: %s", e)
            return []

    # ---- Unknowns -------------------------------------------------------

    def upsert_unknown(self, face_id: str,
                       thumb_path: str = "") -> Tuple[int, bool]:
        """Inserisce o aggiorna un volto sconosciuto.
        Ritorna (count_after, is_new)."""
        now = int(time.time())
        try:
            with self._cursor() as cur:
                cur.execute(
                    "SELECT count FROM unknowns WHERE face_id=?", (face_id,))
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        "INSERT INTO unknowns (face_id,first_seen,last_seen,count,thumb_path) "
                        "VALUES (?,?,?,1,?)",
                        (face_id, now, now, thumb_path),
                    )
                    return 1, True
                count = int(row[0]) + 1
                cur.execute(
                    "UPDATE unknowns SET last_seen=?, count=?, "
                    "thumb_path=COALESCE(NULLIF(?,''), thumb_path) "
                    "WHERE face_id=?",
                    (now, count, thumb_path, face_id),
                )
                return count, False
        except Exception as e:
            LOG.warning("upsert_unknown err: %s", e)
            return 0, False

    def list_unknowns(self, min_count: int = 1,
                      limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with self._cursor() as cur:
                cur.execute(
                    "SELECT face_id,first_seen,last_seen,count,thumb_path "
                    "FROM unknowns WHERE count >= ? "
                    "ORDER BY count DESC, last_seen DESC LIMIT ?",
                    (int(min_count), int(limit)),
                )
                rows = cur.fetchall()
            return [{
                "face_id": r[0], "first_seen": r[1], "last_seen": r[2],
                "count": r[3], "thumb_path": r[4],
            } for r in rows]
        except Exception as e:
            LOG.warning("list_unknowns err: %s", e)
            return []

    def remove_unknown(self, face_id: str) -> bool:
        try:
            with self._cursor() as cur:
                cur.execute("DELETE FROM unknowns WHERE face_id=?", (face_id,))
                return cur.rowcount > 0
        except Exception as e:
            LOG.warning("remove_unknown err: %s", e)
            return False

    def close(self) -> None:
        try:
            with self._lock:
                self._conn.close()
        except Exception:
            pass
