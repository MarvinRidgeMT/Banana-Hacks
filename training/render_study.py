"""Render the hero ("study") through the website's own pipeline hook, first, then
write the user-study ground truth (which 3x3 squares contain Invented pixels)."""
import os, sys, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND)); os.chdir(BACKEND)
import numpy as np, cv2
from PIL import Image, ImageDraw
import api, restore_hook as hook
from pipeline.ingest import ingest
from pipeline.inpaint import split_thin_thick, thick_groups

api.CACHE.mkdir(parents=True, exist_ok=True); api.load_demos(warm=False)
d = next(x for x in api.DEMO_INDEX if x["id"] == "study")
folder = api.CACHE / d["key"]; src = json.loads((folder / "source.json").read_text())
inp, mp = folder / "input.png", folder / "input_mask.png"
if not mp.exists():
    sys.exit(f"STOP: the site did not pick up study_mask.png (no {mp}). Check backend/demos/.")

# How many SDXL regions? 8 seeds if it fits, 4 if the photo would take too long.
img = ingest(str(inp))["image"]
m = cv2.resize(cv2.imread(str(mp), 0), (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST) > 127
md = cv2.dilate(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
n = len(thick_groups(split_thin_thick(m, md, 4)[1]))
seeds = hook.DEMO_SEEDS if n <= 20 else (11, 12, 13, 14)
print(f"study: {n} SDXL regions -> {len(seeds)} seeds, about {round(n * len(seeds) * 55 / 60)} min", flush=True)

for w in api.FIDELITY_STEPS:
    t = time.time()
    r = hook.run_restore(inp, w, src, seeds=seeds)
    print(f"study w={w}: {round(time.time() - t)} s  {r.get('pixel_summary')}", flush=True)

# Ground truth for the user study, from the 0.7 render's label map.
out = hook.fidelity_dir(folder, 0.7)
label = np.asarray(Image.open(out / "label.png"))
H, W = label.shape
squares = {}
for row in range(3):
    for col in range(3):
        cell = label[row * H // 3:(row + 1) * H // 3, col * W // 3:(col + 1) * W // 3]
        squares["ABC"[col] + str(row + 1)] = round(float((cell == 2).mean()), 4)
truth = sorted(k for k, v in squares.items() if v >= 0.01)
gt = {"photo": "study (Bjørnson group)", "fidelity": 0.7, "seeds": list(seeds),
      "rule": "a square 'contains AI-made-up parts' if >= 1% of its pixels are Invented",
      "grid": "A-C left to right, 1-3 top to bottom",
      "invented_share_per_square": squares, "ground_truth_squares": truth}
docs = ROOT / "docs"; docs.mkdir(exist_ok=True)
(docs / "study_ground_truth.json").write_text(json.dumps(gt, indent=2))

def grid(im, path):
    im = im.convert("RGB"); dr = ImageDraw.Draw(im); w, h = im.size
    for i in (1, 2):
        dr.line([(i * w // 3, 0), (i * w // 3, h)], fill=(255, 255, 0), width=4)
        dr.line([(0, i * h // 3), (w, i * h // 3)], fill=(255, 255, 0), width=4)
    for row in range(3):
        for col in range(3):
            x, y = col * w // 3 + 10, row * h // 3 + 8
            dr.rectangle([x - 4, y - 2, x + 40, y + 28], fill=(0, 0, 0))
            dr.text((x, y), "ABC"[col] + str(row + 1), fill=(255, 255, 0))
    im.save(path)

restored = Image.open(out / "restored.png").convert("RGBA")
grid(restored, docs / "study_formA_grid.png")
grid(Image.alpha_composite(restored, Image.open(out / "map.png").convert("RGBA").resize(restored.size)),
     docs / "study_formB_grid_with_map.png")
print("ground truth squares:", truth, squares)
print("saved docs/study_ground_truth.json, docs/study_formA_grid.png, docs/study_formB_grid_with_map.png")
