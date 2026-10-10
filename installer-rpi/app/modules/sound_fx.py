"""Feedback acustici brevi (click/key/error/success/bell).

Riproduce piccoli WAV via PulseAudio (`paplay`) o ALSA (`aplay`).
Evita Kivy SoundLoader: su Kivy 2.3 + SDL2/XWayland il primo load
blocca il main thread e congela UI/navigazione/chiamate.

Indipendente dal canale audio della chiamata (LiveKit) e dalla suoneria
(audio_backchannel), quindi puo' coesistere senza conflitti.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Dict, Optional

LOG = logging.getLogger(__name__)


class SoundFx:
    DEFAULT_FILES = {
        "click": "click.wav",
        "key": "key.wav",
        "error": "error.wav",
        "success": "success.wav",
        "bell": "bell.wav",
    }

    def __init__(self, sounds_dir: Optional[str] = None,
                 volume: float = 0.85, enabled: bool = True) -> None:
        if sounds_dir is None:
            sounds_dir = str(Path(__file__).resolve().parents[1] / "assets" / "sounds")
        self.dir = sounds_dir
        self.volume = max(0.0, min(1.0, float(volume)))
        self.enabled = bool(enabled)
        self._paths: Dict[str, str] = {}
        self._lengths: Dict[str, float] = {}
        self._player = shutil.which("paplay") or shutil.which("aplay")
        self._scan_files()

    def _scan_files(self) -> None:
        if not self.enabled:
            LOG.info("SoundFx disabilitato (ui.feedback_enabled=false)")
            return
        if not self._player:
            LOG.warning("SoundFx: paplay/aplay non disponibili")
            self.enabled = False
            return
        for name, fname in self.DEFAULT_FILES.items():
            path = os.path.join(self.dir, fname)
            if not os.path.exists(path):
                LOG.warning("SoundFx: file mancante %s", path)
                continue
            self._paths[name] = path
            self._lengths[name] = self._wav_duration(path)
        LOG.info("SoundFx pronto: %d suoni (%s)", len(self._paths), self._player)

    @staticmethod
    def _wav_duration(path: str) -> float:
        try:
            with wave.open(path, "rb") as wf:
                rate = wf.getframerate() or 1
                return wf.getnframes() / float(rate)
        except Exception:
            return 0.6

    def _paplay_volume(self) -> int:
        return max(0, min(65536, int(self.volume * 65536)))

    def _spawn(self, path: str) -> None:
        if not self._player:
            return
        name = os.path.basename(self._player)
        cmd: list[str]
        if name == "paplay":
            # paplay (PulseAudio) non supporta -q; con -q fallisce in silenzio.
            cmd = [self._player, f"--volume={self._paplay_volume()}", path]
        else:
            cmd = [self._player, "-q", path]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def set_volume(self, v: float) -> None:
        self.volume = max(0.0, min(1.0, float(v)))

    def get_length(self, name: str) -> float:
        return self._lengths.get(name, 0.0)

    def play(self, name: str, on_end=None, on_end_gap: float = 0.0) -> float:
        if not self.enabled:
            if on_end is not None:
                try:
                    on_end()
                except Exception:
                    pass
            return 0.0
        path = self._paths.get(name)
        if path is None:
            if on_end is not None:
                try:
                    on_end()
                except Exception:
                    pass
            return 0.0
        try:
            self._spawn(path)
        except Exception as e:
            LOG.debug("SoundFx.play(%s) err: %s", name, e)
        L = self._lengths.get(name, 0.0)
        if on_end is not None:
            try:
                from kivy.clock import Clock
                wait = (L if L > 0 else 0.6) + max(0.0, float(on_end_gap))
                Clock.schedule_once(lambda *_: _safe_call(on_end), wait)
            except Exception:
                try:
                    on_end()
                except Exception:
                    pass
        return L


def _safe_call(fn) -> None:
    try:
        fn()
    except Exception as e:
        LOG.debug("sound on_end cb err: %s", e)
