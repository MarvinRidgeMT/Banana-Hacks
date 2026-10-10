import cv2, numpy as np, torch
from pathlib import Path
import segmentation_models_pytorch as smp

WEIGHTS = Path("weights/seg_v1_best.pth")
MODEL_NAME = "cv-unet-r34 (ours) v1"
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
_model = None

def _device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def get_model():
    global _model
    if _model is None:
        m = smp.Unet("resnet34", encoder_weights=None, classes=1)
        m.load_state_dict(torch.load(WEIGHTS, map_location="cpu"))
        _model = m.eval().to(_device())
    return _model

def segment(img, threshold=0.5, win=512, stride=384, min_area=6):
    """img: HxWx3 uint8 RGB. Returns (mask bool HxW = content lost, probability HxW).
    Sliding 512 px windows with overlap, averaged; tiny specks below min_area dropped."""
    h, w = img.shape[:2]
    x = np.pad(img, ((0, max(0, win - h)), (0, max(0, win - w)), (0, 0)), mode="edge")
    H, W = x.shape[:2]
    t = (x.astype(np.float32) / 255 - MEAN) / STD
    t = torch.from_numpy(t.transpose(2, 0, 1))[None].to(_device())
    ys = list(range(0, H - win + 1, stride))
    xs = list(range(0, W - win + 1, stride))
    if ys[-1] != H - win:
        ys.append(H - win)
    if xs[-1] != W - win:
        xs.append(W - win)
    prob = np.zeros((H, W), np.float32)
    cnt = np.zeros((H, W), np.float32)
    model = get_model()
    with torch.no_grad():
        for y in ys:
            for x0 in xs:
                p = torch.sigmoid(model(t[..., y:y + win, x0:x0 + win]))[0, 0].float().cpu().numpy()
                prob[y:y + win, x0:x0 + win] += p
                cnt[y:y + win, x0:x0 + win] += 1
    prob = (prob / cnt)[:h, :w]
    m = prob > threshold
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[lab], prob
