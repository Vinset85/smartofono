"""Engine di riconoscimento facciale basato su InsightFace (ArcFace).

Modello consigliato per Pi5: `buffalo_sc` (det+rec leggero, ~30MB) o
`buffalo_s` (più accurato, ~80MB). InsightFace gira via onnxruntime
CPU su aarch64 Bookworm (lo stesso runtime di Piper TTS, gia' installato).

API compatibile con `FaceRecognizer` di `face_recognition_stub.py`:
    - list_users()
    - enroll_image(nome, image_bytes, ext=..., genere=...)
    - delete_user(nome)
    - rename_user(old, new)
    - update_user(nome, ...)
    - get_user_meta(nome)
    - scan_frame(rgb_array) -> dict | None
    - reload_library()

Il database degli encoding e' lo stesso filesystem di `face_recognition`
(`data/faces/<nome>/*.jpg`) ma con un indice cache separato in
`data/faces/.index_arcface.npz` per non collidere con quello dlib.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

LOG = logging.getLogger(__name__)

_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
_INDEX_FN = ".index_arcface.npz"
_META_FN = "meta.json"


def _normalize_genere(g: Optional[str]) -> str:
    g = (g or "").strip().upper()
    if g in ("M", "MASCHIO", "MALE"):
        return "M"
    if g in ("F", "FEMMINA", "FEMALE"):
        return "F"
    return ""


def _safe_name(s: str) -> str:
    s = (s or "").strip()
    bad = '<>:"/\\|?*'
    return "".join(c for c in s if c not in bad).strip().replace(" ", "_")


class ArcFaceEngine:
    """Engine ArcFace via insightface.app.FaceAnalysis.

    L'inizializzazione e' lazy: il modello (~30-80MB) si carica al primo
    `_ensure_loaded()` e non blocca l'app boot. Se il caricamento
    fallisce (libreria non installata o modelli mancanti),
    `is_available()` ritorna False e il main puo' fare fallback al
    motore dlib classico.
    """

    def __init__(self, cfg: Optional[Dict[str, Any]] = None,
                 storage_dir: str = "data/faces") -> None:
        cfg = cfg or {}
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        # Soglia distanza euclidea normalizzata (1 - cos_sim) sotto la
        # quale il volto e' considerato match. ArcFace ha ottimo
        # separation: 0.40 e' severo (consigliato), 0.45 permissivo.
        self.match_threshold = float(cfg.get("match_threshold", 0.35))
        # Margin minimo tra best e second-best (per utente, non per foto).
        self.match_margin = float(cfg.get("match_margin", 0.07))
        # Pacchetto di modelli InsightFace.
        self.model_pack = str(cfg.get("model_pack", "buffalo_sc"))
        self.det_size = int(cfg.get("det_size", 320))
        self._app = None
        self._available: Optional[bool] = None
        self._lock = threading.RLock()
        self._encs: Optional[np.ndarray] = None
        self._labels: List[str] = []
        # Pre-load nel costruttore non e' ottimo (Kivy starts slow); il
        # caller chiamera' load() esplicitamente in un thread di
        # background.

    # ---- Lifecycle ------------------------------------------------------

    def _ensure_app(self) -> bool:
        if self._app is not None:
            return True
        try:
            from insightface.app import FaceAnalysis  # type: ignore
        except Exception as e:
            LOG.warning("InsightFace non installato: %s (fallback dlib)", e)
            self._available = False
            return False
        try:
            app = FaceAnalysis(name=self.model_pack,
                               providers=["CPUExecutionProvider"])
            app.prepare(ctx_id=0, det_size=(self.det_size, self.det_size))
            self._app = app
            self._available = True
            LOG.info("ArcFace pronto (pack=%s, det_size=%d, threshold=%.2f, margin=%.2f)",
                     self.model_pack, self.det_size, self.match_threshold,
                     self.match_margin)
            return True
        except Exception as e:
            LOG.warning("ArcFace init fallita: %s (fallback dlib)", e)
            self._available = False
            return False

    def is_available(self) -> bool:
        if self._available is None:
            return self._ensure_app()
        return bool(self._available)

    def load(self) -> None:
        """Carica modello e ricalcola/ricarica indice degli encoding."""
        if not self._ensure_app():
            return
        self._build_index()

    # ---- Index / encodings ---------------------------------------------

    def _index_path(self) -> str:
        # Cache specifica per pack: embedding di modelli diversi non sono
        # compatibili, quindi cambiando model_pack si rigenera da zero.
        return os.path.join(self.storage_dir, f".index_arcface_{self.model_pack}.npz")

    def _build_index(self) -> None:
        with self._lock:
            encs: List[np.ndarray] = []
            labels: List[str] = []
            cache = self._load_cache()
            for entry in sorted(os.listdir(self.storage_dir)):
                p = os.path.join(self.storage_dir, entry)
                if not os.path.isdir(p) or entry.startswith("."):
                    continue
                for fn in sorted(os.listdir(p)):
                    if os.path.splitext(fn)[1].lower() not in _IMG_EXT:
                        continue
                    fp = os.path.join(p, fn)
                    key = self._cache_key(fp)
                    vec = cache.get(key)
                    if vec is None:
                        vec = self._encode_image_file(fp)
                        if vec is None:
                            continue
                        cache[key] = vec
                    encs.append(vec)
                    labels.append(entry)
            if encs:
                self._encs = np.stack(encs, axis=0).astype(np.float32)
                self._labels = labels
            else:
                self._encs = None
                self._labels = []
            self._save_cache(cache)
            LOG.info("ArcFace index: %d encodings (%d utenti)",
                     0 if self._encs is None else self._encs.shape[0],
                     len(set(labels)))

    def _cache_key(self, path: str) -> str:
        try:
            st = os.stat(path)
            return f"{path}|{int(st.st_mtime)}|{st.st_size}"
        except Exception:
            return path

    def _load_cache(self) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        try:
            data = np.load(self._index_path(), allow_pickle=False)
            keys = data["keys"]
            vecs = data["vecs"]
            for k, v in zip(keys.tolist(), vecs):
                out[k] = v
        except Exception:
            pass
        return out

    def _save_cache(self, cache: Dict[str, np.ndarray]) -> None:
        try:
            if not cache:
                return
            keys = np.array(list(cache.keys()))
            vecs = np.stack(list(cache.values()), axis=0).astype(np.float32)
            np.savez(self._index_path(), keys=keys, vecs=vecs)
        except Exception as e:
            LOG.debug("save cache err: %s", e)

    # ---- Image -> embedding --------------------------------------------

    def _encode_image_file(self, path: str) -> Optional[np.ndarray]:
        """Carica un file e ritorna il primo embedding L2-normalizzato."""
        try:
            import cv2  # type: ignore
        except Exception as e:
            LOG.warning("opencv non disponibile: %s", e)
            return None
        try:
            img = cv2.imread(path)
            if img is None:
                return None
            return self._encode_bgr(img)
        except Exception as e:
            LOG.debug("encode_image_file err: %s", e)
            return None

    def _encode_bgr(self, bgr: np.ndarray) -> Optional[np.ndarray]:
        if not self._ensure_app():
            return None
        try:
            faces = self._app.get(bgr)
        except Exception as e:
            LOG.debug("arcface get err: %s", e)
            return None
        if not faces:
            return None
        # Scegli il volto piu' grande (di solito quello principale)
        faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
                   reverse=True)
        emb = faces[0].normed_embedding  # gia' L2-normalizzato
        return emb.astype(np.float32)

    # ---- Match ----------------------------------------------------------

    def scan_frame(self, rgb: np.ndarray) -> Optional[Dict[str, Any]]:
        """Riceve un frame RGB (numpy h,w,3 uint8) e ritorna {nome,distance,...}
        per il match piu' vicino sotto soglia, oppure None."""
        if rgb is None or rgb.size == 0:
            return None
        if self._encs is None or len(self._labels) == 0:
            return None
        try:
            import cv2
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception:
            bgr = rgb[..., ::-1]
        emb = self._encode_bgr(bgr)
        if emb is None:
            return None
        from modules.face_match import decide_match, user_min_distances

        sims = self._encs @ emb
        dists = (1.0 - sims).astype(np.float32)
        user_dists = user_min_distances(dists.tolist(), self._labels)
        result = decide_match(user_dists, self.match_threshold, self.match_margin)
        if result is None:
            return None
        if not result.get("match"):
            if result.get("borderline"):
                LOG.info(
                    "ArcFace borderline: best=%s dist=%.3f 2nd=%s margin=%.3f reason=%s",
                    result.get("best_user"), result.get("distance", -1),
                    result.get("second_user"), result.get("margin", -1),
                    result.get("reject_reason"),
                )
            return result
        nome = result["nome"]
        meta = self.get_user_meta(nome)
        best_sim = float(np.max(sims[np.array(self._labels) == nome]))
        return {
            "match": True,
            "nome": nome,
            "distance": result["distance"],
            "similarity": 1.0 - result["distance"],
            "margin": result.get("margin"),
            "second_user": result.get("second_user"),
            "borderline": result.get("borderline", False),
            "genere": meta.get("genere", ""),
            "apre": meta.get("apre", "porta"),
        }

    # ---- User meta ------------------------------------------------------

    def _user_dir(self, nome: str) -> str:
        return os.path.join(self.storage_dir, _safe_name(nome))

    def _meta_path(self, nome: str) -> str:
        return os.path.join(self._user_dir(nome), _META_FN)

    def _load_meta(self, user_dir: str) -> Dict[str, Any]:
        p = os.path.join(user_dir, _META_FN)
        if not os.path.exists(p):
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _save_meta(self, user_dir: str, meta: Dict[str, Any]) -> None:
        try:
            os.makedirs(user_dir, exist_ok=True)
            p = os.path.join(user_dir, _META_FN)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            LOG.debug("save_meta err: %s", e)

    def get_user_meta(self, nome: str) -> Dict[str, Any]:
        return self._load_meta(self._user_dir(nome))

    # ---- Library API ----------------------------------------------------

    @staticmethod
    def _is_auto_sample(fn: str) -> bool:
        return fn.startswith("auto_") and os.path.splitext(fn)[1].lower() in _IMG_EXT

    def list_auto_samples(self, nome: str) -> List[str]:
        ud = self._user_dir(nome)
        if not os.path.isdir(ud):
            return []
        try:
            return sorted(
                fn for fn in os.listdir(ud) if self._is_auto_sample(fn))
        except Exception:
            return []

    def delete_auto_sample(self, nome: str, filename: str) -> bool:
        nome_s = _safe_name(nome)
        fn = os.path.basename(filename or "")
        if not fn.startswith("auto_"):
            return False
        fp = os.path.join(self._user_dir(nome_s), fn)
        if not os.path.isfile(fp):
            return False
        try:
            os.remove(fp)
            self._build_index()
            return True
        except Exception as e:
            LOG.warning("delete_auto_sample err: %s", e)
            return False

    def purge_auto_samples(self, nome: str) -> int:
        removed = 0
        for fn in self.list_auto_samples(nome):
            if self.delete_auto_sample(nome, fn):
                removed += 1
        return removed

    def list_users(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            for entry in sorted(os.listdir(self.storage_dir)):
                p = os.path.join(self.storage_dir, entry)
                if not os.path.isdir(p) or entry.startswith("."):
                    continue
                cnt = 0
                auto_cnt = 0
                for fn in os.listdir(p):
                    if os.path.splitext(fn)[1].lower() in _IMG_EXT:
                        cnt += 1
                        if self._is_auto_sample(fn):
                            auto_cnt += 1
                if cnt <= 0:
                    continue
                meta = self._load_meta(p)
                out.append({
                    "nome": entry,
                    "foto": cnt,
                    "auto_foto": auto_cnt,
                    "genere": meta.get("genere", ""),
                    "pin_set": bool(meta.get("pin_set", False)),
                })
        except Exception as e:
            LOG.warning("list_users err: %s", e)
        return out

    def enroll_image(self, nome: str, image_bytes: bytes,
                     ext: str = ".jpg",
                     genere: Optional[str] = None) -> Dict[str, Any]:
        """Registra una nuova foto. Valida che contenga un volto rilevabile
        prima di salvarla. Ritorna dict compatibile con lo stub dlib:
        {"ok": bool, "msg": str, "n_foto": int}."""
        nome_s = _safe_name(nome)
        if not nome_s:
            return {"ok": False, "msg": "Nome non valido", "n_foto": 0}
        if not image_bytes:
            return {"ok": False, "msg": "Immagine vuota", "n_foto": 0}
        ext_l = (ext or ".jpg").lower()
        if ext_l not in _IMG_EXT:
            ext_l = ".jpg"
        # Decode + validazione volto via insightface (se disponibile)
        emb: Optional[np.ndarray] = None
        if self._ensure_app():
            try:
                import cv2  # type: ignore
                arr = np.frombuffer(image_bytes, dtype=np.uint8)
                bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if bgr is None:
                    return {"ok": False,
                            "msg": "Immagine non decodificabile",
                            "n_foto": 0}
                emb = self._encode_bgr(bgr)
            except Exception as e:
                LOG.debug("enroll decode err: %s", e)
                emb = None
            if emb is None:
                return {"ok": False,
                        "msg": "Nessun volto rilevato nella foto",
                        "n_foto": 0}
        ud = self._user_dir(nome_s)
        os.makedirs(ud, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        out = os.path.join(ud, f"{ts}{ext_l}")
        try:
            with open(out, "wb") as f:
                f.write(image_bytes)
        except Exception as e:
            return {"ok": False, "msg": f"write err: {e}", "n_foto": 0}
        meta = self._load_meta(ud)
        if genere:
            meta["genere"] = _normalize_genere(genere)
        self._save_meta(ud, meta)
        self._build_index()
        n_foto = sum(1 for fn in os.listdir(ud)
                     if os.path.splitext(fn)[1].lower() in _IMG_EXT)
        return {"ok": True, "msg": "Registrato", "n_foto": n_foto}

    def delete_user(self, nome: str) -> bool:
        ud = self._user_dir(nome)
        if not os.path.isdir(ud):
            return False
        try:
            shutil.rmtree(ud)
            self._build_index()
            return True
        except Exception as e:
            LOG.warning("delete_user err: %s", e)
            return False

    def rename_user(self, old: str, new: str) -> bool:
        a = self._user_dir(old)
        b = self._user_dir(new)
        if not os.path.isdir(a) or os.path.exists(b):
            return False
        try:
            os.rename(a, b)
            self._build_index()
            return True
        except Exception as e:
            LOG.warning("rename_user err: %s", e)
            return False

    def update_user(self, nome: str,
                    genere: Optional[str] = None,
                    pin_set: Optional[bool] = None) -> bool:
        ud = self._user_dir(nome)
        if not os.path.isdir(ud):
            return False
        meta = self._load_meta(ud)
        if genere is not None:
            meta["genere"] = _normalize_genere(genere)
        if pin_set is not None:
            meta["pin_set"] = bool(pin_set)
        self._save_meta(ud, meta)
        return True

    def reload_library(self) -> None:
        self._build_index()
