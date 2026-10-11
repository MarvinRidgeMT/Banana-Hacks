"""Colour mode: add colour to a black-and-white restoration, and say how much of it is a guess.

A black-and-white photo has no colour information at all, so every colour we add is made up.
Cold Case keeps that honest:
  * Brightness comes from the scan. We only add the two colour channels (CIE Lab a/b), so the
    picture's light and detail are the original's; the receipt records how closely that holds.
  * Two independently trained colourisers (Zhang et al., ECCV 2016 and SIGGRAPH 2017) colour it.
    Where they agree, the colour is labelled Rebuilt (a well-supported guess: sky, skin, foliage).
    Where they disagree, it is labelled Invented: the models had nothing to go on (a coat could
    be any colour), so treat that colour as decoration, not history.
  * Nothing is ever labelled Real: no colour was in the scan.

Models: github.com/richzhang/colorization (BSD-2), weights in weights/colorize/.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from scipy import ndimage

from colorizers import ECCVGenerator, SIGGRAPHGenerator

HERE = Path(__file__).resolve().parent
WEIGHTS = HERE.parent / "weights" / "colorize"
ECCV_W = WEIGHTS / "colorization_release_v2-9b330a0b.pth"
SIGG_W = WEIGHTS / "siggraph17-df00044c.pth"
DISAGREE = 24.0          # a/b distance (Lab units) above which the two models "disagree"
ALREADY_COLOUR = 6.0     # median chroma above this: the photo already has colour

_lock = threading.Lock()
_models: dict | None = None


def _device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def get_models() -> dict:
    global _models
    if _models is None:
        dev = _device()
        def weights(path: Path) -> dict:
            if path.exists():
                return torch.load(path, map_location="cpu")
            url = "https://colorizers.s3.us-east-2.amazonaws.com/" + path.name
            return torch.hub.load_state_dict_from_url(url, model_dir=str(WEIGHTS), map_location="cpu")
        e = ECCVGenerator()
        e.load_state_dict(weights(ECCV_W))
        s = SIGGRAPHGenerator()
        s.load_state_dict(weights(SIGG_W))
        _models = {"eccv16": e.eval().to(dev), "siggraph17": s.eval().to(dev), "device": dev}
    return _models


def _lab(rgb_u8: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb_u8.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)  # L 0..100, a/b ~ +-127


def _rgb(lab: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB)
    return (np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)


def colorize_array(rgb: np.ndarray) -> dict:
    """rgb: HxWx3 uint8. Returns colourised image, label (1 agree / 2 disagree) and stats."""
    m = get_models()
    dev = m["device"]
    h, w = rgb.shape[:2]
    lab = _lab(rgb)
    chroma_in = float(np.median(np.hypot(lab[..., 1], lab[..., 2])))

    small = cv2.resize(rgb, (256, 256), interpolation=cv2.INTER_AREA)
    gray_small = cv2.cvtColor(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    L_small = _lab(gray_small)[..., 0]
    t = torch.from_numpy(L_small)[None, None].to(dev)
    abs_ = {}
    with _lock, torch.no_grad():
        for name in ("eccv16", "siggraph17"):
            ab = m[name](t)
            ab = F.interpolate(ab, size=(h, w), mode="bilinear", align_corners=False)
            abs_[name] = ab[0].permute(1, 2, 0).float().cpu().numpy()
    ab_e, ab_s = abs_["eccv16"], abs_["siggraph17"]
    # Disagreement between the two models, smoothed so the map shows areas, not noise.
    diff = np.hypot(ab_e[..., 0] - ab_s[..., 0], ab_e[..., 1] - ab_s[..., 1])
    diff = ndimage.gaussian_filter(diff, sigma=max(2.0, min(h, w) / 150))
    label = np.where(diff > DISAGREE, 2, 1).astype(np.uint8)
    # Final colour: the average of both models (less saturated, fewer wild guesses),
    # on the scan's own brightness channel.
    gray_L = _lab(cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB))[..., 0]
    out = _rgb(np.dstack([gray_L, (ab_e + ab_s) / 2]))
    # Brightness check: how far the colour version's lightness moved from the scan's.
    L_out = _lab(out)[..., 0]
    dL = np.abs(L_out - gray_L)
    return {
        "colorized": out,
        "label": label,
        "input_chroma": chroma_in,
        "agree": float((label == 1).mean()),
        "disagree": float((label == 2).mean()),
        "lightness_mean_abs_diff": float(dL.mean()),
        "lightness_p99_abs_diff": float(np.percentile(dL, 99)),
        "device": str(dev),
    }


def colorize_file(src: Path, out_dir: Path, sign=None, map_png=None) -> dict:
    """Colourise src (a restored.png) into out_dir. Cached: returns color.json if present."""
    meta_file = out_dir / "color.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text())
    t0 = time.perf_counter()
    rgb = np.asarray(Image.open(src).convert("RGB"))
    res = colorize_array(rgb)
    if res["input_chroma"] > ALREADY_COLOUR:
        raise ValueError("This photo already has colour, so there is nothing to add.")
    out_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(res["colorized"]).save(out_dir / "colorized.png")
    if map_png is not None:
        map_png(res["label"]).save(out_dir / "map.png")
    manifest = {
        "tool": "Cold Case, colour mode",
        "input": src.name,
        "stages": [
            {"stage": "colourise", "models": ["Zhang et al. ECCV 2016", "Zhang et al. SIGGRAPH 2017"],
             "colour_used": "average of both models", "channels_changed": "Lab a/b only; lightness from the input"},
            {"stage": "labels", "rule": f"models agree (a/b distance <= {DISAGREE}) = Rebuilt; disagree = Invented; "
                                        "no pixel is Real because no colour was in the scan"},
        ],
        "pixel_summary": {"observed": 0.0, "inferred": round(res["agree"], 6), "invented": round(res["disagree"], 6)},
        "lightness_check": {"mean_abs_diff_L": round(res["lightness_mean_abs_diff"], 3),
                            "p99_abs_diff_L": round(res["lightness_p99_abs_diff"], 3), "scale": "L 0-100"},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    signed = None
    if sign is not None:
        try:
            sign(out_dir / "colorized.png", out_dir / "colorized_c2pa.png", manifest)
            signed = "colorized_c2pa.png"
        except Exception as e:  # unsigned colour is still useful; say so
            print(f"[colorize] signing failed: {type(e).__name__}: {e}", flush=True)
    rel = out_dir.parent.name + "/" + out_dir.name
    meta = {
        "files": {"colorized": f"{rel}/colorized.png", "map": f"{rel}/map.png" if map_png else None,
                  "manifest": f"{rel}/manifest.json", "signed": f"{rel}/{signed}" if signed else None},
        "pixel_summary": manifest["pixel_summary"],
        "lightness_check": manifest["lightness_check"],
        "models": ["eccv16", "siggraph17"],
        "device": res["device"],
        "seconds": round(time.perf_counter() - t0, 2),
    }
    meta_file.write_text(json.dumps(meta, indent=2))
    return meta
