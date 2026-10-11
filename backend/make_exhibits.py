"""Refresh the landing page's answer-key exhibit from the current face_missing render.
Run from backend/ after precompute_demos.py:  python make_exhibits.py"""
import json
import shutil
from pathlib import Path

import api

api.load_demos(False)
d = next(x for x in api.DEMO_INDEX if x["id"] == "face_missing")
folder = api.CACHE / d["key"]
r = json.loads((folder / "f070" / "result.json").read_text())
out = Path(__file__).resolve().parent.parent / "frontend" / "public" / "exhibits"
faces = [f["file"] for f in r["faces"]][:3]
for i, f in enumerate(faces, 1):
    shutil.copy2(folder / f, out / f"lincoln_guess{i}.png")
if r.get("face_original"):
    shutil.copy2(folder / r["face_original"], out / "lincoln_damaged.png")
print(f"exhibit updated from {d['key'][:8]}: {len(faces)} guesses")
