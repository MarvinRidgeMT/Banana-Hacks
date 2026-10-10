import itertools
import cv2, numpy as np
from pathlib import Path

YUNET = Path("weights/face_detection_yunet_2023mar.onnx")

def detect_faces(img, score=0.6):
    """img: HxWx3 uint8 RGB. Returns [(x, y, w, h, score)] clamped to the image."""
    H, W = img.shape[:2]
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (W, H), score, 0.3, 50)
    _, faces = det.detect(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    boxes = []
    if faces is not None:
        for f in faces:
            x, y, w, h = [int(round(v)) for v in f[:4]]
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(W, x + w), min(H, y + h)
            if x1 > x0 and y1 > y0:
                boxes.append((x0, y0, x1 - x0, y1 - y0, float(f[-1])))
    return boxes

def face_report(img, label, fallback=()):
    """One manifest region per face: how much of it the pipeline changed, and how much was invented."""
    out = []
    for i, (x, y, w, h, s) in enumerate(detect_faces(img, score=0.5) or list(fallback)):
        lab = label[y:y + h, x:x + w]
        changed = int((lab > 0).sum())
        inv = int((lab == 2).sum())
        out.append({"id": f"face-{i + 1}", "bbox": [x, y, w, h], "kind": "face",
                    "detector_score": round(s, 3), "pixels_changed": changed,
                    "invented_fraction": round(inv / (w * h), 3),
                    "confidence": round(1 - inv / changed, 3) if changed else 1.0})
    return out

def faces_that_could_have_been(outs, box, size=320, pad=0.12):
    """From the seed outputs, pick the 3 versions of this face that differ most from each other."""
    if len(outs) < 3:
        return None, []
    x, y, w, h = box[:4]
    H, W = outs[0].shape[:2]
    p = int(max(w, h) * pad)
    y0, y1, x0, x1 = max(0, y - p), min(H, y + h + p), max(0, x - p), min(W, x + w + p)
    crops = [cv2.resize(o[y0:y1, x0:x1], (size, size), interpolation=cv2.INTER_CUBIC) for o in outs]
    f = [c.astype(np.float32) for c in crops]
    def spread(t):
        return sum(np.mean((f[a] - f[b]) ** 2) for a, b in itertools.combinations(t, 2))
    best = max(itertools.combinations(range(len(f)), 3), key=spread)
    return np.hstack([crops[i] for i in best]), list(best)

def detect_faces_damaged(img, mask):
    """Faces are often what's torn, so fill the damage quickly first, then look for faces."""
    filled = cv2.inpaint(img, (mask > 0).astype(np.uint8), 5, cv2.INPAINT_TELEA)
    return detect_faces(filled, score=0.5) or detect_faces(filled, score=0.3)

def load_face_hints(path):
    """Face boxes a person marked (or a test script wrote) in <name>_faces.json: [[x, y, w, h], ...]."""
    import json
    from pathlib import Path
    p = Path(path).with_name(Path(path).stem + "_faces.json")
    if not p.exists():
        return []
    return [tuple(int(v) for v in b) + (1.0,) for b in json.loads(p.read_text())]
