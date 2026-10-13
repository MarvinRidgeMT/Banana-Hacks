import os, cv2, numpy as np, torch
from pathlib import Path
import segmentation_models_pytorch as smp

WEIGHTS = Path(os.environ.get("SEG_WEIGHTS", "weights/seg_v4_best.pth"))
MODEL_NAME = "cv-unet-r34 (ours) " + WEIGHTS.stem.replace("seg_", "").replace("_best", "")
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
_models = {}
# Live mask settings, tuned on real damaged photos by training/calibrate.py (defaults = old behaviour)
THRESHOLD = float(os.environ.get("SEG_THRESHOLD", "0.5"))
TTA = os.environ.get("SEG_TTA", "0") == "1"

def _device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def get_model(weights=None):
    w = str(weights or WEIGHTS)
    if w not in _models:
        m = smp.Unet("resnet34", encoder_weights=None, classes=1)
        m.load_state_dict(torch.load(w, map_location="cpu"))
        _models[w] = m.eval().to(_device())
    return _models[w]

def segment(img, threshold=None, win=512, stride=384, min_area=6, weights=None, tta=None):
    """img: HxWx3 uint8 RGB. Returns (mask bool HxW = content lost, probability HxW).
    tta: also run the mirror image and average (SEG_TTA=1)."""
    threshold = THRESHOLD if threshold is None else threshold
    if TTA if tta is None else tta:
        m1, p1 = segment(img, threshold, win, stride, min_area, weights, tta=False)
        _, p2 = segment(np.ascontiguousarray(img[:, ::-1]), threshold, win, stride, min_area, weights, tta=False)
        prob = (p1 + p2[:, ::-1]) / 2
        m = prob > threshold
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        keep = np.zeros(n, bool); keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
        return keep[lab], prob
    h, w = img.shape[:2]
    x = np.pad(img, ((0, max(0, win - h)), (0, max(0, win - w)), (0, 0)), mode="edge")
    H, W = x.shape[:2]
    t = (x.astype(np.float32) / 255 - MEAN) / STD
    t = torch.from_numpy(t.transpose(2, 0, 1))[None].to(_device())
    ys = list(range(0, H - win + 1, stride)); xs = list(range(0, W - win + 1, stride))
    if ys[-1] != H - win: ys.append(H - win)
    if xs[-1] != W - win: xs.append(W - win)
    prob = np.zeros((H, W), np.float32); cnt = np.zeros((H, W), np.float32)
    model = get_model(weights)
    with torch.no_grad():
        for y in ys:
            for x0 in xs:
                p = torch.sigmoid(model(t[..., y:y + win, x0:x0 + win]))[0, 0].float().cpu().numpy()
                prob[y:y + win, x0:x0 + win] += p; cnt[y:y + win, x0:x0 + win] += 1
    prob = (prob / cnt)[:h, :w]
    m = prob > threshold
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    keep = np.zeros(n, bool); keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[lab], prob
