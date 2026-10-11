"""End-to-end check of the API against a running server.

    python tests/smoke_test.py http://localhost:8000 path/to/photo.png [path/to/mask.png]

Uploads the photo, waits for the job, checks every artifact the website uses,
then checks the cache, the other fidelity steps, a re-painted mask, the demos,
and that bad input is rejected cleanly. Exits non-zero on the first failure.
"""
import io
import json
import sys
import time

import numpy as np
import requests
from PIL import Image

BASE = sys.argv[1].rstrip("/")
PHOTO = sys.argv[2]
MASK = sys.argv[3] if len(sys.argv) > 3 else None


def check(cond, msg):
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"ok   {msg}")


def wait(job, timeout=600):
    t0 = time.time()
    while job["status"] in ("queued", "running"):
        if time.time() - t0 > timeout:
            check(False, f"job {job['id'][:8]} finished within {timeout}s")
        time.sleep(0.5)
        job = requests.get(f"{BASE}/jobs/{job['id']}").json()
    return job


def get_png(key, rel):
    r = requests.get(f"{BASE}/results/{key}/{rel}")
    check(r.status_code == 200, f"GET {rel} -> 200")
    return Image.open(io.BytesIO(r.content))


h = requests.get(f"{BASE}/health").json()
check(h["ok"], f"health ok (pipeline={h['pipeline']})")

# 1. upload, no mask -> segmenter path
with open(PHOTO, "rb") as f:
    r = requests.post(f"{BASE}/restore", files={"file": f}, data={"fidelity": "0.7"})
check(r.status_code in (200, 202), f"POST /restore -> {r.status_code}")
job = wait(r.json())
check(job["status"] == "done", f"job done ({job.get('error')})")
res = job["result"]
key = res["key"]
check(res["mask_source"] == "segmenter" and res["human_edited_mask"] is False, "no mask -> segmenter, not human")

orig = get_png(key, res["files"]["original"])
restored = get_png(key, res["files"]["restored"])
check(restored.mode == "RGB", "restored is RGB")
check(restored.size == (res["width"], res["height"]), "restored size matches result")
label = np.asarray(get_png(key, res["files"]["label"]))
check(set(np.unique(label)) <= {0, 1, 2}, f"label values {sorted(set(np.unique(label).tolist()))} within 0/1/2")
regions = np.asarray(get_png(key, res["files"]["regions"]).convert("RGB"))
check((regions[:, :, 2] == label).all(), "regions.png blue channel == label")
ids = regions[:, :, 0].astype(int) | (regions[:, :, 1].astype(int) << 8)
check(set(np.unique(ids)) - {0} <= {r["id"] for r in res["regions"]}, "every region id in the PNG is in the list")
check(((ids > 0) <= (label > 0)).all(), "region ids only on changed pixels")
s = res["pixel_summary"]
check(abs(sum(s.values()) - 1) < 1e-6, "pixel_summary adds to 100%")
check(abs(s["invented"] - (label == 2).mean()) < 1e-6, "legend % matches the drawn map")
manifest = requests.get(f"{BASE}/results/{key}/{res['files']['manifest']}").json()
check(manifest["web"]["fidelity_requested"] == 0.7, "manifest records fidelity")
check(manifest["source_sha256"], "manifest has source_sha256")
for face in res["faces"]:
    get_png(key, face["file"])
check(True, f"{len(res['faces'])} faces served")

# 2. downloads are attachments
r = requests.get(f"{BASE}/results/{key}/{res['files']['restored']}?download=1")
check("attachment" in r.headers.get("content-disposition", ""), "download=1 sends an attachment")

# 3. cache: same photo again returns instantly with the same key
t0 = time.time()
with open(PHOTO, "rb") as f:
    r = requests.post(f"{BASE}/restore", files={"file": f}, data={"fidelity": "0.7"})
check(r.status_code == 200 and r.json()["status"] == "done", "re-upload is a cache hit")
check(r.json()["key"] == key and time.time() - t0 < 2, "cache hit is fast and keyed by photo")

# 4. the other fidelity steps were queued automatically
for fid in (0.3, 1.0):
    for _ in range(1200):
        r = requests.get(f"{BASE}/results/{key}", params={"fidelity": fid})
        if r.status_code == 200:
            break
        time.sleep(0.5)
    check(r.status_code == 200, f"fidelity {fid} cached in the background")

# 5. a painted mask on the same photo -> new key, marked human
if MASK:
    with open(MASK, "rb") as m:
        r = requests.post(f"{BASE}/restore", data={"key": key, "fidelity": "0.7", "all_fidelities": "false"},
                          files={"mask": m})
    job = wait(r.json())
    check(job["status"] == "done", f"brush-mask job done ({job.get('error')})")
    check(job["key"] != key, "painted mask gets its own cache key")
    check(job["result"]["human_edited_mask"] is True, "painted mask logged as human_edited_mask")
    m2 = requests.get(f"{BASE}/results/{job['key']}/{job['result']['files']['manifest']}").json()
    check(m2["web"]["mask_source"] in ("human_brush", "human_file"), f"manifest says a person drew the mask ({m2['web']['mask_source']})")

# 6. demos and metrics
d = requests.get(f"{BASE}/demos").json()
check(isinstance(d, list), f"/demos lists {len(d)} photos")
for demo in d:
    r = requests.get(f"{BASE}/results/{demo['key']}/{demo['thumb']}")
    check(r.status_code == 200, f"demo thumb {demo['id']}")
check(isinstance(requests.get(f"{BASE}/metrics").json(), dict), "/metrics is JSON")

# 7. bad input is rejected, not a crash
r = requests.post(f"{BASE}/restore", files={"file": ("x.png", b"not an image")})
check(r.status_code == 400, f"garbage upload -> 400 ({r.json().get('error')})")
r = requests.post(f"{BASE}/restore", data={"key": key, "fidelity": "7"})
check(r.status_code == 400, "fidelity out of range -> 400")
r = requests.get(f"{BASE}/results/{key}/../../etc/passwd")
check(r.status_code == 404, "path traversal -> 404")
r = requests.get(f"{BASE}/results/{'0' * 64}")
check(r.status_code == 404, "unknown key -> 404")
r = requests.get(f"{BASE}/results/{key}", params={"fidelity": 0.5})
check(r.status_code == 202 and r.json()["status"] == "missing", "uncomputed fidelity -> 202 missing")

print("\nALL CHECKS PASSED")
