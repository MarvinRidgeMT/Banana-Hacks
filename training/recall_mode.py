"""High-recall mode: how far can we push "share of real damage found" by flagging more (a lower
probability cutoff and a wider mask), and what does it cost in false alarms?

Honest protocol: the 40 test photos were never used to train v7. They are split in two by a fixed seed:
TUNE (20) picks the setting = the most precise one reaching the target recall; REPORT (20) scores it
once. Live detector otherwise (v7 at 1024 px + Microsoft scratch detector at 256 px).

    python training/recall_mode.py --target 0.87
"""
import argparse, json, random, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_docs import device, load
from train_v5 import thin
from finetune_v7 import load_set
from calibrate import prob as model_prob
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import scratch_ms

TS = [0.5, 0.4, 0.3, 0.2, 0.15, 0.1, 0.07, 0.05, 0.03]
DS = [2, 3, 4, 6, 8, 12]
CACHE = ROOT / "runs" / "recall_cache"; CACHE.mkdir(parents=True, exist_ok=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--target", type=float, default=0.87); a = ap.parse_args()
    dev = device(); m = load(str(ROOT / "weights" / "seg_v7_best.pth"), dev)
    _, test = load_set()
    idx = list(range(len(test))); random.Random(99).shuffle(idx)
    halves = {"tune_20": [test[i] for i in idx[:20]], "report_20": [test[i] for i in idx[20:]]}
    cfgs = [(t, d) for t in TS for d in DS]
    acc = {h: {c: np.zeros(6, np.int64) for c in cfgs} for h in halves}
    for h, items in halves.items():
        for k, (name, img, gt, ign) in enumerate(items):
            cf = CACHE / f"{name}.npy"
            if cf.exists():
                arr = np.load(cf)
                for j, c in enumerate(cfgs):
                    acc[h][c] += arr[j]
                continue
            before = {c: acc[h][c].copy() for c in cfgs}
            p = model_prob(m, img, dev)
            ms = scratch_ms.detect_prob(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), 256) >= 0.4
            keep = ~ign; g = gt & keep; th = thin(g)
            for t, d in cfgs:
                x = cv2.dilate(((p > t) | ms).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * d + 1, 2 * d + 1))) > 0
                x &= keep
                tp = int((x & g).sum())
                acc[h][(t, d)] += [tp, int((x | g).sum()), int(x.sum()), int(g.sum()), int((x & th).sum()), int(th.sum())]
            np.save(cf, np.stack([acc[h][c] - before[c] for c in cfgs]))
            print(h, k + 1, flush=True)

    def sc(h, c):
        tp, u, pp, gg, ti, tn = acc[h][c]
        return {"recall": round(float(tp / max(gg, 1)), 3), "precision": round(float(tp / max(pp, 1)), 3),
                "iou": round(float(tp / max(u, 1)), 3), "thin_recall": round(float(ti / max(tn, 1)), 3),
                "flagged_vs_true": round(float(pp / max(gg, 1)), 2)}
    live = (0.5, 2)
    ok = [c for c in cfgs if sc("tune_20", c)["recall"] >= a.target]
    chosen = max(ok, key=lambda c: sc("tune_20", c)["precision"]) if ok else max(cfgs, key=lambda c: sc("tune_20", c)["recall"])
    curve = sorted(({"threshold": t, "dilate": d, **sc("tune_20", (t, d))} for t, d in cfgs), key=lambda r: r["recall"])
    rep = {"target_recall": a.target,
           "live": {"threshold": 0.5, "dilate": 2, "tune_20": sc("tune_20", live), "report_20": sc("report_20", live)},
           "chosen": {"threshold": chosen[0], "dilate": chosen[1], "tune_20": sc("tune_20", chosen), "report_20": sc("report_20", chosen)},
           "curve_tune_20": curve}
    (ROOT / "runs" / "recall_mode.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: rep[k] for k in ("live", "chosen")}, indent=2))


if __name__ == "__main__":
    main()
