"""Second damage detector: Microsoft's old-photo scratch detector (Wan et al., "Bringing Old Photos
Back to Life", CVPR 2020; MIT licence, code in third_party/bop_detection, weights/scratch_ms.pt).

It is strong where ours is weak (long thin cracks and scratches) and weak where ours is strong
(our model also covers holes and synthetic-style losses), so the pipeline uses the UNION of both.
Inference mirrors the reference script third_party/bop_detection/detection_reference.py exactly:
grey, normalised to [-1, 1], short side scaled to 256 (multiple of 16), sigmoid >= 0.4,
nearest-neighbour back to full size. Runs on CPU (it is a small net at 256 px)."""
from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
WEIGHTS = HERE.parent / "weights" / "scratch_ms.pt"
MODEL_NAME = "Microsoft old-photo scratch detector (Wan et al. 2020)"
_lock = threading.Lock()
_model = None


def available() -> bool:
    return WEIGHTS.exists() and (HERE / "third_party" / "bop_detection" / "networks.py").exists()


def get_model():
    global _model
    if _model is None:
        tp = str(HERE / "third_party")
        if tp not in sys.path:
            sys.path.insert(0, tp)
        # their code imports itself as the package "detection_models"
        sys.modules.setdefault("detection_models", importlib.import_module("bop_detection"))
        networks = importlib.import_module("detection_models.networks")
        m = networks.UNet(in_channels=1, out_channels=1, depth=4, conv_num=2, wf=6, padding=True,
                          batch_norm=True, up_mode="upsample", with_tanh=False, sync_bn=True,
                          antialiasing=True)
        ck = torch.load(str(WEIGHTS), map_location="cpu")
        m.load_state_dict(ck["model_state"])
        _model = m.cpu().eval()
    return _model


def _r16(v: float) -> int:
    return int(round(v / 16) * 16)


def detect(img: np.ndarray, threshold: float = 0.4, scale: int = 256) -> np.ndarray:
    """img: HxWx3 uint8 RGB. Returns a bool HxW mask of scratches/cracks."""
    return detect_prob(img, scale) >= threshold


def detect_prob(img: np.ndarray, scale: int = 256) -> np.ndarray:
    """img: HxWx3 uint8 RGB. Returns the scratch probability, float32 HxW in [0, 1]."""
    pil = Image.fromarray(img).convert("RGB")
    ow, oh = pil.size
    w, h = _r16(ow), _r16(oh)                                   # data_transforms("full_size")
    if (w, h) != (ow, oh):
        pil = pil.resize((w, h), Image.BICUBIC)
    g = np.asarray(pil.convert("L"), np.float32) / 255.0
    t = torch.from_numpy((g - 0.5) / 0.5)[None, None]          # ToTensor + Normalize([.5],[.5])
    _, _, H, W = t.shape                                        # scale_tensor(default_scale=256)
    if H < W:
        nh, nw = scale, W / H * scale
    else:
        nw, nh = scale, H / W * scale
    t = F.interpolate(t, [_r16(nh), _r16(nw)], mode="bilinear")
    with _lock, torch.no_grad():
        p = torch.sigmoid(get_model()(t))
    p = F.interpolate(p, [H, W], mode="nearest")[0, 0].numpy().astype(np.float32)
    if (W, H) != (ow, oh):
        p = np.asarray(Image.fromarray(p, mode="F").resize((ow, oh), Image.NEAREST), np.float32)
    return p
