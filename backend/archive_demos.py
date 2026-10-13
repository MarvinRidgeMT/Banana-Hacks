"""Precompute the typical-restorer comparison for every photo demo (default fidelity), so the
'vs. a typical restorer' tab also works on the offline copies. Run from backend/:  python archive_demos.py"""
import json

import numpy as np
from PIL import Image

import api
import features
import restore_hook as hook
from pipeline.codeformer import restore_face

api.load_demos(False)
for d in api.DEMO_INDEX:
    if d.get("kind", "photo") != "photo":
        continue
    r = api.cached_result(d["key"], api.DEFAULT_FIDELITY)
    if not r:
        print(f"[skip] {d['id']}: not restored yet"); continue
    folder = api.CACHE / d["key"]
    orig = np.asarray(Image.open(folder / r["files"]["original"]).convert("RGB"))
    m = r["files"].get("mask")
    dmg = (np.asarray(Image.open(folder / m).convert("L")) > 127) if m else (np.asarray(Image.open(folder / r["files"]["label"]).convert("L")) > 0)
    out = hook.fidelity_dir(folder, api.DEFAULT_FIDELITY) / "compare"
    meta = features.typical_restore(orig, dmg, out, restore_face)
    print(f"{d['id']:14s} typical restorer changed {meta['undamaged_changed_pct']}% of undamaged pixels (Cold Case: 0)")
