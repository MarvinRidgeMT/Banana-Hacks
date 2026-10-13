"""The live damage detector for photos: our segmenter combined with Microsoft's scratch detector.
Settings come from the environment and were chosen on 90 real training photos by
training/eval_variants.py (defaults = the setup measured at 61% recall on 40 unseen photos):

  SEG_RES     working size for our segmenter, longest side in px (1024; 0 = full resolution, max 4096)
  SEG_WITH_MS 1 to add the Microsoft scratch detector (1)
  MS_SCALE    short side the scratch detector looks at, px (256 = its reference setting)
  MS_GATE     keep a scratch mark only where our segmenter's probability is at least this (0 = keep all)
"""
from __future__ import annotations

import os

import cv2
import numpy as np


def settings() -> dict:
    return {"seg_res": int(os.environ.get("SEG_RES", "1024")),
            "with_ms": os.environ.get("SEG_WITH_MS", "1") == "1",
            "ms_scale": int(os.environ.get("MS_SCALE", "256")),
            "ms_gate": float(os.environ.get("MS_GATE", "0"))}


def _resize(a, size, interp):
    return cv2.resize(a, size, interpolation=interp)


def detect_damage(rgb: np.ndarray, weights=None, cfg: dict | None = None):
    """rgb: HxWx3 uint8. Returns (mask bool HxW, prob float32 HxW, description str)."""
    from .segment import segment, MODEL_NAME
    cfg = cfg or settings()
    h, w = rgb.shape[:2]
    res = cfg["seg_res"] or 4096
    k = min(1.0, res / max(h, w))
    small = _resize(rgb, (round(w * k), round(h * k)), cv2.INTER_AREA) if k < 1 else rgb
    m, p = segment(small, weights=weights)
    if k < 1:
        p = _resize(p.astype(np.float32), (w, h), cv2.INTER_LINEAR)
        m = _resize(m.astype(np.uint8), (w, h), cv2.INTER_NEAREST) > 0
    desc = f"{MODEL_NAME} @ {small.shape[1]}x{small.shape[0]}"
    if cfg["with_ms"]:
        try:
            from . import scratch_ms
            if scratch_ms.available():
                pm = scratch_ms.detect_prob(rgb, scale=cfg["ms_scale"])
                ms = pm >= 0.4
                if cfg["ms_gate"] > 0:
                    ms &= p >= cfg["ms_gate"]
                m = m | ms
                p = np.maximum(p, np.where(ms, pm, 0).astype(np.float32))
                desc += f" + {scratch_ms.MODEL_NAME} @ {cfg['ms_scale']}px" + (f", gated at {cfg['ms_gate']}" if cfg["ms_gate"] else "")
        except Exception as e:  # the second detector is a bonus, never a blocker
            print(f"[detect] scratch detector skipped: {type(e).__name__}: {e}", flush=True)
    return m, p.astype(np.float32), desc
