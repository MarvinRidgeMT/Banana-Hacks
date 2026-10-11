import sys, cv2, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from backend.pipeline.segment import segment
W = sys.argv[1] if len(sys.argv) > 1 else "weights/seg_v3_best.pth"
ths = [0.5, 0.3, 0.2, 0.1, 0.05]
I = {t: 0 for t in ths}; U = {t: 0 for t in ths}; R = {t: 0 for t in ths}; G = 0
out = ROOT / "outputs/real_diag"; out.mkdir(parents=True, exist_ok=True)
for p in sorted((ROOT / "data/real_eval").glob("picture*.png")):
    if p.stem.endswith("_mask"): continue
    img = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
    s = 1024 / max(img.shape[:2]); big = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_LANCZOS4)
    _, prob = segment(big, weights=W)
    gt = cv2.resize(cv2.imread(str(p.with_name(p.stem + "_mask.png")), 0), big.shape[1::-1], interpolation=cv2.INTER_NEAREST) > 127
    G += gt.sum()
    for t in ths:
        m = prob > t; I[t] += (m & gt).sum(); U[t] += (m | gt).sum(); R[t] += (m & gt).sum()
    print(f"{p.name:15s} max prob {prob.max():.2f}   mean prob on damage {prob[gt].mean():.3f}   on clean {prob[~gt].mean():.3f}")
    heat = cv2.applyColorMap((prob * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)[..., ::-1]
    cv2.imwrite(str(out / p.name), cv2.cvtColor(np.hstack([big, heat, np.repeat(gt[..., None] * 255, 3, 2).astype(np.uint8)]), cv2.COLOR_RGB2BGR))
for t in ths:
    print(f"threshold {t:.2f}: IoU {I[t] / max(U[t], 1):.3f}   recall {R[t] / max(G, 1):.3f}")
