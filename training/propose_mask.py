"""v4 proposes a damage mask, merged with any hand-painted one, saved as <name>_mask.png for touch-up."""
import sys, cv2, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from backend.pipeline.segment import segment
for p in sys.argv[1:]:
    img = cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB); h, w = img.shape[:2]
    s = 1024 / max(h, w); big = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_LANCZOS4)
    m, _ = segment(big)
    m = cv2.resize(m.astype(np.uint8) * 255, (w, h), interpolation=cv2.INTER_NEAREST) > 127
    mp = Path(p).with_name(Path(p).stem + "_mask.png")
    if mp.exists():
        m |= cv2.resize(cv2.imread(str(mp), 0), (w, h), interpolation=cv2.INTER_NEAREST) > 127
    cv2.imwrite(str(mp), (m * 255).astype(np.uint8))
    print(f"{mp}: {m.mean():.1%} marked (v4 proposal + your earlier paint)")
