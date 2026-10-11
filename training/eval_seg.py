"""Real-photo IoU: segmenter vs hand-labelled masks on genuinely damaged photos.
Usage: python training/eval_seg.py weights/seg_v1_best.pth weights/seg_v3_best.pth"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import cv2, numpy as np
from backend.pipeline.segment import segment

photos = sorted(p for p in (ROOT / "data/real_eval").glob("*.png") if not p.stem.endswith("_mask"))
pairs = [(p, p.with_name(p.stem + "_mask.png")) for p in photos]
pairs = [(p, m) for p, m in pairs if m.exists()]
print(f"{len(pairs)} hand-labelled real photos")
results = {}
for wpath in sys.argv[1:]:
    name = Path(wpath).stem.replace("seg_", "").replace("_best", "")
    I = U = FP = FN = 0; per = []
    for p, mp in pairs:
        img = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
        s = 1024 / max(img.shape[:2])                      # same working size as the pipeline
        big = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_LANCZOS4)
        pred, _ = segment(big, weights=wpath)
        gt = cv2.resize(cv2.imread(str(mp), 0), big.shape[1::-1], interpolation=cv2.INTER_NEAREST) > 127
        i, u = int((pred & gt).sum()), int((pred | gt).sum())
        I += i; U += u; FP += int((pred & ~gt).sum()); FN += int((~pred & gt).sum())
        per.append({"photo": p.name, "iou": round(i / max(u, 1), 3)})
    r = {"pooled_iou": round(I / max(U, 1), 3),
         "mean_iou": round(float(np.mean([q["iou"] for q in per])), 3),
         "precision": round(I / max(I + FP, 1), 3), "recall": round(I / max(I + FN, 1), 3),
         "per_photo": per}
    results[name] = r
    print(f"{name}: pooled IoU {r['pooled_iou']}  mean IoU {r['mean_iou']}  "
          f"precision {r['precision']}  recall {r['recall']}")
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/real_iou.json").write_text(json.dumps(results, indent=2))
print("saved docs/real_iou.json")
