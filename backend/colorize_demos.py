"""Precompute colour mode for every black-and-white photo demo (all fidelity steps).
Run from backend/ after precompute_demos.py:  python colorize_demos.py"""
import json

import api
import colorize
import restore_hook as hook

api.load_demos(False)
for d in api.DEMO_INDEX:
    key = d["key"]
    if d.get("kind", "photo") != "photo":
        continue
    for fid in api.FIDELITY_STEPS:
        folder = hook.fidelity_dir(api.CACHE / key, fid)
        if not (folder / "restored.png").exists():
            print(f"[skip] {d['id']} w={fid}: not restored yet"); continue
        try:
            m = colorize.colorize_file(folder / "restored.png", folder / "color", hook.sign_c2pa, hook.map_png)
            s = m["pixel_summary"]
            print(f"{d['id']:14s} w={fid}  agree {s['inferred']:.0%}  guess {s['invented']:.0%}  {m['seconds']}s")
        except ValueError as e:
            print(f"{d['id']:14s} w={fid}  {e}")
