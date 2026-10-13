"""Check pipeline/scratch_ms.py reproduces Microsoft's reference script exactly (runs/bop_out/mask)."""
import sys, numpy as np
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import scratch_ms
tot = same = 0
for p in sorted((ROOT / "runs" / "bop_in").glob("*.png")):
    img = np.asarray(Image.open(p).convert("RGB"))
    ours = scratch_ms.detect(img)
    ref = np.asarray(Image.open(ROOT / "runs" / "bop_out" / "mask" / p.name).convert("L").resize(img.shape[1::-1], Image.NEAREST)) > 127
    tot += ours.size; same += int((ours == ref).sum())
print(f"pixel agreement with Microsoft's script: {100 * same / tot:.3f}% over {len(list((ROOT / 'runs' / 'bop_in').glob('*.png')))} photos")
