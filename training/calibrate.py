"""Tune the live mask settings on the 90 TRAINING real photos only, then report once on the 40
unseen test photos. Settings: the model's probability cutoff, mirror test-time augmentation (TTA),
whether to add the Microsoft scratch detector, and how far to widen the final mask.

    python training/calibrate.py --weights weights/seg_v7_best.pth      (or seg_v5_best.pth)
Writes runs/calibration.json and prints the env settings to start the server with."""
import argparse, itertools, json, sys
from pathlib import Path
import cv2, numpy as np, torch
from scipy import ndimage
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_docs import device, to_tensor, load
from finetune_v7 import load_set, scores, demo_set
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


@torch.no_grad()
def prob(model, bgr, dev, tta=False, win=512, stride=384):
    def run(x):
        h, w = x.shape[:2]
        xp = cv2.copyMakeBorder(x, 0, max(0, win - h), 0, max(0, win - w), cv2.BORDER_REFLECT)
        H, W = xp.shape[:2]
        ys = list(range(0, H - win + 1, stride)); xs = list(range(0, W - win + 1, stride))
        if ys[-1] != H - win: ys.append(H - win)
        if xs[-1] != W - win: xs.append(W - win)
        p = np.zeros((H, W), np.float32); c = np.zeros((H, W), np.float32)
        for y in ys:
            for x0 in xs:
                t = to_tensor(np.ascontiguousarray(xp[y:y + win, x0:x0 + win]))[None].to(dev)
                p[y:y + win, x0:x0 + win] += torch.sigmoid(model(t))[0, 0].float().cpu().numpy(); c[y:y + win, x0:x0 + win] += 1
        return (p / c)[:h, :w]
    p = run(bgr)
    if tta:
        p = (p + run(np.ascontiguousarray(bgr[:, ::-1]))[:, ::-1]) / 2
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(ROOT / "weights" / "seg_v7_best.pth"))
    a = ap.parse_args()
    from pipeline import scratch_ms
    dev = device(); model = load(a.weights, dev)
    train, test = load_set()
    def feats(items):
        out = []
        for name, img, gt, ign in items:
            ms = scratch_ms.detect(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)) if scratch_ms.available() else np.zeros(gt.shape, bool)
            out.append((prob(model, img, dev), prob(model, img, dev, tta=True), ms, gt, ign))
        return out
    print("scoring the 90 training photos...", flush=True)
    F = feats(train)
    grid = list(itertools.product([0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6], [False, True], [False, True], [0, 1, 2, 3]))
    def apply(f, t, tta, use_ms, dil):
        p, pt, ms, gt, ign = f
        m = (pt if tta else p) > t
        if use_ms: m = m | ms
        if dil: m = ndimage.binary_dilation(m, iterations=dil)
        return m, gt, ign
    best = max(grid, key=lambda g: scores([apply(f, *g) for f in F])["iou"])
    base = (0.5, False, True, 2)   # what the site does now
    res = {"chosen": dict(zip(["threshold", "tta", "with_ms", "dilate"], best)),
           "train_90": {"current": scores([apply(f, *base) for f in F]), "chosen": scores([apply(f, *best) for f in F])}}
    print("scoring the 40 unseen test photos once...", flush=True)
    T = feats(test); D = feats(demo_set())
    res["test_40"] = {"current": scores([apply(f, *base) for f in T]), "chosen": scores([apply(f, *best) for f in T])}
    res["demo_5"] = {"current": scores([apply(f, *base) for f in D]), "chosen": scores([apply(f, *best) for f in D])}
    res["weights"] = Path(a.weights).name
    (ROOT / "runs" / "calibration.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    t, tta, use_ms, dil = best
    print(f"\nStart the server with:\n  SEG_WEIGHTS=weights/{Path(a.weights).name} SEG_THRESHOLD={t} SEG_TTA={int(tta)} "
          f"SEG_WITH_MS={int(use_ms)} SEG_DILATE={dil} uvicorn api:app --port 8000")


if __name__ == "__main__":
    main()
