"""Adapter between the web API and Person A's pipeline (backend/pipeline/restore.py).

Everything the website needs from restore() passes through this file, so if the
pipeline's output changes, this is the only Python file to touch.

restore(path, fidelity=w) returns a dict; the keys used here:
  restored          HxWx3 uint8, the displayed seed after face restoration
  original          the photo as the pipeline saw it (possibly resized), pixel-aligned
  label             HxW, 0 observed / 1 inferred / 2 invented
  pixel_summary     share per class (checked against label)
  regions           damaged regions; face_regions for faces (with invented_fraction)
  pre_face_outputs  every seed before CodeFormer, for "faces that could have been"
  damage_mask       what the segmenter (or the mask file) marked as damaged
  mask_source       "provided mask file" or the segmenter's model name
  displayed_seed
The manifest comes from pipeline.manifest.build_manifest(result) and the signed
copy from pipeline.c2pa_embed.embed(), exactly as restore.py's __main__ does.
A <name>_mask.png / <name>_faces.json next to the image is used when present.

Overrides (environment variables), in case something differs at 3 a.m.:
  CV_LABELS   label values for observed,inferred,invented   default "0,1,2"
  CV_BBOX     force bbox format "xyxy" or "xywh"             default: detected
  CV_PIPELINE "stub" runs the fake pipeline in dev/ for UI work without a GPU
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

OBSERVED, INFERRED, INVENTED = 0, 1, 2

# Demo photos are rendered with 8 seeds (as in training/render_demo.py);
# live uploads use restore()'s own default (4 seeds, about 3-4 min per photo).
DEMO_SEEDS = (11, 12, 13, 14, 15, 16, 17, 18)
CLASS_NAMES = {OBSERVED: "observed", INFERRED: "inferred", INVENTED: "invented"}

# Colours for the downloadable map.png (the deck's Real / Rebuilt / Invented).
# The website draws its own overlay from regions.png with the same colours.
MAP_RGBA = {
    OBSERVED: (154, 146, 130, 0),    # Real: clear
    INFERRED: (44, 90, 160, 175),    # Rebuilt: blue
    INVENTED: (179, 38, 30, 205),    # Invented: red (pink hatching below)
}

MIN_REGION_PX = 20  # specks smaller than this get no region id (class is still shown)


# --------------------------------------------------------------------------- #
# Loading the pipeline
# --------------------------------------------------------------------------- #
_restore_fn = None


# Bump when the restoration output changes (6: seamless membrane blending), so cached results re-render.
RENDER_VERSION = 6


def pipeline_name() -> str:
    return "stub" if os.environ.get("CV_PIPELINE") == "stub" else "real"


def get_restore():
    """Import restore() lazily, so the API can start (and serve the cache) even
    while the pipeline is broken or still loading models."""
    global _restore_fn
    if _restore_fn is None:
        if pipeline_name() == "stub":
            from dev.stub_pipeline import restore
        else:
            from pipeline.restore import restore
        _restore_fn = restore
    return _restore_fn


def label_values() -> tuple[int, int, int]:
    raw = os.environ.get("CV_LABELS", "0,1,2")
    vals = tuple(int(v) for v in raw.split(","))
    if len(vals) != 3:
        raise ValueError("CV_LABELS must be three numbers: observed,inferred,invented")
    return vals  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Converting whatever restore() returns into plain arrays
# --------------------------------------------------------------------------- #
def _load_any_image(x: Any) -> Image.Image:
    if isinstance(x, Image.Image):
        return x
    if isinstance(x, (str, Path)):
        return Image.open(x)
    if isinstance(x, np.ndarray):
        return Image.fromarray(x)
    raise TypeError(f"Can't read an image from {type(x).__name__}")


def to_rgb_uint8(x: Any) -> np.ndarray:
    """RGB array as uint8 HxWx3, from uint8 0-255, float 0-1, float 0-255,
    grayscale, RGBA, a PIL image or a file path."""
    if not isinstance(x, np.ndarray):
        return np.asarray(_load_any_image(x).convert("RGB"))
    arr = x
    if arr.dtype != np.uint8:
        arr = arr.astype(np.float64)
        scale = 255.0 if np.nanmax(arr) <= 1.0 + 1e-6 else 1.0
        arr = np.clip(np.nan_to_num(arr) * scale, 0, 255).round().astype(np.uint8)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    elif arr.ndim == 3 and arr.shape[2] == 1:
        arr = np.repeat(arr, 3, axis=2)
    elif arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[:, :, :3]
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"'restored' has an unexpected shape {x.shape}")
    return np.ascontiguousarray(arr)


def to_label(x: Any, size_wh: tuple[int, int], warnings: list[str]) -> np.ndarray:
    """Label map as uint8 HxW with values 0/1/2, resized to the output size."""
    if isinstance(x, np.ndarray):
        lab = x
    else:
        lab = np.asarray(_load_any_image(x))
    if lab.ndim == 3:  # a label saved as an RGB PNG: every channel is the same
        lab = lab[:, :, 0]
    lab = np.asarray(lab)
    if lab.dtype.kind == "f":
        lab = np.rint(lab)
    lab = lab.astype(np.int64)

    obs, inf, inv = label_values()
    present = set(np.unique(lab).tolist())
    if present <= {obs, inf, inv}:
        out = np.full(lab.shape, OBSERVED, dtype=np.uint8)
        out[lab == inf] = INFERRED
        out[lab == inv] = INVENTED
    elif len(present) <= 3:
        # e.g. a PNG saved as 0 / 127 / 255 for visibility: keep the order
        ordered = sorted(present)
        warnings.append(
            f"label values {ordered} are not {[obs, inf, inv]}; mapped them in order "
            "(lowest = observed). Set CV_LABELS if that is wrong."
        )
        out = np.zeros(lab.shape, dtype=np.uint8)
        for cls, v in enumerate(ordered):
            out[lab == v] = cls
    else:
        raise ValueError(
            f"label has {len(present)} distinct values; expected 3 classes. "
            "Is 'label' the per-pixel class map?"
        )

    w, h = size_wh
    if out.shape != (h, w):
        warnings.append(f"label was {out.shape[1]}x{out.shape[0]}, resized to {w}x{h} (nearest)")
        out = np.asarray(Image.fromarray(out).resize((w, h), Image.NEAREST))
    return out


def to_json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist() if obj.size <= 64 else f"<array {obj.shape} {obj.dtype}>"
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Image.Image):
        return f"<image {obj.size[0]}x{obj.size[1]}>"
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


# --------------------------------------------------------------------------- #
# Regions
# --------------------------------------------------------------------------- #
def _box4(raw: Any) -> list[float] | None:
    try:
        b = [float(v) for v in list(raw)[:4]]
    except (TypeError, ValueError):
        return None
    return b if len(b) == 4 else None


def detect_bbox_format(boxes: list[list[float]], size_wh: tuple[int, int]) -> tuple[str, str]:
    """Work out whether boxes are [x0, y0, x1, y1] or [x, y, w, h].

    Some boxes prove it: a second corner left of / above the first can only be
    xywh, and x + w past the image edge can only be xyxy. CV_BBOX overrides.
    Returns (format, how it was decided).
    """
    forced = os.environ.get("CV_BBOX")
    if forced in ("xyxy", "xywh"):
        return forced, "set by CV_BBOX"
    w, h = size_wh
    for b in boxes:
        if b[2] <= b[0] or b[3] <= b[1]:
            return "xywh", "a box's width/height was smaller than its x/y"
    for b in boxes:
        if b[0] + b[2] > w + 1 or b[1] + b[3] > h + 1:
            return "xyxy", "a box's x + w would run off the image"
    return "xywh", "no box settled it; assumed xywh (Person A confirmed [x, y, w, h])"


def _bbox_xyxy(b: list[float] | None, size_wh: tuple[int, int], fmt: str) -> list[int] | None:
    if b is None:
        return None
    if fmt == "xywh":
        b = [b[0], b[1], b[0] + b[2], b[1] + b[3]]
    w, h = size_wh
    x0, y0, x1, y1 = b
    x0, x1 = sorted((max(0, min(w, x0)), max(0, min(w, x1))))
    y0, y1 = sorted((max(0, min(h, y0)), max(0, min(h, y1))))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return [int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))]


def normalise_pipeline_regions(result: dict, size_wh: tuple[int, int],
                               warnings: list[str] | None = None) -> list[dict]:
    """Person A's regions and face_regions, in one consistent shape."""
    raw: list[tuple[str, str, int, dict]] = []
    for source_key, default_kind in (("regions", "damage"), ("face_regions", "face")):
        items = result.get(source_key) or []
        if isinstance(items, dict):
            items = list(items.values())
        raw += [(source_key, default_kind, i, r) for i, r in enumerate(items) if isinstance(r, dict)]

    boxes = [b for *_, r in raw if (b := _box4(r.get("bbox") or r.get("box"))) is not None]
    fmt, why = detect_bbox_format(boxes, size_wh)
    if warnings is not None and boxes and why.startswith("no box"):
        warnings.append("bbox format not provable from these boxes; assumed [x, y, w, h] as Person A specified (set CV_BBOX=xyxy if wrong)")

    out: list[dict] = []
    for source_key, default_kind, i, r in raw:
        conf = r.get("confidence", r.get("conf"))
        if not isinstance(conf, (int, float, np.generic)) and isinstance(r.get("invented_fraction"), (int, float, np.generic)):
            conf = 1.0 - float(r["invented_fraction"])  # the game plan's rule: 1 - invented / changed
        out.append({
            "source": source_key,
            "id": r.get("id", i + 1),
            "kind": str(r.get("kind") or r.get("type") or default_kind),
            "confidence": float(conf) if isinstance(conf, (int, float, np.generic)) else None,
            "stage": r.get("stage") or r.get("changed_by"),
            "bbox": _bbox_xyxy(_box4(r.get("bbox") or r.get("box")), size_wh, fmt),
            "raw_bbox": to_json_safe(r.get("bbox") or r.get("box")),
            "extra": to_json_safe({k: v for k, v in r.items()
                                   if k not in {"id", "kind", "type", "confidence",
                                                "conf", "stage", "changed_by", "bbox",
                                                "box", "mask"}}),
        })
    return out


def _overlap(a: list[int], b: list[int]) -> float:
    """Share of box a covered by box b."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    return ix * iy / area


def build_regions(label: np.ndarray, pipeline_regions: list[dict]) -> tuple[np.ndarray, list[dict]]:
    """Connected regions of changed pixels, each matched to the pipeline region
    that covers it best (for kind, confidence and stage).

    Returns an HxW uint16 id map (0 = no region) and the region list.
    Confidence uses the game plan's rule: 1 - invented / changed pixels.
    """
    changed = label != OBSERVED
    comp, n = ndimage.label(changed, structure=np.ones((3, 3), dtype=bool))
    ids = np.zeros(label.shape, dtype=np.uint16)
    regions: list[dict] = []
    if n == 0:
        return ids, regions

    objects = ndimage.find_objects(comp)
    counts_inv = ndimage.sum(label == INVENTED, comp, index=np.arange(1, n + 1))
    counts_all = ndimage.sum(changed, comp, index=np.arange(1, n + 1))

    # Biggest first, so if there are more than 65,535 regions only specks lose ids.
    order = np.argsort(-counts_all)
    next_id = 1
    for idx in order:
        area = int(counts_all[idx])
        if area < MIN_REGION_PX or next_id > 65535:
            continue
        sl = objects[idx]
        bbox = [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop]
        invented = int(counts_inv[idx])
        computed_conf = 1.0 - invented / area

        best, best_score = None, 0.0
        for pr in pipeline_regions:
            if pr["bbox"] is None:
                continue
            score = _overlap(bbox, pr["bbox"])
            # faces win ties: a face box inside a damage box is the more specific match
            if pr["kind"] == "face":
                score += 1e-3
            if score > best_score:
                best, best_score = pr, score
        if best_score < 0.3:
            best = None

        ids[comp == idx + 1] = next_id
        regions.append({
            "id": next_id,
            "bbox": [int(v) for v in bbox],
            "area_px": area,
            "inferred_px": area - invented,
            "invented_px": invented,
            "kind": best["kind"] if best else "damage",
            "stage": (best or {}).get("stage") or ("face_restoration" if best and best["kind"] == "face" else "inpainting"),
            "confidence": best["confidence"] if best and best["confidence"] is not None else round(computed_conf, 4),
            "confidence_computed": round(computed_conf, 4),
            "pipeline_region_id": best["id"] if best else None,
        })
        next_id += 1
    return ids, regions


def regions_png(ids: np.ndarray, label: np.ndarray) -> Image.Image:
    """R,G = region id (little-endian 16-bit), B = class. The website reads this
    one image to draw the map and to answer 'what is under the cursor?'."""
    rgb = np.zeros((*label.shape, 3), dtype=np.uint8)
    rgb[:, :, 0] = (ids & 0xFF).astype(np.uint8)
    rgb[:, :, 1] = (ids >> 8).astype(np.uint8)
    rgb[:, :, 2] = label
    return Image.fromarray(rgb, mode="RGB")


def map_png(label: np.ndarray) -> Image.Image:
    """Coloured, hatched map for download and for tools other than our site."""
    h, w = label.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for cls, colour in MAP_RGBA.items():
        rgba[label == cls] = colour
    yy, xx = np.mgrid[0:h, 0:w]
    stripes = ((xx + yy) % 12) < 3
    rgba[(label == INVENTED) & stripes] = (231, 183, 177, 225)
    return Image.fromarray(rgba, mode="RGBA")


def summary_from_label(label: np.ndarray) -> dict[str, float]:
    total = label.size or 1
    return {name: float((label == cls).sum()) / total for cls, name in CLASS_NAMES.items()}


def normalise_summary(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    vals = {}
    for name in CLASS_NAMES.values():
        v = raw.get(name, raw.get(name.capitalize()))
        if isinstance(v, (int, float, np.generic)):
            vals[name] = float(v)
    if len(vals) != 3:
        return None
    total = sum(vals.values())
    if total > 1.5:  # counts or percentages -> fractions
        vals = {k: v / total for k, v in vals.items()}
    return vals


# --------------------------------------------------------------------------- #
# Faces, manifest, signing
# --------------------------------------------------------------------------- #
FACE_KEYS = ("faces", "face_variants", "alt_faces", "faces_could_have_been", "alternate_faces")


def _explicit_faces(result: dict) -> list[tuple[Any, dict]]:
    """Ready-made alternate faces, if the pipeline ever returns them directly."""
    for key in FACE_KEYS:
        items = result.get(key)
        if not items:
            continue
        if isinstance(items, dict):
            items = list(items.values())
        faces = []
        for item in items:
            if isinstance(item, dict):
                img = item.get("image", item.get("path", item.get("face")))
                meta = {k: to_json_safe(v) for k, v in item.items() if k not in {"image", "path", "face"}}
            else:
                img, meta = item, {}
            if img is not None:
                faces.append((img, meta))
        return faces
    return []


def _most_different(crops: list[np.ndarray], k: int = 3) -> list[int]:
    """Fallback pick: start from the run closest to the others, then keep adding
    the run furthest from everything already picked."""
    n = len(crops)
    flat = [c.astype(np.float32).ravel() for c in crops]
    d = np.array([[np.abs(a - b).mean() for b in flat] for a in flat])
    picked = [int(np.argmin(d.sum(1)))]
    while len(picked) < min(k, n):
        rest = [i for i in range(n) if i not in picked]
        picked.append(max(rest, key=lambda i: min(d[i, j] for j in picked)))
    return picked


def alternate_faces(result: dict, regions: list[dict], warnings: list[str]) -> tuple[list[tuple[np.ndarray, dict]], list[int] | None]:
    """The three 'faces that could have been', as the pipeline's own script makes
    them: crops of the face with the most invention, taken from the seed outputs
    *before* face restoration (CodeFormer would hide the disagreement).

    Returns [(face, meta)], and the face box used (xyxy, output coordinates).
    """
    explicit = _explicit_faces(result)
    face_regions = [r for r in regions if r["kind"] == "face" and r["bbox"]]
    best = max(face_regions, key=lambda r: (r["extra"].get("invented_fraction") or 0,
                                            (r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1])),
               default=None)
    if explicit:
        return [(to_rgb_uint8(img), meta) for img, meta in explicit], best["bbox"] if best else None

    runs = result.get("pre_face_outputs") or result.get("seed_outputs")
    if best is None or runs is None or len(runs) < 2:
        return [], None
    if not (best["extra"].get("invented_fraction") or 0) > 0 and "invented_fraction" in best["extra"]:
        return [], None  # nothing about this face was invented, so there is nothing to compare

    x0, y0, x1, y1 = best["bbox"]
    crops = [to_rgb_uint8(r)[y0:y1, x0:x1] for r in runs]
    idx = None
    if pipeline_name() == "real":
        try:
            from pipeline.faces import faces_that_could_have_been
            _, idx = faces_that_could_have_been(runs, best["raw_bbox"])
            idx = [int(i) for i in list(idx)]
        except Exception as e:
            warnings.append(f"faces_that_could_have_been() failed ({type(e).__name__}: {e}); picked the 3 most different runs instead")
    if not idx:
        idx = _most_different(crops)
    faces = [(crops[i], {"run": i}) for i in idx[:3]]
    return faces, best["bbox"]


DOC_WEIGHTS = "weights/seg_doc_best.pth"


def propose_mask(image_path: Path, kind: str = "photo") -> Path:
    """Run only the damage segmenter on an uploaded photo, so a person can review and
    correct the mask before restoring (the mask is the biggest quality lever).
    Segments a 1024 px copy, like the pipeline, then widens the result by 2 px so
    thin cracks are fully covered. Saved as proposed_mask.png next to the photo."""
    out = image_path.parent / "proposed_mask.png"
    if out.exists():
        return out
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    if pipeline_name() == "stub":
        m = np.zeros((H, W), bool)
    else:
        from pipeline.segment import segment
        k = min(1.0, 1024 / max(W, H))
        small = img.resize((max(1, round(W * k)), max(1, round(H * k))), Image.LANCZOS) if k < 1 else img
        ms, _ = segment(np.asarray(small), weights=DOC_WEIGHTS if kind == "document" else None)
        ms = ndimage.binary_dilation(ms, iterations=2)
        m = np.asarray(Image.fromarray(ms.astype(np.uint8) * 255, mode="L").resize((W, H), Image.NEAREST)) > 127
    Image.fromarray(m.astype(np.uint8) * 255, mode="L").save(out)
    return out


def document_restore(image_path: Path) -> dict:
    """Document mode: our document damage detector + classical fill (OpenCV Telea) ONLY.
    No diffusion model runs, so no letters are ever generated. Filled paper is labelled
    Rebuilt; damaged areas that touch ink (text was probably lost there) are labelled
    Invented, as a warning that the blank fill is not the original text."""
    import cv2
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    k = min(1.0, 1024 / max(W, H))
    if k < 1:
        img = img.resize((round(W * k), round(H * k)), Image.LANCZOS)
    orig = np.asarray(img).copy()
    h, w = orig.shape[:2]
    mask_file = image_path.with_name(image_path.stem + "_mask.png")
    if mask_file.exists():
        mask = np.asarray(Image.open(mask_file).convert("L").resize((w, h), Image.NEAREST)) > 127
        mask_source = "provided mask file"
    else:
        from pipeline.segment import segment
        mask, _ = segment(orig, weights=DOC_WEIGHTS)
        mask = ndimage.binary_dilation(mask, iterations=2)
        mask_source = "seg_doc_best (document detector)"
    bgr = cv2.cvtColor(orig, cv2.COLOR_RGB2BGR)
    filled = cv2.inpaint(bgr, mask.astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
    restored = cv2.cvtColor(filled, cv2.COLOR_BGR2RGB)
    restored[~mask] = orig[~mask]                     # untouched pixels stay byte for byte
    gray = cv2.cvtColor(orig, cv2.COLOR_RGB2GRAY).astype(np.float32)
    paper = float(np.median(gray[~mask])) if (~mask).any() else 230.0
    ink = (gray < paper * 0.62) & ~mask
    # Where is there text nearby? Local ink density from the undamaged pixels around each spot.
    win = max(9, int(round(min(h, w) / 45)))
    seen = ndimage.uniform_filter((~mask).astype(np.float32), win)
    density = ndimage.uniform_filter(ink.astype(np.float32), win) / np.maximum(seen, 1e-3)
    text_area = density > 0.035
    label = np.zeros((h, w), np.uint8)
    label[mask] = 1
    label[mask & text_area] = 2
    comps, n = ndimage.label(mask)
    text_lost = int(len(np.unique(comps[mask & text_area])))
    changed_outside = int((restored[~mask] != orig[~mask]).any(axis=-1).sum())
    summary = {"observed": float((label == 0).mean()), "inferred": float((label == 1).mean()),
               "invented": float((label == 2).mean())}
    manifest = {
        "tool": "Cold Case, document mode",
        "working_copy": {"width": w, "height": h, "scale": round(k, 4)},
        "stages": [
            {"stage": "damage_segmentation", "model": mask_source},
            {"stage": "classical_fill", "method": "OpenCV Telea inpainting, radius 3",
             "generated_text": False, "diffusion_model_used": False},
            {"stage": "labels", "rule": "fill touching ink (text probably lost) = Invented; other fill = Rebuilt",
             "damaged_areas": int(n), "areas_touching_text": text_lost},
        ],
        "pixel_summary": {k2: round(v, 6) for k2, v in summary.items()},
        "untouched_pixel_check": {"changed_outside_mask": changed_outside},
    }
    return {"original": orig, "restored": restored, "label": label, "damage_mask": mask,
            "mask_source": mask_source, "pixel_summary": summary, "manifest": manifest,
            "regions": [], "face_regions": []}


def load_manifest(result: dict) -> dict | None:
    m = result.get("manifest")
    if isinstance(m, dict):
        return to_json_safe(m)
    for key in ("manifest", "manifest_path"):
        p = result.get(key)
        if isinstance(p, (str, Path)) and Path(p).is_file():
            return json.loads(Path(p).read_text())
    if pipeline_name() == "real":
        from pipeline.manifest import build_manifest  # Person A's manifest builder
        return to_json_safe(build_manifest(result))
    return None


def find_signed(result: dict) -> Path | None:
    for key in ("signed_path", "c2pa_path", "signed", "signed_image"):
        p = result.get(key)
        if isinstance(p, (str, Path)) and Path(p).is_file():
            return Path(p)
    return None


def sign_c2pa(src: Path, dst: Path, manifest: dict) -> None:
    """Embed the manifest with Person A's c2pa_embed (self-signed test cert)."""
    from pipeline.c2pa_embed import embed
    embed(src, dst, manifest)


# --------------------------------------------------------------------------- #
# The one function the API calls
# --------------------------------------------------------------------------- #
def fidelity_dir(folder: Path, fidelity: float) -> Path:
    return folder / f"f{int(round(fidelity * 100)):03d}"


def _save_mask(x: Any, path: Path) -> None:
    m = x if isinstance(x, np.ndarray) else np.asarray(_load_any_image(x).convert("L"))
    if m.ndim == 3:
        m = m[:, :, 0]
    m = (m > 0.5) if m.dtype == bool or (m.dtype.kind == "f" and m.max() <= 1) else (m > 127)
    Image.fromarray(m.astype(np.uint8) * 255, mode="L").save(path)


def run_restore(image_path: Path, fidelity: float, source: dict,
                seeds: tuple[int, ...] | None = None) -> dict:
    """Run restore() once for this image and fidelity, write every artifact the
    site needs into the cache, and return the result JSON (also saved to disk).

    `source` is the record written when the image was ingested
    (sha256, mask_source, original filename, ...).
    """
    out = fidelity_dir(image_path.parent, fidelity)
    result_file = out / "result.json"
    if result_file.exists():
        cached = json.loads(result_file.read_text())
        if cached.get("pipeline", "stub") == pipeline_name() and cached.get("render_version") == RENDER_VERSION:
            return cached
        shutil.rmtree(out, ignore_errors=True)  # made by the other pipeline: redo it

    t0 = time.perf_counter()
    kwargs: dict[str, Any] = {}
    if source.get("kind") == "document" and pipeline_name() == "real":
        result = document_restore(image_path)
        fidelity_applied = True
    else:
        restore = get_restore()
        params = inspect.signature(restore).parameters
        fidelity_applied = "fidelity" in params
        if fidelity_applied:
            kwargs["fidelity"] = fidelity
        if seeds and "seeds" in params:
            kwargs["seeds"] = tuple(seeds)
        result = restore(str(image_path), **kwargs)
    seconds = time.perf_counter() - t0

    if not isinstance(result, dict):
        raise TypeError(f"restore() returned {type(result).__name__}, expected a dict")
    if "restored" not in result:
        raise KeyError(f"restore() result has no 'restored' key (keys: {sorted(result)})")

    warnings: list[str] = []
    seeds_used = len(kwargs["seeds"]) if "seeds" in kwargs else (len(result.get("seed_outputs") or []) or None)
    if not fidelity_applied:
        warnings.append("restore() has no fidelity argument; all fidelity steps are the same image")

    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "faces").mkdir(parents=True)

    restored = to_rgb_uint8(result["restored"])
    h, w = restored.shape[:2]
    Image.fromarray(restored, mode="RGB").save(tmp / "restored.png")

    # The pipeline may work on a resized copy ("scale"); its own "original" is
    # pixel-aligned with "restored", so the slider uses that one.
    if result.get("original") is not None:
        original = to_rgb_uint8(result["original"])
        if original.shape[:2] != (h, w):
            warnings.append(f"pipeline 'original' is {original.shape[1]}x{original.shape[0]} but "
                            f"'restored' is {w}x{h}; the slider stretches them to match")
        Image.fromarray(original, mode="RGB").save(tmp / "original.png")
        original_file = f"{out.name}/original.png"
    else:
        with Image.open(image_path) as src:
            original = np.asarray(src.convert("RGB").resize((w, h), Image.LANCZOS))
        original_file = "input.png"

    if result.get("label") is not None:
        label = to_label(result["label"], (w, h), warnings)
    else:
        warnings.append("restore() returned no 'label'; the map shows everything as observed")
        label = np.zeros((h, w), dtype=np.uint8)

    Image.fromarray(label, mode="L").save(tmp / "label.png")     # 0/1/2, for other tools
    map_png(label).save(tmp / "map.png")
    pipeline_regions = normalise_pipeline_regions(result, (w, h), warnings)
    ids, regions = build_regions(label, pipeline_regions)
    regions_png(ids, label).save(tmp / "regions.png")

    computed_summary = summary_from_label(label)
    pipeline_summary = normalise_summary(result.get("pixel_summary"))
    if pipeline_summary:
        drift = max(abs(pipeline_summary[k] - computed_summary[k]) for k in computed_summary)
        if drift > 0.01:
            warnings.append(
                f"pipeline pixel_summary differs from the label map by up to {drift:.1%}; "
                "the legend uses the label map so it matches what is drawn"
            )

    faces_out = []
    face_box = None
    try:
        faces, face_box = alternate_faces(result, pipeline_regions, warnings)
        for i, (img, meta) in enumerate(faces):
            name = f"faces/face_{i + 1}.png"
            Image.fromarray(to_rgb_uint8(img)).save(tmp / name)
            faces_out.append({"file": name, "meta": meta})
    except Exception as e:  # the faces tab is extra; never lose the restoration over it
        warnings.append(f"alternate faces failed: {type(e).__name__}: {e}")
    face_crop = None
    if faces_out and face_box:
        x0, y0, x1, y1 = face_box
        Image.fromarray(original[y0:y1, x0:x1]).save(tmp / "faces/original_crop.png")
        face_crop = "faces/original_crop.png"

    mask_file = image_path.with_name(image_path.stem + "_mask.png")
    found_mask = result.get("damage_mask", result.get("mask"))
    try:
        if mask_file.exists():
            shutil.copyfile(mask_file, tmp / "mask.png")
        elif found_mask is not None:
            _save_mask(found_mask, tmp / "mask.png")
    except Exception as e:
        warnings.append(f"mask could not be saved: {type(e).__name__}: {e}")

    try:
        pipeline_manifest = load_manifest(result)
    except Exception as e:
        warnings.append(f"build_manifest() failed: {type(e).__name__}: {e}")
        pipeline_manifest = None

    signed_name = None
    signed = find_signed(result)
    if signed:
        signed_name = "restored_signed" + signed.suffix.lower()
        shutil.copyfile(signed, tmp / signed_name)
    elif pipeline_name() == "real" and pipeline_manifest:
        try:
            sign_c2pa(tmp / "restored.png", tmp / "restored_c2pa.png", pipeline_manifest)
            signed_name = "restored_c2pa.png"
        except Exception as e:
            warnings.append(f"C2PA signing failed: {type(e).__name__}: {e}")

    human_mask = source.get("mask_source") in {"human_file", "human_brush"}
    manifest = json.loads(json.dumps(pipeline_manifest)) if pipeline_manifest else {
        "tool": "Cold Case",
        "note": "the pipeline returned no manifest; this one was written by the web API",
    }
    for stage in manifest.get("stages", []) if isinstance(manifest.get("stages"), list) else []:
        if isinstance(stage, dict) and stage.get("stage") == "damage_segmentation" and human_mask:
            stage["human_edited_mask"] = True
    manifest.setdefault("source_sha256", source["sha256"])
    manifest["web"] = {
        "fidelity_requested": fidelity,
        "fidelity_applied": fidelity_applied,
        "mask_source": source.get("mask_source", "segmenter"),
        "pipeline_mask_source": to_json_safe(result.get("mask_source")),
        "human_edited_mask": human_mask,
        "pixel_summary": {k: round(v, 6) for k, v in computed_summary.items()},
        "pipeline_pixel_summary": pipeline_summary,
        "regions": regions,
        "displayed_seed": to_json_safe(result.get("displayed_seed")),
        "seeds": seeds_used,
        "seconds": round(seconds, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "warnings": warnings,
    }
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2))

    payload = {
        "key": image_path.parent.name,
        "source_sha256": source["sha256"],
        "fidelity": fidelity,
        "fidelity_applied": fidelity_applied,
        "width": w,
        "height": h,
        "files": {
            "original": original_file,
            "restored": f"{out.name}/restored.png",
            "map": f"{out.name}/map.png",
            "label": f"{out.name}/label.png",
            "regions": f"{out.name}/regions.png",
            "manifest": f"{out.name}/manifest.json",
            "signed": f"{out.name}/{signed_name}" if signed_name else None,
            "mask": f"{out.name}/mask.png" if (tmp / "mask.png").exists() else None,
        },
        "faces": [{"file": f"{out.name}/{f['file']}", "meta": f["meta"]} for f in faces_out],
        "face_original": f"{out.name}/{face_crop}" if face_crop else None,
        "pixel_summary": computed_summary,
        "regions": regions,
        "mask_source": source.get("mask_source", "segmenter"),
        "human_edited_mask": human_mask,
        "seeds": seeds_used,
        "pipeline": pipeline_name(),
        "kind": source.get("kind", "photo"),
        "render_version": RENDER_VERSION,
        "seconds": round(seconds, 2),
        "warnings": warnings,
        "manifest": manifest,
    }
    (tmp / "result.json").write_text(json.dumps(payload, indent=2))

    # Swap the finished folder in only once everything is written, so a crash
    # mid-run never leaves a half-finished result that looks cached.
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    return payload
