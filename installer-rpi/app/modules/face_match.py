"""Logica matching condivisa: aggregazione per-utente, margin, borderline."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def user_min_distances(dists: List[float], labels: List[str]) -> Dict[str, float]:
    """Min distanza per utente (non per singola foto)."""
    out: Dict[str, float] = {}
    for d, name in zip(dists, labels):
        cur = out.get(name)
        if cur is None or d < cur:
            out[name] = float(d)
    return out


def decide_match(
    user_dists: Dict[str, float],
    threshold: float,
    margin: float,
    *,
    borderline_ratio: float = 0.85,
) -> Optional[Dict[str, Any]]:
    """Decide match con soglia assoluta + margin tra 1° e 2° candidato."""
    if not user_dists:
        return None
    ranked = sorted(user_dists.items(), key=lambda x: x[1])
    best_user, best_dist = ranked[0]
    second_user, second_dist = (
        ranked[1] if len(ranked) > 1 else (None, float("inf"))
    )
    margin_actual = second_dist - best_dist
    borderline = best_dist > threshold * borderline_ratio or (
        len(ranked) > 1 and margin_actual < margin * 1.5
    )
    base: Dict[str, Any] = {
        "distance": best_dist,
        "best_user": best_user,
        "second_user": second_user,
        "second_distance": second_dist if second_user else None,
        "margin": margin_actual,
        "borderline": borderline,
    }
    if best_dist > threshold:
        return {"match": False, "reject_reason": "threshold", **base}
    if len(ranked) > 1 and margin_actual < margin:
        return {"match": False, "reject_reason": "margin", **base}
    return {"match": True, "nome": best_user, **base}
