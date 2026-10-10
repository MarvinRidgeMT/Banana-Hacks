import cv2, numpy as np, random
from math import comb
from pathlib import Path

def _bezier(pts, n=200):
    pts = np.array(pts, float); t = np.linspace(0, 1, n)[:, None]; k = len(pts) - 1
    return sum(comb(k, i) * t**i * (1 - t)**(k - i) * pts[i] for i in range(k + 1)).astype(np.int32)

def scratches(x, mask, rng):
    h, w = mask.shape
    for _ in range(rng.integers(1, 5)):
        n = 2 if rng.random() < 0.6 else 3   # mostly straight, sometimes a gentle curve
        pts = [(rng.integers(0, w), rng.integers(0, h)) for _ in range(n)]
        th = int(rng.choice([1, 1, 2, 2, 3, 4, 5]))   # mostly thin
        layer = np.zeros((h, w), np.uint8)
        cv2.polylines(layer, [_bezier(pts)], False, 255, th, cv2.LINE_AA)
        a = cv2.GaussianBlur(layer, (3, 3), 0).astype(np.float32) / 255 * rng.uniform(0.6, 0.95)
        val = rng.uniform(190, 245) if rng.random() < 0.7 else rng.uniform(10, 60)
        x[:] = x * (1 - a[..., None]) + val * a[..., None]
        mask[a > 0.3] = 1

def tear(x, mask, rng):
    h, w = mask.shape
    cx, cy = (0 if rng.random() < .5 else w), (0 if rng.random() < .5 else h)
    sx, sy = (1 if cx == 0 else -1), (1 if cy == 0 else -1)
    s = rng.uniform(0.1, 0.35) * min(h, w)
    a = (cx + sx * s * rng.uniform(.5, 1.5), cy); b = (cx, cy + sy * s * rng.uniform(.5, 1.5))
    edge = [(a[0] + (b[0] - a[0]) * t + rng.normal(0, s * .06),
             a[1] + (b[1] - a[1]) * t + rng.normal(0, s * .06)) for t in np.linspace(0, 1, 14)]
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.array([(cx, cy)] + edge, np.int32)], 1)
    _fill_paper(x, m, rng); mask |= m

def hole(x, mask, rng):
    h, w = mask.shape
    c = (rng.integers(0, w), rng.integers(0, h)); r = rng.uniform(0.03, 0.15) * min(h, w)
    ang = np.sort(rng.uniform(0, 2 * np.pi, 16))
    rad = r * rng.uniform(0.5, 1.3, 16)
    poly = np.stack([c[0] + rad * np.cos(ang), c[1] + rad * np.sin(ang)], 1).astype(np.int32)
    m = np.zeros((h, w), np.uint8); cv2.fillPoly(m, [poly], 1)
    _fill_paper(x, m, rng); mask |= m

def _fill_paper(x, m, rng):
    h, w = m.shape
    base = rng.uniform(200, 250) if rng.random() < 0.8 else rng.uniform(20, 60)
    paper = base + rng.normal(0, 6, (h, w))
    x[m == 1] = paper[m == 1][:, None] * np.array([0.92, 0.97, 1.0])

def foxing(x, mask, rng):
    h, w = mask.shape
    n = cv2.GaussianBlur(rng.random((h, w)).astype(np.float32), (0, 0), rng.uniform(3, 10))
    n = (n - n.min()) / (np.ptp(n) + 1e-6)
    m = n > rng.uniform(0.75, 0.9)
    region = np.zeros((h, w), bool)
    x0, y0 = rng.integers(0, w // 2), rng.integers(0, h // 2)
    region[y0:y0 + rng.integers(h // 4, h // 2), x0:x0 + rng.integers(w // 4, w // 2)] = True
    m &= region
    color = np.array([rng.uniform(60, 110), rng.uniform(100, 140), rng.uniform(140, 180)])  # brown, BGR
    op = rng.uniform(0.5, 0.9)
    x[m] = x[m] * (1 - op) + color * op
    mask[m] = 1

def crease(x, mask, rng):
    h, w = mask.shape
    if rng.random() < 0.5:
        p1, p2, off = (int(rng.integers(0, w)), 0), (int(rng.integers(0, w)), h), (4, 0)
    else:
        p1, p2, off = (0, int(rng.integers(0, h))), (w, int(rng.integers(0, h))), (0, 4)
    th = int(rng.integers(2, 6))
    shade = np.zeros((h, w), np.float32)
    cv2.line(shade, (p1[0] + off[0], p1[1] + off[1]), (p2[0] + off[0], p2[1] + off[1]), 1.0, th + 4)
    x[:] = x + cv2.GaussianBlur(shade, (0, 0), 3)[..., None] * rng.uniform(15, 40)
    m = np.zeros((h, w), np.uint8); cv2.line(m, p1, p2, 1, th)
    x[m == 1] = rng.uniform(170, 230); mask |= m

def dust(x, mask, rng):
    h, w = mask.shape
    for _ in range(rng.integers(5, 60)):
        c = (int(rng.integers(0, w)), int(rng.integers(0, h))); r = int(rng.integers(1, 4))
        v = float(rng.uniform(220, 255) if rng.random() < 0.6 else rng.uniform(0, 35))
        cv2.circle(x, c, r, (v, v, v), -1); cv2.circle(mask, c, r, 1, -1)

def age(x, rng):
    """Global aging. NOT added to the mask: these pixels still carry information."""
    c = rng.uniform(0.55, 1.0)
    x[:] = (x - 128) * c + 128 + rng.uniform(-10, 40)
    if rng.random() < 0.6:
        x[:] = x * np.array([rng.uniform(.75, .9), rng.uniform(.88, .97), 1.0])  # yellowing
    x[:] = x + rng.normal(0, rng.uniform(1, 7), x.shape)

def damage(img, rng=None):
    """img: HxWx3 uint8 BGR. Returns (damaged uint8 BGR, mask uint8 0/1 of lost-content pixels)."""
    rng = rng or np.random.default_rng()
    if rng.random() < 0.7:
        img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    x = img.astype(np.float32); mask = np.zeros(img.shape[:2], np.uint8)
    if rng.random() > 0.08:  # ~8% of samples stay undamaged
        for f, p in [(scratches, .7), (tear, .3), (hole, .35), (foxing, .4), (crease, .3), (dust, .6)]:
            if rng.random() < p:
                f(x, mask, rng)
    age(x, rng)
    out = np.clip(x, 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(40, 96))])
    return cv2.imdecode(enc, cv2.IMREAD_COLOR), mask

if __name__ == "__main__":
    # Preview: python training\damage_synth.py  ->  data\preview\*.png  (clean | damaged | mask)
    files = sorted(Path("data/clean").glob("*.jpg")); random.shuffle(files)
    out = Path("data/preview"); out.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(files[:12]):
        img = cv2.imread(str(f))
        if img is None:
            continue
        img = cv2.resize(img, (512, int(512 * img.shape[0] / img.shape[1])))
        d, m = damage(img)
        cv2.imwrite(str(out / f"{i:02d}.png"), np.hstack([img, d, cv2.cvtColor(m * 255, cv2.COLOR_GRAY2BGR)]))
    print("wrote previews to", out)