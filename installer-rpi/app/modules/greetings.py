"""Costruzione di saluti vocali variabili.

Il messaggio cambia in base a:
  - fascia oraria (mattina, pomeriggio, sera, notte)
  - sesso ("M" / "F" / non specificato)

Per ogni combinazione esiste un set di varianti, scelte a caso, in modo
che lo stesso utente non senta sempre la stessa frase.

Uso:
    from modules.greetings import build_greeting
    saluto = build_greeting("Stefania", "F")
"""
from __future__ import annotations

import datetime as _dt
import random
from typing import List, Optional


def _time_slot(now: Optional[_dt.datetime] = None) -> str:
    """Ritorna 'mattina' | 'pomeriggio' | 'sera' | 'notte'."""
    if now is None:
        now = _dt.datetime.now()
    h = now.hour
    if 5 <= h < 12:
        return "mattina"
    if 12 <= h < 18:
        return "pomeriggio"
    if 18 <= h < 23:
        return "sera"
    return "notte"


def _norm_gender(g: Optional[str]) -> str:
    g = (g or "").strip().upper()
    if g in ("M", "MASCHIO", "MALE", "U"):
        return "M"
    if g in ("F", "FEMMINA", "FEMALE", "D"):
        return "F"
    return ""


# Per ogni combinazione (slot, gender) un elenco di template.
# {nome} viene sostituito con il nome dell'utente (o stringa vuota).
# Ogni frase conferma esplicitamente l'apertura, perche' l'utente vuole
# sentirlo dire. Nessuna usa "la porta è aperta": la voce neurale schiaccia
# quella "è" fra due vocali e all'ascolto si sente "la porta aperta". Le
# formule scelte ("porta aperta", "ti apro la porta") non hanno il problema.
_TEMPLATES = {
    ("mattina", "F"): [
        "Buongiorno {nome}, porta aperta",
        "Buongiorno {nome}, entra pure, ti apro la porta",
        "Buongiorno {nome}, bentornata a casa, porta aperta",
        "Ciao {nome}, buongiorno, ti apro la porta",
    ],
    ("mattina", "M"): [
        "Buongiorno {nome}, porta aperta",
        "Buongiorno {nome}, entra pure, ti apro la porta",
        "Buongiorno {nome}, bentornato a casa, porta aperta",
        "Ciao {nome}, buongiorno, ti apro la porta",
    ],
    ("mattina", ""): [
        "Buongiorno {nome}, porta aperta",
        "Buongiorno {nome}, entra pure, ti apro la porta",
        "Ciao {nome}, buongiorno, ti apro la porta",
    ],
    ("pomeriggio", "F"): [
        "Buon pomeriggio {nome}, porta aperta",
        "Buon pomeriggio {nome}, entra pure, ti apro la porta",
        "Ciao {nome}, bentornata, porta aperta",
        "Buon pomeriggio {nome}, bentornata a casa, porta aperta",
    ],
    ("pomeriggio", "M"): [
        "Buon pomeriggio {nome}, porta aperta",
        "Buon pomeriggio {nome}, entra pure, ti apro la porta",
        "Ciao {nome}, bentornato, porta aperta",
        "Buon pomeriggio {nome}, bentornato a casa, porta aperta",
    ],
    ("pomeriggio", ""): [
        "Buon pomeriggio {nome}, porta aperta",
        "Ciao {nome}, entra pure, ti apro la porta",
    ],
    ("sera", "F"): [
        "Buonasera {nome}, porta aperta",
        "Buonasera {nome}, bentornata a casa, porta aperta",
        "Buonasera {nome}, entra pure, ti apro la porta",
        "Ciao {nome}, buonasera, ti apro la porta",
    ],
    ("sera", "M"): [
        "Buonasera {nome}, porta aperta",
        "Buonasera {nome}, bentornato a casa, porta aperta",
        "Buonasera {nome}, entra pure, ti apro la porta",
        "Ciao {nome}, buonasera, ti apro la porta",
    ],
    ("sera", ""): [
        "Buonasera {nome}, porta aperta",
        "Buonasera {nome}, entra pure, ti apro la porta",
    ],
    ("notte", "F"): [
        "Buonanotte {nome}, porta aperta",
        "Ciao {nome}, bentornata, ti apro la porta",
        "Eccoti {nome}, porta aperta",
    ],
    ("notte", "M"): [
        "Buonanotte {nome}, porta aperta",
        "Ciao {nome}, bentornato, ti apro la porta",
        "Eccoti {nome}, porta aperta",
    ],
    ("notte", ""): [
        "Buonanotte {nome}, porta aperta",
        "Ciao {nome}, ti apro la porta",
    ],
}


def build_greeting(nome: str, genere: str = "",
                   now: Optional[_dt.datetime] = None) -> str:
    """Genera una frase di saluto variabile.

    Args:
        nome: nome dell'utente. Se vuoto/None, viene rimosso dal template.
        genere: 'M' | 'F' | '' (sconosciuto).
        now: opzionale per test, datetime di riferimento.
    """
    nome = (nome or "").strip()
    g = _norm_gender(genere)
    slot = _time_slot(now)

    templates: List[str] = _TEMPLATES.get((slot, g)) or _TEMPLATES.get((slot, ""), [])
    if not templates:
        templates = ["Ciao {nome}, porta aperta"]

    tpl = random.choice(templates)
    msg = tpl.format(nome=nome).strip()
    msg = " ".join(msg.split())  # collassa doppi spazi se nome=""
    msg = msg.replace(" ,", ",")
    return msg
