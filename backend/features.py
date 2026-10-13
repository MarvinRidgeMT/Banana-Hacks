"""Five archive features on top of a Cold Case restoration.

1. verify_file      Read a file's Cold Case receipt (C2PA), check the signature still covers
                    the pixels, and match it to the case on record.
2. likeness         Score each AI face guess against a real reference photo of the same person
                    (OpenCV SFace face embeddings; cosine >= 0.363 is OpenCV's same-person bar).
3. (batch mode lives in api.py: it is queueing + a CSV built from `catalog_row`)
4. sidecar_xmp/json Catalog-ready metadata (Dublin Core + IPTC digital source type + our counts).
5. typical_restore  What a whole-image "AI enhance" restorer does to the same scan, and how many
                    undamaged pixels it changes (Cold Case changes 0).
"""
from __future__ import annotations

import hashlib
import io
import json
import time
from pathlib import Path
from xml.sax.saxutils import escape

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
WEIGHTS = HERE.parent / "weights"
YUNET = WEIGHTS / "face_detection_yunet_2023mar.onnx"
SFACE = WEIGHTS / "face_recognition_sface_2021dec.onnx"
SAME_PERSON = 0.363          # OpenCV's published cosine threshold for SFace
RECEIPT_LABEL = "org.chronovisage.edit_manifest"
SITE = "https://cold-case-t1s8.onrender.com"


# --------------------------------------------------------------------------- #
# 1. Verify a file
# --------------------------------------------------------------------------- #
def _mime(data: bytes) -> str:
    fmt = (Image.open(io.BytesIO(data)).format or "PNG").upper()
    return {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "TIFF": "image/tiff"}.get(fmt, "image/png")


def verify_file(data: bytes, cache: Path) -> dict:
    """What the file's receipt says, whether the pixels still match the signature, and which case it is."""
    out: dict = {"has_receipt": False, "valid": False, "tampered": False, "signer_trusted": False,
                 "case_key": None, "fidelity": None, "pixel_summary": None, "stages": [], "issues": []}
    try:  # match it to a case on record by its pixels (works even if the receipt was stripped)
        hit = find_case_by_pixels(pixel_hash(np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))), cache)
    except Exception:
        hit = None
    if hit:
        out["case_key"], out["fidelity"], out["matched_file"] = hit
        out["pixels_match_record"] = True
    try:
        import c2pa
        with c2pa.Reader(_mime(data), io.BytesIO(data)) as r:
            store = json.loads(r.json())
    except Exception as e:  # no manifest at all, or an unreadable one
        msg = str(e)
        out["issues"].append("No Content Credentials in this file." if "ManifestNotFound" in msg or "not found" in msg.lower()
                             else f"Couldn't read Content Credentials: {msg[:160]}")
        if hit:
            out["issues"].append("The receipt was removed, but these pixels exactly match a Cold Case restoration on record.")
        return out
    active = store.get("manifests", {}).get(store.get("active_manifest", ""), {})
    receipt = next((a.get("data") for a in active.get("assertions", []) if a.get("label") == RECEIPT_LABEL), None)
    statuses = store.get("validation_status") or []
    codes = [s.get("code", "") for s in statuses]
    out["validation_codes"] = codes
    out["tampered"] = any("mismatch" in c or "hash" in c and "mismatch" in c for c in codes)
    out["signer_trusted"] = not any("untrusted" in c for c in codes)
    out["has_receipt"] = receipt is not None
    out["valid"] = out["has_receipt"] and not out["tampered"]
    out["claim_generator"] = (active.get("claim_generator_info") or [{}])[0].get("name") or active.get("claim_generator")
    if not receipt:
        out["issues"].append("This file has Content Credentials, but not a Cold Case receipt.")
        return out
    out["pixel_summary"] = receipt.get("pixel_summary")
    out["stages"] = [s.get("stage") for s in receipt.get("stages", []) if isinstance(s, dict)]
    out["kind"] = "color" if "colour" in str(receipt.get("tool", "")).lower() else (
        "document" if "document" in str(receipt.get("tool", "")).lower() else "photo")
    if out["tampered"]:
        out["issues"].append("The pixels were changed after the receipt was signed.")
    if not out["signer_trusted"]:
        out["issues"].append("Signed with our demo certificate, so standard viewers show the signer as untrusted.")
    return out


_px_index: dict[str, tuple[float, str]] = {}


def pixel_hash(rgb: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(rgb).tobytes() + str(rgb.shape).encode()).hexdigest()


def find_case_by_pixels(px: str, cache: Path):
    """Which cached restoration (or color version) has exactly these pixels? Index cached by mtime."""
    for f in list(cache.glob("*/f*/restored.png")) + list(cache.glob("*/f*/color/colorized.png")):
        k = str(f)
        m = f.stat().st_mtime
        if k not in _px_index or _px_index[k][0] != m:
            try:
                _px_index[k] = (m, pixel_hash(np.asarray(Image.open(f).convert("RGB"))))
            except Exception:
                continue
        if _px_index[k][1] == px:
            fid_dir = f.parent if f.parent.name.startswith("f") else f.parent.parent
            key = fid_dir.parent.name
            return key, int(fid_dir.name[1:]) / 100, "color" if "color" in k else "restored"
    return None


# --------------------------------------------------------------------------- #
# 2. Likeness check against a reference photo
# --------------------------------------------------------------------------- #
_models: dict = {}


def _sface():
    if "rec" not in _models:
        if not SFACE.exists():  # 37 MB, Apache-2.0, from the OpenCV model zoo
            import urllib.request
            SFACE.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve("https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/"
                                       "face_recognition_sface_2021dec.onnx", SFACE)
        _models["rec"] = cv2.FaceRecognizerSF.create(str(SFACE), "")
    return _models["rec"]


def _detect(bgr: np.ndarray, score: float = 0.5):
    h, w = bgr.shape[:2]
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (w, h), score, 0.3, 50)
    _, faces = det.detect(bgr)
    if faces is None or len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])  # the largest face


def embed_face(rgb: np.ndarray, allow_unaligned: bool = False) -> tuple[np.ndarray | None, str]:
    """SFace embedding of the main face. Upscales small crops so the detector finds the face."""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    s = max(1.0, 320 / max(bgr.shape[:2]))
    if s > 1:
        bgr = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    for score in (0.6, 0.4, 0.25):
        f = _detect(bgr, score)
        if f is not None:
            aligned = _sface().alignCrop(bgr, f)
            return _sface().feature(aligned).flatten(), "aligned"
    if allow_unaligned:
        return _sface().feature(cv2.resize(bgr, (112, 112))).flatten(), "unaligned"
    return None, "no face found"


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def likeness(reference_rgb: np.ndarray, candidates: list[tuple[str, np.ndarray]]) -> dict:
    """Score each candidate face (name, RGB crop) against the reference person."""
    ref, how = embed_face(reference_rgb)
    if ref is None:
        raise ValueError("No face was found in the reference photo. Use a clear, front-facing photo of the same person.")
    scores = []
    for name, rgb in candidates:
        emb, how_c = embed_face(rgb, allow_unaligned=True)
        sim = cosine(ref, emb)
        scores.append({"name": name, "similarity": round(sim, 3), "same_person": sim >= SAME_PERSON, "method": how_c})
    best = max(scores, key=lambda s: s["similarity"]) if scores else None
    verdict = ("none" if not best or not best["same_person"] else best["name"])
    return {"model": "OpenCV SFace (2021dec) + YuNet", "threshold": SAME_PERSON, "scores": scores,
            "best": best["name"] if best else None, "verdict": verdict}


# --------------------------------------------------------------------------- #
# 4. Catalog metadata
# --------------------------------------------------------------------------- #
def catalog_row(key: str, result: dict | None, source: dict, color: dict | None = None) -> dict:
    s = (result or {}).get("pixel_summary") or {}
    manifest_file = None
    if result:
        manifest_file = (result.get("files") or {}).get("manifest")
    return {
        "case": key,
        "filename": source.get("filename", ""),
        "kind": source.get("kind", "photo"),
        "source_sha256": source.get("sha256", ""),
        "real_pct": round(100 * s.get("observed", 0), 2) if result else "",
        "rebuilt_pct": round(100 * s.get("inferred", 0), 2) if result else "",
        "invented_pct": round(100 * s.get("invented", 0), 2) if result else "",
        "fidelity": result.get("fidelity") if result else "",
        "mask_source": result.get("mask_source", "") if result else "",
        "receipt_file": manifest_file or "",
        "case_url": f"{SITE}/#/p/{key}/{(result or {}).get('fidelity', 0.7)}",
        "color_guess_pct": round(100 * color["pixel_summary"]["invented"], 2) if color else "",
    }


def sidecar_json(row: dict) -> dict:
    return {
        "dc:title": row["filename"],
        "dc:description": (f"Digitally restored with Cold Case. Real {row['real_pct']}%, rebuilt {row['rebuilt_pct']}%, "
                           f"invented {row['invented_pct']}% of pixels. Invented areas are guesses, not recoveries."),
        "dc:source": f"sha256:{row['source_sha256']}",
        "dc:relation": row["case_url"],
        "dc:type": "StillImage",
        "Iptc4xmpExt:DigitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia",
        "coldcase:realPercent": row["real_pct"],
        "coldcase:rebuiltPercent": row["rebuilt_pct"],
        "coldcase:inventedPercent": row["invented_pct"],
        "coldcase:faceFidelity": row["fidelity"],
        "coldcase:maskSource": row["mask_source"],
        "coldcase:colorGuessPercent": row["color_guess_pct"],
    }


def sidecar_xmp(row: dict) -> str:
    j = sidecar_json(row)
    e = lambda v: escape(str(v))
    return f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
    xmlns:coldcase="https://cold-case-t1s8.onrender.com/ns/1.0/"
    Iptc4xmpExt:DigitalSourceType="{e(j['Iptc4xmpExt:DigitalSourceType'])}"
    coldcase:realPercent="{e(j['coldcase:realPercent'])}"
    coldcase:rebuiltPercent="{e(j['coldcase:rebuiltPercent'])}"
    coldcase:inventedPercent="{e(j['coldcase:inventedPercent'])}"
    coldcase:faceFidelity="{e(j['coldcase:faceFidelity'])}"
    coldcase:maskSource="{e(j['coldcase:maskSource'])}"
    coldcase:colorGuessPercent="{e(j['coldcase:colorGuessPercent'])}">
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{e(j['dc:title'])}</rdf:li></rdf:Alt></dc:title>
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{e(j['dc:description'])}</rdf:li></rdf:Alt></dc:description>
   <dc:source>{e(j['dc:source'])}</dc:source>
   <dc:relation><rdf:Bag><rdf:li>{e(j['dc:relation'])}</rdf:li></rdf:Bag></dc:relation>
   <dc:type><rdf:Bag><rdf:li>StillImage</rdf:li></rdf:Bag></dc:type>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""


# --------------------------------------------------------------------------- #
# 5. What a typical whole-image restorer does
# --------------------------------------------------------------------------- #
def typical_restore(original: np.ndarray, damaged: np.ndarray, out_dir: Path, face_pass=None) -> dict:
    """face_pass: pipeline.codeformer.restore_face (512x512 RGB in, out), or None to skip faces."""
    """A representative whole-image "AI enhance" pass: fill the damage, denoise and sharpen the
    whole frame, and run face restoration on every face (not just damaged pixels).
    Returns how many UNDAMAGED pixels it changed; Cold Case changes 0 by construction (tested)."""
    meta_file = out_dir / "compare.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text())
    t0 = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    img = original.copy()
    if damaged.shape != img.shape[:2]:
        damaged = cv2.resize(damaged.astype(np.uint8), (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    filled = cv2.inpaint(img, damaged.astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
    bgr = cv2.cvtColor(filled, cv2.COLOR_RGB2BGR)
    den = cv2.fastNlMeansDenoisingColored(bgr, None, 6, 6, 7, 21)
    blur = cv2.GaussianBlur(den, (0, 0), 1.2)
    sharp = cv2.addWeighted(den, 1.6, blur, -0.6, 0)
    typical = cv2.cvtColor(sharp, cv2.COLOR_BGR2RGB)
    faces_done = 0
    if face_pass is not None:
        from pipeline.faces import detect_faces
        boxes = detect_faces(typical, score=0.5)
        for b in boxes:   # face restoration pasted back with a soft feathered edge, as consumer apps do
            x, y, w, h = [int(v) for v in b[:4]]
            H, W = typical.shape[:2]
            p = int(0.25 * max(w, h))
            x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
            crop = typical[y0:y1, x0:x1]
            fixed = face_pass(cv2.resize(crop, (512, 512), interpolation=cv2.INTER_LANCZOS4), 0.5)
            fixed = cv2.resize(fixed, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
            alpha = np.zeros((y1 - y0, x1 - x0), np.float32)
            cv2.ellipse(alpha, ((x1 - x0) // 2, (y1 - y0) // 2), (max(1, w // 2), max(1, int(h * 0.6))), 0, 0, 360, 1, -1)
            alpha = cv2.GaussianBlur(alpha, (0, 0), max(3, w / 12))[..., None]
            typical[y0:y1, x0:x1] = (alpha * fixed + (1 - alpha) * crop).round().clip(0, 255).astype(np.uint8)
            faces_done += 1
    diff = np.abs(typical.astype(np.int16) - original.astype(np.int16)).max(axis=-1)
    changed = diff > 3                      # more than sensor noise / rounding
    undamaged = ~damaged
    n_und = int(undamaged.sum())
    changed_und = int((changed & undamaged).sum())
    lab_o = cv2.cvtColor(original, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab_t = cv2.cvtColor(typical, cv2.COLOR_RGB2LAB).astype(np.float32)
    de = np.sqrt(((lab_o - lab_t) ** 2).sum(-1))
    Image.fromarray(typical).save(out_dir / "typical.png")
    overlay = np.zeros(original.shape[:2] + (4,), np.uint8)
    overlay[changed & undamaged] = (179, 38, 30, 190)    # changed though nothing was damaged
    overlay[damaged] = (44, 90, 160, 120)                 # the damage both tools fill
    Image.fromarray(overlay).save(out_dir / "changed.png")
    rel = out_dir.parent.name + "/" + out_dir.name
    meta = {
        "files": {"typical": f"{rel}/typical.png", "changed": f"{rel}/changed.png"},
        "method": "Telea fill + non-local-means denoise + unsharp mask over the whole frame"
                  + (" + CodeFormer on every face, feathered paste" if faces_done else ""),
        "faces_restored": faces_done,
        "undamaged_pixels": n_und,
        "undamaged_changed": changed_und,
        "undamaged_changed_pct": round(100 * changed_und / max(1, n_und), 2),
        "mean_delta_e_undamaged": round(float(de[undamaged].mean()), 2),
        "cold_case_undamaged_changed": 0,
        "seconds": round(time.perf_counter() - t0, 2),
    }
    meta_file.write_text(json.dumps(meta, indent=2))
    return meta


def receipt_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
