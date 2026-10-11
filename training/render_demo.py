"""Final demo renders: 8 seeds, fidelity 0.3 / 0.7 / 1.0 -> outputs/demo/<name>/w<fidelity>/"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from backend.pipeline.restore import restore
from backend.pipeline.invention_map import overlay
from backend.pipeline.manifest import write_manifest
from backend.pipeline.faces import faces_that_could_have_been

SEEDS = (11, 12, 13, 14, 15, 16, 17, 18)
for p in sys.argv[1:]:
    name = Path(p).stem
    for w in (0.3, 0.7, 1.0):
        r = restore(p, seeds=SEEDS, fidelity=w)
        d = ROOT / "outputs/demo" / name / f"w{w}"; d.mkdir(parents=True, exist_ok=True)
        Image.fromarray(r["original"]).save(d / "original.png")
        Image.fromarray(r["restored"]).save(d / "restored.png")
        Image.fromarray(r["label"]).save(d / "map.png")
        Image.fromarray(overlay(r["restored"], r["label"])).save(d / "map_overlay.png")
        write_manifest(r, d / "manifest.json")
        if r["face_regions"]:
            fr = max(r["face_regions"], key=lambda f: f["invented_fraction"])
            grid, _ = faces_that_could_have_been(r["pre_face_outputs"], fr["bbox"])
            if grid is not None:
                Image.fromarray(grid).save(d / "faces.png")
        print(f"{name} w={w}: {r['pixel_summary']}", flush=True)
