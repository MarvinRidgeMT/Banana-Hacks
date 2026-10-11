"""Copy the rendered demo results into frontend/public/static-api/, mirroring the API's
paths, so the site can show the demo cases even when the restoring server is offline.

    cd backend && python export_static_demos.py     # after precompute_demos.py
then rebuild the frontend (npm run build) and push; Vercel ships the copies with the site.
"""
import json, shutil
from pathlib import Path

import api
import restore_hook as hook

OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "static-api"
shutil.rmtree(OUT, ignore_errors=True)
(OUT / "results").mkdir(parents=True)

api.load_demos(warm=False)
listing, copied = [], 0
for d in api.DEMO_INDEX:
    folder = api.CACHE / d["key"]
    dst = OUT / "results" / d["key"]
    files = {"thumb.jpg"}
    ok = True
    for fid in api.FIDELITY_STEPS:
        rf = hook.fidelity_dir(folder, fid) / "result.json"
        if not rf.exists():
            print(f"[skip] {d['id']} w={fid}: not rendered"); ok = False; continue
        r = json.loads(rf.read_text())
        files.add(str(rf.relative_to(folder)))
        files.update(v for v in r["files"].values() if v)
        files.update(f["file"] for f in r["faces"])
        if r.get("face_original"):
            files.add(r["face_original"])
        cj = rf.parent / "color" / "color.json"
        if cj.exists():  # colour mode, if precomputed (colorize_demos.py)
            files.add(str(cj.relative_to(folder)))
            files.update(v for v in json.loads(cj.read_text())["files"].values() if v)
    if not ok:
        continue
    for rel in files:
        src = folder / rel
        if src.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / rel); copied += 1
    listing.append({**d, "thumb": "thumb.jpg", "ready": list(api.FIDELITY_STEPS)})

(OUT / "demos.json").write_text(json.dumps(listing, indent=2, ensure_ascii=False))
metrics = Path(__file__).resolve().parent / "metrics.json"
if metrics.exists():
    shutil.copy2(metrics, OUT / "metrics.json")
size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e6
print(f"exported {len(listing)} demos, {copied} files, {size:.1f} MB -> {OUT}")
