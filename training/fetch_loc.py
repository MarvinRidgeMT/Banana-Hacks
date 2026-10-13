"""Download public-domain Civil War-era photographs (Library of Congress, cwpb + cwpbh collections,
no known restrictions) and prepare them as clean training photos for the damage detector.

    python training/fetch_loc.py --n 900      # -> data/loc_raw/*.jpg, data/loc_clean/*.jpg

Polite: a few requests at a time, backs off on HTTP 429. Glass-plate edges are often chipped, so we
keep the central 86% of each frame, where real damage is rarer.
"""
import argparse, random, time, concurrent.futures as cf
from pathlib import Path
import urllib.request, urllib.error
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW, CLEAN = ROOT / "data" / "loc_raw", ROOT / "data" / "loc_clean"
BASE = "https://tile.loc.gov/storage-services/service/pnp/"

def ids(n, seed=7):
    r = random.Random(seed)
    a = [f"cwpb/{(i // 100) * 100:05d}/{i:05d}v.jpg" for i in r.sample(range(1, 7900), int(n * 0.68))]
    b = [f"cwpbh/{(i // 100) * 100:05d}/{i:05d}v.jpg" for i in r.sample(range(1, 5100), n - len(a))]
    return a + b

def fetch(path):
    out = RAW / path.replace("/", "_")
    if out.exists() and out.stat().st_size > 0:
        return "have"
    for attempt in range(6):
        try:
            req = urllib.request.Request(BASE + path, headers={"User-Agent": "ColdCase-hackathon/1.0 (training data)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                out.write_bytes(r.read())
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "missing"
            time.sleep(2 ** attempt)          # 429 / 5xx: back off
        except Exception:
            time.sleep(2 ** attempt)
    return "failed"

def prepare(src):
    dst = CLEAN / (src.stem + ".jpg")
    if dst.exists():
        return True
    img = cv2.imread(str(src))
    if img is None:
        return False
    h, w = img.shape[:2]
    m = 0.07
    img = img[int(h * m):int(h * (1 - m)), int(w * m):int(w * (1 - m))]
    s = 1024 / max(img.shape[:2])
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if g.std() < 18 or min(img.shape[:2]) < 400:        # blank, faded to nothing, or tiny
        return False
    cv2.imwrite(str(dst), img, [cv2.IMWRITE_JPEG_QUALITY, 94])
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=900)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True); CLEAN.mkdir(parents=True, exist_ok=True)
    stats = {}
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, s in enumerate(ex.map(fetch, ids(a.n)), 1):
            stats[s] = stats.get(s, 0) + 1
            if i % 100 == 0:
                print(f"  {i}/{a.n}: {stats}", flush=True)
    kept = sum(prepare(p) for p in sorted(RAW.glob("*.jpg")))
    print(f"download: {stats}; clean training photos: {kept} in {CLEAN}")

if __name__ == "__main__":
    main()
