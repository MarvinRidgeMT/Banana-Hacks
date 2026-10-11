"""A FAKE restore() for building and testing the website without the real models.

Run the API with CV_PIPELINE=stub to use it. It returns the same keys as
backend/pipeline/restore.py, with made-up but plausible content:
  - damage = the <name>_mask.png next to the image if there is one, otherwise
    very bright or very dark specks
  - each "seed" fills the damage with a blur plus its own noise
  - label = inferred where the seeds agree, invented where they don't
Never use its output in the demo or the write-up.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

SEEDS = (11, 12, 13, 14)


def _find_mask(path: Path, gray: np.ndarray) -> tuple[np.ndarray, str]:
    mask_file = path.with_name(path.stem + "_mask.png")
    if mask_file.exists():
        m = np.asarray(Image.open(mask_file).convert("L").resize(gray.shape[::-1], Image.NEAREST))
        return m > 127, "provided mask file"
    blur = ndimage.uniform_filter(gray.astype(float), 15)
    return ndimage.binary_opening(np.abs(gray - blur) > 60, iterations=1), "stub-segmenter"


def restore(path, seeds=SEEDS, steps=20, fidelity=0.5, strict_faces=True, face_stage=True):
    p = Path(path)
    img = np.asarray(Image.open(p).convert("RGB"))
    gray = img.mean(axis=2)
    damage, mask_source = _find_mask(p, gray)
    used = ndimage.binary_dilation(damage, iterations=2)

    fill = np.asarray(Image.fromarray(img).filter(ImageFilter.GaussianBlur(9))).astype(np.float32)
    depth = ndimage.distance_transform_edt(used)
    pre = []
    for s in seeds:
        rng = np.random.default_rng(s)
        noise = ndimage.gaussian_filter(rng.normal(0, 40, gray.shape), 3)[..., None]
        wobble = np.clip(depth / 10, 0, 1)[..., None]  # deeper inside the damage = more disagreement
        o = img.astype(np.float32).copy()
        cand = np.clip(fill + noise * wobble, 0, 255)
        o[used] = cand[used]
        pre.append(o.astype(np.uint8))

    # "face restoration": pull the face area slightly towards the original by fidelity
    outs = [o.copy() for o in pre]
    sigma = np.std(np.stack(pre).astype(np.float32), axis=0).mean(axis=2)
    k = int(np.argmin([np.abs(o.astype(float) - np.mean(pre, axis=0)).mean() for o in pre]))
    out = outs[k]
    label = np.zeros(gray.shape, dtype=np.uint8)
    label[used] = 1
    label[used & (sigma > 1.5 + 2 * fidelity)] = 2

    faces_file = p.with_name(p.stem + "_faces.json")
    boxes = []
    if faces_file.exists():
        data = json.loads(faces_file.read_text())
        boxes = [f["bbox"] for f in (data.get("faces", data) if isinstance(data, dict) else data)]
    face_regions = []
    for j, (x0, y0, x1, y1) in enumerate(boxes, start=1):
        box = label[y0:y1, x0:x1]
        changed = int((box > 0).sum())
        face_regions.append({"id": f"face{j}", "bbox": [x0, y0, x1, y1],
                             "invented_fraction": round(int((box == 2).sum()) / max(changed, 1), 3)})

    comp, n = ndimage.label(used)
    regions = []
    for i, sl in enumerate(ndimage.find_objects(comp), start=1):
        part = comp[sl] == i
        regions.append({"id": i, "bbox": [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop],
                        "confidence": round(1 - int((part & (label[sl] == 2)).sum()) / max(int(part.sum()), 1), 3)})

    time.sleep(float(os.environ.get("CV_STUB_SECONDS", "2")))
    total = label.size
    return {
        "sha256": "stub", "original": img, "restored": out, "seed_outputs": outs, "pre_face_outputs": pre,
        "displayed_seed": seeds[k], "damage_mask": damage, "mask_source": mask_source,
        "mask": used, "label": label, "sigma": sigma,
        "pixel_summary": {"observed": float((label == 0).sum() / total),
                          "inferred": float((label == 1).sum() / total),
                          "invented": float((label == 2).sum() / total)},
        "regions": regions, "face_regions": face_regions, "fidelity": fidelity, "scale": 1.0,
        "log": object(),
    }
