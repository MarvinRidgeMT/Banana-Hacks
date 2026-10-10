"""CodeFormer face restoration, loaded without CodeFormer's bundled basicsr package init
(which breaks on current torchvision). Only the two model files we need are imported."""
import sys, types, importlib
from pathlib import Path
import numpy as np, torch

CF_DIR = Path("third_party/CodeFormer")
WEIGHTS = Path("weights/codeformer.pth")
_net = None

def _device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def _load_class():
    import torchvision.transforms.functional as F
    sys.modules.setdefault("torchvision.transforms.functional_tensor", F)   # old name basicsr expects
    root = (CF_DIR / "basicsr").resolve()
    # Register empty package stubs so basicsr/__init__.py (which imports everything) never runs
    for name, path in [("basicsr", root), ("basicsr.archs", root / "archs")]:
        if name not in sys.modules:
            m = types.ModuleType(name)
            m.__path__ = [str(path)]
            sys.modules[name] = m
    return importlib.import_module("basicsr.archs.codeformer_arch").CodeFormer

def get_net():
    global _net
    if _net is None:
        CodeFormer = _load_class()
        net = CodeFormer(dim_embd=512, codebook_size=1024, n_head=8, n_layers=9,
                         connect_list=["32", "64", "128", "256"])
        ck = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
        net.load_state_dict(ck.get("params_ema", ck))
        _net = net.eval().to(_device())
    return _net

@torch.no_grad()
def restore_face(face512, fidelity=0.7):
    """face512: 512x512x3 uint8 RGB face crop.
    fidelity w: 1.0 = stay close to the input, 0.0 = most generative (most invented)."""
    x = torch.from_numpy(face512.astype(np.float32) / 255).permute(2, 0, 1)[None]
    x = ((x - 0.5) / 0.5).to(_device())
    out = get_net()(x, w=fidelity, adain=True)[0]
    out = ((out.clamp(-1, 1) + 1) / 2 * 255).round()[0].permute(1, 2, 0)
    return out.byte().cpu().numpy()

def face_pass(img, orig, boxes, damaged, fidelity=0.5, strict=True, pad=0.15):
    """Stage 4. Run CodeFormer on each face box and paste the result back.
    strict=True: only damaged face pixels are replaced, so real undamaged pixels stay untouched.
    Replaced pixels get the photo's own tint, brightness and grain (same blend-in as inpainting)."""
    import cv2
    from .inpaint import _blend_in
    out = img.copy()
    H, W = damaged.shape
    for b in boxes:
        x, y, w, h = [int(v) for v in b[:4]]
        p = int(pad * max(w, h))
        x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
        crop = out[y0:y1, x0:x1]
        fixed = restore_face(cv2.resize(crop, (512, 512), interpolation=cv2.INTER_LANCZOS4), fidelity)
        fixed = cv2.resize(fixed, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        ell = np.zeros((H, W), np.uint8)
        cv2.ellipse(ell, (x + w // 2, y + h // 2), (max(1, w // 2), max(1, int(h * 0.55))), 0, 0, 360, 1, -1)
        region = ell.astype(bool) & (damaged if strict else True)
        if not region.any():
            continue
        full = out.copy()
        full[y0:y1, x0:x1] = fixed
        out[region] = full[region]
        _blend_in(out, orig, region, damaged)
    return out
