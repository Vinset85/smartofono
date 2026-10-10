"""Anomaly detection sugli orari di apertura.

Usa una distribuzione storica (oraria, ultimi N giorni) per stimare la
probabilita' di un'apertura in un dato slot orario per un dato utente.
Se la probabilita' osservata (count_user_hour / count_user_total) e'
sotto una soglia o se l'ora e' al di fuori del range tipico (z-score >
threshold), pubblica un evento `videocitofono/anomaly`.

Approccio semplice e on-device, niente ML pesante: ottimo per dataset
piccoli (10-50 aperture/utente).
"""
from __future__ import annotations

import json
import logging
import math
import time
from typing import Any, Dict, List, Optional


LOG = logging.getLogger(__name__)


class AnomalyDetector:
    def __init__(self, audit_db,
                 mqtt_publish=None,
                 window_days: int = 60,
                 z_threshold: float = 2.5,
                 min_samples: int = 15) -> None:
        self.db = audit_db
        self.mqtt_publish = mqtt_publish
        self.window_days = int(window_days)
        self.z_threshold = float(z_threshold)
        self.min_samples = int(min_samples)

    def _user_open_hours(self, user: str) -> List[int]:
        """Ritorna lista degli hour-of-day di tutte le aperture di `user`."""
        try:
            since = int(time.time() - self.window_days * 86400)
            with self.db._cursor() as cur:
                cur.execute(
                    "SELECT strftime('%H', ts, 'unixepoch', 'localtime') "
                    "FROM events "
                    "WHERE kind='open' AND success=1 AND user=? AND ts >= ?",
                    (user, since),
                )
                return [int(r[0]) for r in cur.fetchall()]
        except Exception as e:
            LOG.debug("user_open_hours err: %s", e)
            return []

    def evaluate(self, user: str,
                 hour: Optional[int] = None) -> Dict[str, Any]:
        """Ritorna dict con `is_anomaly`, `z`, `samples` per la (user,hour)."""
        if hour is None:
            hour = time.localtime().tm_hour
        hours = self._user_open_hours(user)
        n = len(hours)
        if n < self.min_samples:
            return {
                "is_anomaly": False,
                "reason": "not_enough_samples",
                "samples": n,
            }
        # Calcolo media/std circolare semplificato: trasformo h in
        # vettori (cos,sin) e calcolo distanza all'ora corrente.
        thetas = [(2 * math.pi * h / 24.0) for h in hours]
        cur_theta = 2 * math.pi * hour / 24.0
        # Distanza angolare (circolare).
        dists = [min(abs(t - cur_theta), 2 * math.pi - abs(t - cur_theta)) for t in thetas]
        mean = sum(dists) / n
        var = sum((d - mean) ** 2 for d in dists) / n
        std = math.sqrt(var) if var > 0 else 1e-6
        # z-score sulla distanza minima (ora corrente vs distribuzione).
        # Una distanza piccola = ora frequente; grande = ora raro.
        # Per "anomalia" guardiamo se la distanza tipica e' lontana dal
        # presente: se mean >> 0.5 (rad ~30°) -> ora rara.
        # z-score: quanto l'ora corrente e' lontana dalla distribuzione tipica.
        cur_dist = min(dists) if dists else 0.0
        z = (cur_dist - mean) / std if std > 1e-9 else 0.0
        # Semplifico: probabilita' = frazione di aperture entro ±1h.
        nearby = sum(1 for h in hours if abs(((h - hour + 12) % 24) - 12) <= 1)
        prob = nearby / n
        is_anom = prob < 0.05 and z > self.z_threshold
        return {
            "is_anomaly": bool(is_anom),
            "reason": "rare_hour" if is_anom else "normal",
            "samples": n,
            "prob_window": round(prob, 3),
            "z": round(z, 3),
            "hour": hour,
        }

    def maybe_emit(self, user: str, hour: Optional[int] = None) -> None:
        if not self.mqtt_publish:
            return
        try:
            r = self.evaluate(user, hour)
            if not r.get("is_anomaly"):
                return
            payload = {"user": user, "ts": int(time.time()), **r}
            self.mqtt_publish("videocitofono/anomaly",
                              json.dumps(payload), False)
            LOG.info("anomaly: user=%s hour=%s prob=%.3f",
                     user, r["hour"], r["prob_window"])
        except Exception as e:
            LOG.debug("anomaly emit err: %s", e)
