"""Modulo riconoscimento facciale.

Implementazione reale basata su `face_recognition` (dlib + ResNet 128D).
Se le dipendenze non sono installate, il modulo cade graceful in modalita'
disabilitata (`is_available() == False`) cosi' la UI puo' mostrare un
messaggio "non configurato" senza crashare.

Architettura:
- Volti registrati in: <storage_dir>/<nome_persona>/*.jpg|png
- Cache encodings in:  <storage_dir>/_encodings.npz   (rigenerato se le foto
  cambiano: confronto mtime). Riduce startup da minuti a millisecondi.
- scan_frame(frame_bgr): ritorna {"nome", "apre"} se match consecutivo
  raggiunto, altrimenti None. Convenzione frame: numpy array BGR.

Per accuratezza:
- Tolerance default 0.45 (sotto la default 0.6 di face_recognition: piu'
  rigorosa, meno falsi positivi).
- Per ogni persona si possono registrare N foto -> N encoding distinti.
  Si confronta col MIN della distance: bastano 1 foto frontale, ma con
  3-5 foto da angoli diversi l'accuracy aumenta significativamente.
- Frame downsampled (default 0.5x) per velocizzare detection: la
  detection HOG a 320x240 e' ~50ms sul Pi5; encoding ~80ms.
- L'utente di livello superiore (FaceScreen) richiede `min_consecutive_matches`
  frame consecutivi della stessa persona prima di autorizzare: anti-spoof
  basilare contro flash/glitch.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

LOG = logging.getLogger(__name__)

try:
    import numpy as np  # type: ignore
    _NP = True
except Exception:
    _NP = False

try:
    import face_recognition  # type: ignore
    _FR = True
except Exception:
    face_recognition = None  # type: ignore
    _FR = False

# Estensioni accettate per le foto enrolled
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# Cache file (NPZ binario, piu' veloce di JSON per array float32)
_CACHE_FN = "_encodings.npz"

# Metadati per-utente (genere, etc.) salvati come JSON nella cartella utente.
_META_FN = "meta.json"


def _normalize_genere(g) -> str:
    """Ritorna 'M' / 'F' / '' (sconosciuto)."""
    if not g:
        return ""
    s = str(g).strip().upper()
    if s in ("M", "MALE", "MASCHIO", "MASCHILE", "U", "UOMO"):
        return "M"
    if s in ("F", "FEMALE", "FEMMINA", "FEMMINILE", "D", "DONNA"):
        return "F"
    return ""


class FaceRecognizer:
    """Riconoscitore basato su face_recognition (dlib).

    cfg attesa (tutti opzionali con default):
      enabled: bool
      modello: 'hog' | 'cnn'   (default hog; cnn richiede GPU/CUDA)
      tolerance: float         (default 0.45)
      storage_dir: str         (default 'data/faces')
      timeout_sec: int         (default 8) - usato dalla UI
      min_consecutive_matches: int (default 3) - usato dalla UI
      downsample: float        (default 0.5) - fattore resize prima detection
      utenti: list[dict]       (opzionale, override scope/apre per nome:
                                [{nome:'Anna', apre:'porta'}, ...])
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg or {}
        self.enabled = bool(self.cfg.get("enabled", False))
        self.modello = str(self.cfg.get("modello", "hog"))
        self.tolerance = float(self.cfg.get("tolerance", 0.35))
        self.match_margin = float(self.cfg.get("match_margin", 0.07))
        self.storage_dir = self._resolve_storage(self.cfg.get("storage_dir", "data/faces"))
        self.downsample = float(self.cfg.get("downsample", 0.5))
        # users_meta[nome.lower()] -> {"apre": "porta"|"cancello"}
        self.users_meta: Dict[str, Dict[str, Any]] = {}
        for u in self.cfg.get("utenti", []) or []:
            n = (u.get("nome") or "").strip().lower()
            if n:
                self.users_meta[n] = {"apre": u.get("apre", "porta")}
        # Lista parallela: encodings[i] e' encoding 128D, names[i] e' il
        # nome della persona (puo' avere duplicati: piu' foto per persona).
        self._encodings: Optional["np.ndarray"] = None
        self._names: List[str] = []
        self._loaded = False
        self._lock = None
        try:
            import threading
            self._lock = threading.Lock()
        except Exception:
            pass
        if not self.enabled:
            return
        if not _FR:
            LOG.warning("FaceRecognizer enabled ma face_recognition/dlib non installati: modulo inerte")
            return
        os.makedirs(self.storage_dir, exist_ok=True)
        self.reload_library()

    # ----------------------------- public API ------------------------------

    def is_available(self) -> bool:
        """True solo se face_recognition installato + abilitato + almeno 1
        encoding caricato (cioe' qualcuno e' registrato)."""
        return bool(self.enabled and _FR and self._loaded and self._encodings is not None and len(self._names) > 0)

    def reload_library(self) -> int:
        """Ricarica tutti gli encoding dal disco. Restituisce numero
        encoding caricati. Idempotente, sicuro da chiamare in runtime."""
        if not _FR:
            return 0
        with (self._lock or _NullCtx()):
            try:
                encs, names = self._load_or_build_cache()
                if encs is None or len(names) == 0:
                    self._encodings = None
                    self._names = []
                    self._loaded = True
                    LOG.info("FaceRecognizer: nessun volto registrato in %s", self.storage_dir)
                    return 0
                self._encodings = encs
                self._names = names
                self._loaded = True
                LOG.info("FaceRecognizer: %d encoding caricati per %d persone",
                         len(names), len(set(names)))
                return len(names)
            except Exception as e:
                LOG.error("FaceRecognizer reload err: %s", e)
                self._encodings = None
                self._names = []
                self._loaded = True
                return 0

    @staticmethod
    def _is_auto_sample(fn: str) -> bool:
        return fn.startswith("auto_") and os.path.splitext(fn)[1].lower() in _IMG_EXT

    def list_auto_samples(self, nome: str) -> List[str]:
        d = os.path.join(self.storage_dir, self._sanitize_name(nome))
        if not os.path.isdir(d):
            return []
        try:
            return sorted(
                fn for fn in os.listdir(d) if self._is_auto_sample(fn))
        except Exception:
            return []

    def delete_auto_sample(self, nome: str, filename: str) -> bool:
        nome_safe = self._sanitize_name(nome)
        fn = os.path.basename(filename or "")
        if not fn.startswith("auto_"):
            return False
        fp = os.path.join(self.storage_dir, nome_safe, fn)
        if not os.path.isfile(fp):
            return False
        try:
            os.remove(fp)
            self._loaded = False
            self.load()
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
        """Lista persone registrate con conteggio foto e metadati (genere)."""
        out: List[Dict[str, Any]] = []
        try:
            for entry in sorted(os.listdir(self.storage_dir)):
                p = os.path.join(self.storage_dir, entry)
                if not os.path.isdir(p):
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

    def _load_meta(self, user_dir: str) -> Dict[str, Any]:
        path = os.path.join(user_dir, _META_FN)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                return {}
            d["genere"] = _normalize_genere(d.get("genere", ""))
            return d
        except Exception:
            return {}

    def _save_meta(self, user_dir: str, meta: Dict[str, Any]) -> None:
        path = os.path.join(user_dir, _META_FN)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            LOG.warning("save meta %s err: %s", path, e)

    def get_user_meta(self, nome: str) -> Dict[str, Any]:
        """Ritorna il dict meta {genere, ...} di una persona registrata."""
        nome_safe = self._sanitize_name(nome)
        d = os.path.join(self.storage_dir, nome_safe)
        if not os.path.isdir(d):
            return {}
        return self._load_meta(d)

    def update_user(self, nome: str, genere: Optional[str] = None,
                    pin_set: Optional[bool] = None) -> Dict[str, Any]:
        """Aggiorna i metadati (genere, pin_set) della persona registrata."""
        nome_safe = self._sanitize_name(nome)
        d = os.path.join(self.storage_dir, nome_safe)
        if not os.path.isdir(d):
            return {"ok": False, "msg": "Persona non trovata"}
        meta = self._load_meta(d)
        if genere is not None:
            meta["genere"] = _normalize_genere(genere)
        if pin_set is not None:
            meta["pin_set"] = bool(pin_set)
        self._save_meta(d, meta)
        return {"ok": True, "msg": "Aggiornato", "meta": meta}

    def rename_user(self, old: str, new: str) -> Dict[str, Any]:
        """Rinomina la persona (sposta la cartella). Non rigenera gli
        encoding (tanto e' la stessa identita': cambia solo il nome
        ritornato a UI). Invalida la cache cosi' al prossimo scan i
        names del cache npz vengono rigenerati col nuovo nome."""
        old_safe = self._sanitize_name(old)
        new_safe = self._sanitize_name(new)
        if not old_safe or not new_safe:
            return {"ok": False, "msg": "Nome non valido"}
        if old_safe == new_safe:
            return {"ok": True, "msg": "Nessun cambio", "nome": new_safe}
        src = os.path.join(self.storage_dir, old_safe)
        dst = os.path.join(self.storage_dir, new_safe)
        if not os.path.isdir(src):
            return {"ok": False, "msg": "Persona non trovata"}
        if os.path.exists(dst):
            return {"ok": False, "msg": "Esiste gia' una persona con quel nome"}
        try:
            os.rename(src, dst)
        except Exception as e:
            return {"ok": False, "msg": f"Errore rename: {e}"}
        self._invalidate_cache()
        self.reload_library()
        return {"ok": True, "msg": "Rinominato", "nome": new_safe}

    def enroll_image(self, nome: str, image_bytes: bytes, ext: str = ".jpg",
                     genere: Optional[str] = None) -> Dict[str, Any]:
        """Registra una nuova foto per la persona `nome`. Estrae l'encoding
        prima di salvare per validare che la foto contenga UN solo volto
        riconoscibile. Se `genere` viene passato (M/F) salva/aggiorna
        anche il meta.json della persona.
        Ritorna {"ok": bool, "msg": str, "n_foto": int}."""
        if not _FR:
            return {"ok": False, "msg": "face_recognition non installato", "n_foto": 0}
        nome_safe = self._sanitize_name(nome)
        if not nome_safe:
            return {"ok": False, "msg": "Nome non valido", "n_foto": 0}
        if not image_bytes:
            return {"ok": False, "msg": "Immagine vuota", "n_foto": 0}
        ext = (ext or ".jpg").lower()
        if ext not in _IMG_EXT:
            ext = ".jpg"
        # 1) decodifica + verifica volto
        try:
            import io
            from PIL import Image  # type: ignore
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            arr = np.array(img)
        except Exception as e:
            return {"ok": False, "msg": f"Immagine non leggibile: {e}", "n_foto": 0}
        try:
            locs = face_recognition.face_locations(arr, model=self.modello)
        except Exception as e:
            return {"ok": False, "msg": f"Detection fallita: {e}", "n_foto": 0}
        if len(locs) == 0:
            return {"ok": False, "msg": "Nessun volto rilevato", "n_foto": 0}
        if len(locs) > 1:
            return {"ok": False, "msg": "Rilevati piu' volti: usa una foto con un solo volto", "n_foto": 0}
        try:
            encs = face_recognition.face_encodings(arr, known_face_locations=locs, num_jitters=1)
        except Exception as e:
            return {"ok": False, "msg": f"Encoding fallito: {e}", "n_foto": 0}
        if not encs:
            return {"ok": False, "msg": "Encoding non estratto", "n_foto": 0}
        # 2) salva file
        d = os.path.join(self.storage_dir, nome_safe)
        os.makedirs(d, exist_ok=True)
        fn = f"{int(time.time()*1000)}{ext}"
        path = os.path.join(d, fn)
        try:
            with open(path, "wb") as f:
                f.write(image_bytes)
        except Exception as e:
            return {"ok": False, "msg": f"Scrittura file fallita: {e}", "n_foto": 0}
        # 2b) salva/aggiorna meta.json se passato genere (lo manteniamo
        # anche tra successivi enroll: se gia' presente, lo aggiorniamo
        # solo se viene passato un nuovo valore non vuoto).
        try:
            meta = self._load_meta(d)
            g = _normalize_genere(genere) if genere is not None else ""
            if g:
                meta["genere"] = g
                self._save_meta(d, meta)
            elif "genere" not in meta:
                # Inizializza il file meta vuoto la prima volta cosi'
                # esiste sempre (e l'aggiornamento successivo via
                # update_user funziona senza dover creare la cartella).
                self._save_meta(d, meta)
        except Exception as e:
            LOG.warning("enroll meta save err: %s", e)
        # 3) ricarica libreria (cache invalidata da mtime cartella)
        self._invalidate_cache()
        n = self.reload_library()
        n_foto = sum(1 for x in self._names if x.lower() == nome_safe.lower())
        return {"ok": True, "msg": "Registrato", "n_foto": n_foto, "totale_encodings": n}

    def delete_user(self, nome: str) -> Dict[str, Any]:
        """Elimina tutte le foto della persona `nome`."""
        nome_safe = self._sanitize_name(nome)
        d = os.path.join(self.storage_dir, nome_safe)
        if not os.path.isdir(d):
            return {"ok": False, "msg": "Persona non trovata"}
        try:
            for fn in os.listdir(d):
                try:
                    os.remove(os.path.join(d, fn))
                except Exception:
                    pass
            os.rmdir(d)
        except Exception as e:
            return {"ok": False, "msg": f"Errore eliminazione: {e}"}
        self._invalidate_cache()
        self.reload_library()
        return {"ok": True, "msg": "Eliminato"}

    def scan_frame(self, frame_bgr) -> Optional[Dict[str, Any]]:
        """Cerca un match nel frame BGR. Ritorna dict utente o None.
        - Downsample il frame per velocita' (default 0.5x)
        - HOG detection (~50ms su Pi5 a 640x480)
        - Per ogni volto rilevato calcola distanza euclidea verso TUTTI gli
          encoding della libreria. Se la min distance < tolerance, match.
        - Se piu' volti: ritorna il primo che fa match (tipicamente uno solo
          davanti alla camera in stretto inquadramento).
        """
        if not self.is_available() or frame_bgr is None or not _NP:
            return None
        try:
            # BGR -> RGB (face_recognition lavora su RGB)
            rgb = frame_bgr[:, :, ::-1]
            if self.downsample and self.downsample != 1.0:
                # Ridimensionamento via slicing nearest-neighbor (no cv2):
                # sufficiente per detection HOG.
                step = max(1, int(round(1.0 / self.downsample)))
                small = rgb[::step, ::step]
                scale = step
            else:
                small = rgb
                scale = 1
            small = np.ascontiguousarray(small)
            locs = face_recognition.face_locations(small, model=self.modello, number_of_times_to_upsample=1)
            if not locs:
                return None
            encs = face_recognition.face_encodings(small, known_face_locations=locs, num_jitters=1)
            if not encs:
                return None
            for enc in encs:
                from modules.face_match import decide_match, user_min_distances

                dists = np.linalg.norm(self._encodings - enc, axis=1)
                user_dists = user_min_distances(
                    dists.tolist(), self._names)
                result = decide_match(
                    user_dists, self.tolerance, self.match_margin)
                if result is None:
                    continue
                if not result.get("match"):
                    if result.get("borderline"):
                        LOG.info(
                            "dlib borderline: best=%s dist=%.3f 2nd=%s margin=%.3f reason=%s",
                            result.get("best_user"),
                            result.get("distance", -1),
                            result.get("second_user"),
                            result.get("margin", -1),
                            result.get("reject_reason"),
                        )
                    return result
                nome = result["nome"]
                meta = self.users_meta.get(nome.lower(), {})
                user_meta = self._load_meta(
                    os.path.join(self.storage_dir, nome))
                return {
                    "match": True,
                    "nome": nome,
                    "apre": meta.get("apre", "porta"),
                    "genere": user_meta.get("genere", ""),
                    "distance": result["distance"],
                    "margin": result.get("margin"),
                    "second_user": result.get("second_user"),
                    "borderline": result.get("borderline", False),
                }
        except Exception as e:
            LOG.warning("scan_frame err: %s", e)
        return None

    # ----------------------------- internal --------------------------------

    def _resolve_storage(self, p: str) -> str:
        if os.path.isabs(p):
            return p
        # Se app gira da /opt/videocitofono/app, lo storage sta in
        # /opt/videocitofono/data/... (vicino, non dentro app/).
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            app_root = os.path.dirname(here)        # .../app
            project_root = os.path.dirname(app_root)  # .../videocitofono
            return os.path.join(project_root, p)
        except Exception:
            return p

    def _sanitize_name(self, nome: str) -> str:
        if not nome:
            return ""
        s = nome.strip().replace(" ", "_")
        out = "".join(ch for ch in s if ch.isalnum() or ch in "_-")
        return out[:64]

    def _invalidate_cache(self) -> None:
        try:
            os.remove(os.path.join(self.storage_dir, _CACHE_FN))
        except Exception:
            pass

    def _load_or_build_cache(self) -> Tuple[Optional["np.ndarray"], List[str]]:
        cache_path = os.path.join(self.storage_dir, _CACHE_FN)
        # Cache valida se: esiste E mtime cache > mtime di OGNI file foto
        photos = self._scan_photos()
        if not photos:
            return None, []
        try:
            cache_mtime = os.path.getmtime(cache_path)
            ok = all(os.path.getmtime(p) <= cache_mtime for _, p in photos)
            if ok:
                z = np.load(cache_path, allow_pickle=False)
                encs = z["encodings"]
                names = list(z["names"])
                if len(encs) == len(names) and len(encs) > 0:
                    return encs, names
        except Exception:
            pass
        # Rebuild cache
        return self._build_cache(photos, cache_path)

    def _scan_photos(self) -> List[Tuple[str, str]]:
        """Ritorna lista (nome_persona, path_foto)."""
        out: List[Tuple[str, str]] = []
        try:
            for entry in sorted(os.listdir(self.storage_dir)):
                p = os.path.join(self.storage_dir, entry)
                if not os.path.isdir(p):
                    continue
                for fn in sorted(os.listdir(p)):
                    if os.path.splitext(fn)[1].lower() in _IMG_EXT:
                        out.append((entry, os.path.join(p, fn)))
        except Exception as e:
            LOG.warning("scan_photos err: %s", e)
        return out

    def _build_cache(self, photos: List[Tuple[str, str]], cache_path: str) -> Tuple[Optional["np.ndarray"], List[str]]:
        if not _FR:
            return None, []
        encs_list: List["np.ndarray"] = []
        names_list: List[str] = []
        for nome, path in photos:
            try:
                arr = face_recognition.load_image_file(path)
                # num_jitters=1 e' default; alza per accuratezza extra a costo CPU
                e = face_recognition.face_encodings(arr, num_jitters=1)
                if not e:
                    LOG.warning("Volto non trovato in %s, salto", path)
                    continue
                encs_list.append(e[0])
                names_list.append(nome)
            except Exception as ex:
                LOG.warning("encoding %s err: %s", path, ex)
        if not encs_list:
            return None, []
        encs = np.vstack(encs_list).astype("float32")
        try:
            np.savez(cache_path, encodings=encs, names=np.array(names_list))
        except Exception as e:
            LOG.warning("save cache err: %s", e)
        return encs, names_list


class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *a): return False
