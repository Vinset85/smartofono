#!/usr/bin/env python3
"""Diagnostica facciale dal vivo: cattura un frame dalla camera, esegue il
detector ArcFace e stampa le distanze reali verso ogni utente registrato.

Va eseguito col servizio videocitofono FERMO (camera libera).
"""
import os
import sys
import time

APP_DIR = "/opt/videocitofono/app"
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

import numpy as np  # noqa: E402


def load_config():
    from modules.config import load_config as lc  # type: ignore
    return lc(os.environ.get("VC_CONFIG"))


def capture_frame():
    from picamera2 import Picamera2  # type: ignore
    cam = Picamera2()
    cfg = cam.create_still_configuration(main={"size": (640, 480), "format": "RGB888"})
    cam.configure(cfg)
    cam.start()
    time.sleep(1.2)  # auto-exposure
    frame = cam.capture_array("main")
    cam.stop()
    cam.close()
    return frame  # RGB888 h,w,3


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    print(f"[diag] mettiti DAVANTI alla camera, cattura tra {secs}s...")
    time.sleep(secs)
    rgb = capture_frame()
    print(f"[diag] frame catturato shape={rgb.shape} dtype={rgb.dtype} "
          f"mean={float(rgb.mean()):.1f} (luminosita')")
    try:
        import cv2
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        cv2.imwrite("/tmp/face_diag.jpg", bgr)
        print("[diag] immagine salvata in /tmp/face_diag.jpg")
    except Exception as e:
        print("[diag] salvataggio jpg fallito:", e)

    cfg = load_config()
    fr = cfg.get("face_recognition", {}) or {}
    from modules.face_arcface import ArcFaceEngine  # type: ignore
    eng = ArcFaceEngine(fr, storage_dir="/opt/videocitofono/data/faces")
    eng.load()
    if not eng.is_available():
        print("[diag] ArcFace non disponibile"); return
    print(f"[diag] threshold={eng.match_threshold} margin={eng.match_margin} "
          f"pack={eng.model_pack} det_size={eng.det_size} "
          f"encodings={0 if eng._encs is None else eng._encs.shape[0]} "
          f"utenti={sorted(set(eng._labels))}")

    # Detection grezza
    import cv2
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    faces = eng._app.get(bgr)
    print(f"[diag] VOLTI RILEVATI: {len(faces)}")
    for i, f in enumerate(faces):
        x1, y1, x2, y2 = [int(v) for v in f.bbox]
        print(f"  volto[{i}] bbox=({x1},{y1},{x2},{y2}) "
              f"w={x2-x1} h={y2-y1} det_score={float(f.det_score):.3f}")
    if not faces:
        print("[diag] NESSUN volto rilevato dal detector.")
        return

    faces.sort(key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)
    emb = faces[0].normed_embedding.astype(np.float32)
    sims = eng._encs @ emb
    dists = (1.0 - sims).astype(np.float32)
    from modules.face_match import user_min_distances, decide_match  # type: ignore
    ud = user_min_distances(dists.tolist(), eng._labels)
    print("[diag] DISTANZE per utente (piu' bassa = piu' simile):")
    for name, d in sorted(ud.items(), key=lambda x: x[1]):
        print(f"  {name}: dist={d:.3f}  similarity={1.0-d:.3f}")
    res = decide_match(ud, eng.match_threshold, eng.match_margin)
    print(f"[diag] decisione: {res}")


if __name__ == "__main__":
    main()
