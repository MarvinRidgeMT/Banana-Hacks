"""Pick restoration settings with evidence: render the simulated-face demo (whose true,
undamaged photo we have) at several SDXL step counts and mask widenings, and measure
how far each result is from the truth (mean CIELAB ΔE inside the repaired area and
inside the face box). Lower is better.

    cd backend && source .venv-gpu/bin/activate
    python sweep_quality.py            # ~10-15 min on an M5 Pro; results in sweep_out/

Uses 4 seeds per run to keep it quick; the ranking carries over to 8 seeds.
"""
import csv, json, shutil, sys, time
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.color import rgb2lab

from pipeline.restore import restore

DEMOS = Path("demos")
DAMAGED, TRUTH = DEMOS / "face_missing.png", DEMOS / "inferred.png"
MASK, FACES = DEMOS / "face_missing_mask.png", DEMOS / "face_missing_faces.json"
STEPS = (20, 30, 40)
WIDEN = (0, 4)          # extra pixels added around the mask
SEEDS = (11, 12, 13, 14)
OUT = Path("sweep_out"); OUT.mkdir(exist_ok=True)

truth_full = Image.open(TRUTH).convert("RGB")
mask_full = np.asarray(Image.open(MASK).convert("L")) > 127
face = json.loads(FACES.read_text())[0][:4]  # [x, y, w, h] in the photo's own pixels

def delta_e(a, b, m):
    d = np.linalg.norm(rgb2lab(a / 255.0) - rgb2lab(b / 255.0), axis=-1)
    return float(d[m].mean()) if m.any() else float("nan")

rows = []
for widen in WIDEN:
    work = OUT / f"w{widen}"; work.mkdir(exist_ok=True)
    img = work / "photo.png"; shutil.copy(DAMAGED, img); shutil.copy(FACES, work / "photo_faces.json")
    m = ndimage.binary_dilation(mask_full, iterations=widen) if widen else mask_full
    Image.fromarray(m.astype(np.uint8) * 255, "L").save(work / "photo_mask.png")
    for steps in STEPS:
        t = time.time()
        r = restore(str(img), seeds=SEEDS, steps=steps, fidelity=0.7)
        secs = time.time() - t
        out = np.asarray(r["restored"]).astype(np.float32)
        h, w = out.shape[:2]
        truth = np.asarray(truth_full.resize((w, h), Image.LANCZOS)).astype(np.float32)
        # score on the ORIGINAL damage so every setting is judged on the same pixels
        dmg = np.asarray(Image.fromarray(mask_full.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 127
        sx, sy = w / truth_full.width, h / truth_full.height
        fb = np.zeros((h, w), bool)
        fb[int(face[1] * sy):int((face[1] + face[3]) * sy), int(face[0] * sx):int((face[0] + face[2]) * sx)] = True
        row = {"steps": steps, "widen_px": widen, "seconds": round(secs),
               "dE_damaged": round(delta_e(out, truth, dmg), 2),
               "dE_face_damaged": round(delta_e(out, truth, dmg & fb), 2),
               "invented_pct": round(100 * r["pixel_summary"].get("invented", 0), 2)}
        rows.append(row); print(row, flush=True)
        Image.fromarray(out.astype(np.uint8)).save(OUT / f"restored_steps{steps}_widen{widen}.png")

with open(OUT / "results.csv", "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
best = min(rows, key=lambda r: r["dE_face_damaged"])
print("\nBEST (closest to the true face):", best)
print("Full table: sweep_out/results.csv · images: sweep_out/restored_*.png")
