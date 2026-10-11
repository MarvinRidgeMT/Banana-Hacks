"""Pre-compute every demo photo at every fidelity step, without the web server.

    cd backend && python precompute_demos.py            # only what's missing
    cd backend && python precompute_demos.py --force    # redo everything

Run it at code freeze (Sun 18:00) so the site and the video never wait on the GPU.
"""
import json
import shutil
import sys
import time

import api
import restore_hook as hook

force = "--force" in sys.argv
api.CACHE.mkdir(parents=True, exist_ok=True)
api.load_demos(warm=False)
if not api.DEMO_INDEX:
    sys.exit(f"No demo photos found in {api.DEMOS} (check demos.json and the file names).")

failures = 0
for demo in api.DEMO_INDEX:
    folder = api.CACHE / demo["key"]
    source = json.loads((folder / "source.json").read_text())
    for fid in api.FIDELITY_STEPS:
        out = hook.fidelity_dir(folder, fid)
        if force:
            shutil.rmtree(out, ignore_errors=True)
        t0 = time.time()
        try:
            r = hook.run_restore(folder / "input.png", fid, source, seeds=hook.DEMO_SEEDS)
            s = r["pixel_summary"]
            print(f"{demo['id']:<10} w={fid:<4} {time.time() - t0:6.1f}s  "
                  f"observed {s['observed']:.0%} · inferred {s['inferred']:.0%} · invented {s['invented']:.0%}"
                  + (f"  WARN: {'; '.join(r['warnings'])}" if r["warnings"] else ""))
        except Exception as e:
            failures += 1
            print(f"{demo['id']:<10} w={fid:<4} FAILED: {type(e).__name__}: {e}")

sys.exit(1 if failures else 0)
