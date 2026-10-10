import sys, cv2, numpy as np
from pathlib import Path
from damage_synth import damage

src = sys.argv[1]
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
out = Path("test_inputs"); out.mkdir(exist_ok=True)
img = cv2.imread(src)
h, w = img.shape[:2]
s = 1024 / max(h, w)
if s < 1:
    img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
d, m = damage(img, np.random.default_rng(seed))
stem = Path(src).stem
cv2.imwrite(str(out / f"{stem}.png"), d)
cv2.imwrite(str(out / f"{stem}_mask.png"), m * 255)
print("wrote", out / f"{stem}.png", "and its mask")
