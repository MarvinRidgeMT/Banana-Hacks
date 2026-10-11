"""What does the segmenter see on real photos? Original size vs. upscaled to 1024, with probability heatmaps."""
import sys
import numpy as np, cv2
from pathlib import Path
from PIL import Image
from backend.pipeline.segment import segment

out = Path("outputs/seg_diag"); out.mkdir(parents=True, exist_ok=True)
for p in sys.argv[1:]:
    img = np.asarray(Image.open(p).convert("RGB"))
    rows = []
    for target in (None, 1024):
        im = img
        if target and max(img.shape[:2]) < target:
            s = target / max(img.shape[:2])
            im = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_LANCZOS4)
        m, prob = segment(im)
        heat = cv2.applyColorMap((prob * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)[..., ::-1]
        row = np.hstack([im, heat, np.repeat((m * 255).astype(np.uint8)[..., None], 3, 2)])
        rows.append(cv2.resize(row, (1536, round(1536 * row.shape[0] / row.shape[1]))))
        label = "original" if target is None else "upscaled"
        print(f"{Path(p).name:20s} {label:9s} {im.shape[1]}x{im.shape[0]}: "
              f"flagged {m.mean():6.2%}   max prob {prob.max():.2f}")
    Image.fromarray(np.vstack(rows)).save(out / f"{Path(p).stem}.png")
print("saved heatmaps to", out)
