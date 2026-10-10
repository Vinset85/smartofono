"""Voice identification (speaker recognition) — scaffold.

Usa Resemblyzer (https://github.com/resemble-ai/Resemblyzer): leggero,
funziona su CPU, embedding 256-dim, distanza cosine.

API:
    vi = VoiceId(cfg)                # carica encoder lazy
    vi.enroll("stefania", wav_bytes) # salva embedding
    vi.identify(wav_bytes)           # ritorna {nome, similarity} o None

Storage: data/voices/<nome>.npy (embedding) + meta.json.

Modulo opzionale: se Resemblyzer non e' installato, `is_available()`
ritorna False e tutti i metodi sono no-op. Si attiva con
`voice_recognition.enabled: true` in config + `pip install resemblyzer`.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

LOG = logging.getLogger(__name__)


class VoiceId:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.storage_dir = str(cfg.get("storage_dir", "data/voices"))
        self.match_threshold = float(cfg.get("match_threshold", 0.75))
        os.makedirs(self.storage_dir, exist_ok=True)
        self._encoder = None
        self._available: Optional[bool] = None
        self._lock = threading.RLock()
        self._embs: Dict[str, np.ndarray] = {}
        self._load_index()

    def _ensure(self) -> bool:
        if not self.enabled:
            return False
        if self._available is not None:
            return self._available
        try:
            from resemblyzer import VoiceEncoder  # type: ignore
            self._encoder = VoiceEncoder("cpu", verbose=False)
            self._available = True
            LOG.info("VoiceId pronto (resemblyzer)")
        except Exception as e:
            LOG.warning("VoiceId non disponibile: %s", e)
            self._available = False
        return self._available

    def is_available(self) -> bool:
        return self._ensure()

    def _user_path(self, nome: str) -> str:
        safe = "".join(c for c in (nome or "") if c.isalnum() or c in "_-").strip()
        return os.path.join(self.storage_dir, f"{safe}.npy")

    def _load_index(self) -> None:
        try:
            for fn in os.listdir(self.storage_dir):
                if not fn.endswith(".npy"):
                    continue
                nome = os.path.splitext(fn)[0]
                self._embs[nome] = np.load(os.path.join(self.storage_dir, fn))
        except Exception as e:
            LOG.debug("voice index load err: %s", e)

    def _wav_to_emb(self, wav_bytes: bytes,
                    sample_rate: int = 16000) -> Optional[np.ndarray]:
        if not self._ensure():
            return None
        try:
            import io
            import soundfile as sf  # type: ignore
            audio, sr = sf.read(io.BytesIO(wav_bytes))
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            from resemblyzer import preprocess_wav  # type: ignore
            wav = preprocess_wav(audio.astype(np.float32), source_sr=sr)
            emb = self._encoder.embed_utterance(wav)
            return emb.astype(np.float32)
        except Exception as e:
            LOG.warning("wav_to_emb err: %s", e)
            return None

    def enroll(self, nome: str, wav_bytes: bytes) -> bool:
        emb = self._wav_to_emb(wav_bytes)
        if emb is None:
            return False
        with self._lock:
            self._embs[nome] = emb
            np.save(self._user_path(nome), emb)
        return True

    def identify(self, wav_bytes: bytes) -> Optional[Dict[str, Any]]:
        emb = self._wav_to_emb(wav_bytes)
        if emb is None:
            return None
        if not self._embs:
            return None
        names = list(self._embs.keys())
        mat = np.stack([self._embs[n] for n in names], axis=0)
        # Resemblyzer usa cosine similarity nativa.
        a = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        b = emb / (np.linalg.norm(emb) + 1e-9)
        sims = a @ b
        idx = int(np.argmax(sims))
        sim = float(sims[idx])
        if sim < self.match_threshold:
            return None
        return {"nome": names[idx], "similarity": sim}

    def list_users(self) -> List[str]:
        return sorted(self._embs.keys())

    def delete(self, nome: str) -> bool:
        with self._lock:
            if nome in self._embs:
                del self._embs[nome]
            try:
                os.remove(self._user_path(nome))
                return True
            except Exception:
                return False
