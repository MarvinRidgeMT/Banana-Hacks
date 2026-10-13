"""Add the "every attempt" strips (click a red area -> see all 8 attempts) to results rendered before
that feature existed, WITHOUT re-running SDXL: only results whose diffusion outputs are already cached
(backend/cache/*.npz) are done; the face pass is re-run (seconds). A strip is saved only if the
re-run reproduces the saved restoration exactly, so it always shows the attempts behind the image.

    cd backend && python backfill_alternatives.py && python export_static_demos.py
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
import restore_hook as hook
from pipeline.restore import restore, ingest, get_mask, _cache_key, is_color_photo

HERE = Path(__file__).resolve().parent
RESULTS = None  # set from api.CACHE


def main():
    done = skipped = 0
    import api
    api.load_demos(warm=False)
    demos = {d["key"] for d in api.DEMO_INDEX}
    for rf in sorted(api.CACHE.glob("*/f*/result.json")):
        if "--all" not in sys.argv and demos and rf.parent.parent.name not in demos:
            continue
        r = json.loads(rf.read_text())
        if r.get("kind") == "document" or r.get("pipeline") != "real":
            continue
        if any(g.get("alternatives") for g in r.get("regions", [])):
            continue
        folder = rf.parent; src = folder.parent / "input.png"
        n = int(r.get("seeds") or 4)
        seeds = tuple(range(11, 11 + n))
        d = ingest(str(src)); mask, _ = get_mask(str(src), d["image"])
        if not _cache_key(d["sha256"], mask, seeds, 20, is_color_photo(d["image"])).exists():
            skipped += 1
            print("skip (diffusion outputs not cached):", folder.parent.name[:8], folder.name, flush=True)
            continue
        out = restore(str(src), seeds=seeds, fidelity=float(r["fidelity"]))
        saved = np.asarray(Image.open(folder / "restored.png").convert("RGB"))
        if out["restored"].shape != saved.shape or not np.array_equal(out["restored"], saved):
            skipped += 1
            print("skip (re-run differs from the saved restoration):", folder.parent.name[:8], folder.name, flush=True)
            continue
        k = hook.save_alternatives(folder, folder.name, out["original"], out["seed_outputs"],
                                   out.get("displayed_seed"), seeds, r["regions"])
        rf.write_text(json.dumps(r, indent=2))
        done += 1
        print(f"ok {folder.parent.name[:8]} {folder.name}: {k} regions", flush=True)
    print(f"done {done}, skipped {skipped}")


if __name__ == "__main__":
    main()
