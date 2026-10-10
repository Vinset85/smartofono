#!/usr/bin/env python3
"""Publisher LiveKit sintetico per collaudare la registrazione (egress).

Entra nella room come il visitatore (identity `rpi`) e pubblica una traccia
video (barre di colore che scorrono, cosi' si vede subito se l'MP4 e' nero) e
una traccia audio (tono 440 Hz) per N secondi. Serve a verificare la catena
HA -> token issuer -> egress -> file MP4 senza dover suonare fisicamente al
citofono e senza toccare la camera del Pi (i frame sono generati, il sensore
IMX708 resta libero: l'app in esecuzione non viene disturbata).

Uso, sul Pi:
    /opt/videocitofono/venv/bin/python3 test-livekit-publish.py [secondi]

Non usare mentre e' in corso una chiamata reale: l'identity `rpi` sarebbe
duplicata e il server disconnetterebbe la sessione dell'app.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import urllib.request

import numpy as np
from livekit import rtc

TOKEN_URL = os.environ.get(
    "VC_LK_TOKEN_URL", "http://192.168.1.160:8081/token")
ROOM = os.environ.get("VC_LK_ROOM", "videocitofono")
IDENTITY = os.environ.get("VC_LK_IDENTITY", "rpi")

WIDTH, HEIGHT, FPS = 640, 480, 15
SAMPLE_RATE, CHANNELS = 48000, 1
SAMPLES_PER_FRAME = SAMPLE_RATE // 100  # 10 ms


def fetch_token() -> tuple[str, str]:
    body = json.dumps({
        "identity": IDENTITY,
        "room": ROOM,
        "prefer_lan": True,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
    return data["ws_url"], data["token"]


def i420_frame(tick: int) -> rtc.VideoFrame:
    """Barre verticali che scorrono: contenuto non statico e non nero."""
    y = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    bar = WIDTH // 8
    for i in range(8):
        y[:, i * bar:(i + 1) * bar] = 32 + ((i * 28 + tick * 4) % 200)
    u = np.full((HEIGHT // 2, WIDTH // 2), 90 + (tick % 60), dtype=np.uint8)
    v = np.full((HEIGHT // 2, WIDTH // 2), 160 - (tick % 60), dtype=np.uint8)
    return rtc.VideoFrame(
        width=WIDTH,
        height=HEIGHT,
        type=rtc.VideoBufferType.I420,
        data=y.tobytes() + u.tobytes() + v.tobytes(),
    )


async def pump_video(source: rtc.VideoSource, stop: asyncio.Event) -> None:
    tick = 0
    interval = 1.0 / FPS
    while not stop.is_set():
        source.capture_frame(i420_frame(tick))
        tick += 1
        await asyncio.sleep(interval)


async def pump_audio(source: rtc.AudioSource, stop: asyncio.Event) -> None:
    phase = 0.0
    step = 2 * math.pi * 440.0 / SAMPLE_RATE
    while not stop.is_set():
        samples = np.empty(SAMPLES_PER_FRAME, dtype=np.int16)
        for i in range(SAMPLES_PER_FRAME):
            samples[i] = int(8000 * math.sin(phase))
            phase += step
        frame = rtc.AudioFrame(
            data=samples.tobytes(),
            sample_rate=SAMPLE_RATE,
            num_channels=CHANNELS,
            samples_per_channel=SAMPLES_PER_FRAME,
        )
        await source.capture_frame(frame)


async def main(seconds: float) -> int:
    ws_url, token = fetch_token()
    print(f"token ok, connessione a {ws_url} come {IDENTITY}", flush=True)
    room = rtc.Room()
    await room.connect(ws_url, token)
    print(f"connesso in room '{ROOM}'", flush=True)

    vsource = rtc.VideoSource(WIDTH, HEIGHT)
    vtrack = rtc.LocalVideoTrack.create_video_track("rpi-cam", vsource)
    await room.local_participant.publish_track(
        vtrack, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA))
    asource = rtc.AudioSource(SAMPLE_RATE, CHANNELS)
    atrack = rtc.LocalAudioTrack.create_audio_track("rpi-mic", asource)
    await room.local_participant.publish_track(
        atrack,
        rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    print("tracce pubblicate (video 640x480@15 + audio 440Hz)", flush=True)

    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(pump_video(vsource, stop)),
        asyncio.create_task(pump_audio(asource, stop)),
    ]
    await asyncio.sleep(seconds)
    stop.set()
    for t in tasks:
        t.cancel()
    await room.disconnect()
    print(f"pubblicazione terminata dopo {seconds:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    raise SystemExit(asyncio.run(main(dur)))
