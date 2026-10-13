"""Damage generator v5 = damage_synth + the damage our real-scan failures show we miss most:
long glass-plate cracks across the whole frame, chipped plate corners, and more thin scratches."""
import cv2, numpy as np
import damage_synth as D

def plate_crack(x, mask, rng):
    """Cracked glass negative: 1-3 long, nearly straight cracks crossing the frame, sometimes forking.
    Thin (1-3 px), bright or dark, often with a slight offset of the image across the crack."""
    h, w = mask.shape
    for _ in range(rng.integers(1, 4)):
        side = rng.integers(0, 4)
        p0 = [(rng.uniform(0, w), 0), (rng.uniform(0, w), h), (0, rng.uniform(0, h)), (w, rng.uniform(0, h))][side]
        ang = np.arctan2(h / 2 - p0[1], w / 2 - p0[0]) + rng.normal(0, 0.5)
        pts, (xx, yy) = [p0], p0
        L = rng.uniform(0.6, 1.4) * max(h, w)
        for _ in range(24):
            ang += rng.normal(0, 0.08); st = L / 24
            xx += np.cos(ang) * st; yy += np.sin(ang) * st; pts.append((xx, yy))
        th = int(rng.choice([1, 1, 2, 2, 3]))
        layer = np.zeros((h, w), np.uint8)
        cv2.polylines(layer, [np.array(pts, np.int32)], False, 255, th, cv2.LINE_AA)
        if rng.random() < 0.4:                       # a fork part-way along
            k = int(rng.integers(6, 18)); fa = ang + rng.choice([-1, 1]) * rng.uniform(0.4, 1.0)
            fx, fy = pts[k]; fp = [(fx, fy)]
            for _ in range(12):
                fa += rng.normal(0, 0.1); fx += np.cos(fa) * L / 30; fy += np.sin(fa) * L / 30; fp.append((fx, fy))
            cv2.polylines(layer, [np.array(fp, np.int32)], False, 255, max(1, th - 1), cv2.LINE_AA)
        a = cv2.GaussianBlur(layer, (3, 3), 0).astype(np.float32) / 255 * rng.uniform(0.7, 1.0)
        val = rng.uniform(205, 250) if rng.random() < 0.65 else rng.uniform(5, 45)
        x[:] = x * (1 - a[..., None]) + val * a[..., None]
        mask[a > 0.3] = 1

def edge_chip(x, mask, rng):
    """A chipped corner or edge of the plate: a jagged wedge of black (no emulsion) or white."""
    h, w = mask.shape
    cx, cy = (0 if rng.random() < .5 else w), (0 if rng.random() < .5 else h)
    s = rng.uniform(0.05, 0.45) * min(h, w)
    pts = [(cx, cy)] + [(cx + (1 if cx == 0 else -1) * s * rng.uniform(.2, 1.6) * np.cos(t),
                         cy + (1 if cy == 0 else -1) * s * rng.uniform(.2, 1.6) * np.sin(t))
                        for t in np.linspace(0, np.pi / 2, 9)]
    m = np.zeros((h, w), np.uint8); cv2.fillPoly(m, [np.array(pts, np.int32)], 1)
    m = D._ragged(m, rng, rng.uniform(1, 3))
    v = rng.uniform(0, 30) if rng.random() < 0.6 else rng.uniform(225, 255)
    x[m == 1] = v + rng.normal(0, 3, (int(m.sum()), 1)); mask |= m

def dense_flaking(x, mask, rng):
    """Emulsion lifting off across a large area: hundreds of small white/grey flecks and short
    streaks (the 'study' demo look). Much denser and wider than damage_synth.flaking."""
    h, w = mask.shape
    m = np.zeros((h, w), np.uint8)
    region = cv2.GaussianBlur(rng.random((h // 16 + 1, w // 16 + 1)).astype(np.float32), (0, 0), 2)
    region = cv2.resize(region, (w, h)) > np.quantile(region, rng.uniform(0.0, 0.6))
    for _ in range(int(rng.uniform(300, 2000) * h * w / 512 ** 2)):
        cx, cy = int(rng.integers(0, w)), int(rng.integers(0, h))
        if not region[cy, cx]: continue
        r = min(18, rng.pareto(2.5) * 2.5 + 1.2)
        if rng.random() < 0.35:   # short streak
            a = rng.uniform(0, np.pi); L = r * rng.uniform(3, 10)
            cv2.line(m, (cx, cy), (int(cx + L * np.cos(a)), int(cy + L * np.sin(a))), 1, max(1, int(r / 2)))
        else:
            pts = np.array([(cx + r * rng.uniform(.4, 1.4) * np.cos(t), cy + r * rng.uniform(.4, 1.4) * np.sin(t))
                            for t in np.linspace(0, 2 * np.pi, 7)[:-1]], np.int32)
            cv2.fillPoly(m, [pts], 1)
    if not m.any(): return
    v = rng.uniform(170, 250)
    op = cv2.GaussianBlur(m.astype(np.float32), (0, 0), .7) * rng.uniform(.75, 1)
    x[:] = x * (1 - op[..., None]) + (v + rng.normal(0, 8, (h, w, 1))) * op[..., None]
    mask |= m

OPS = [(D.scratches, .8), (plate_crack, .45), (edge_chip, .3), (dense_flaking, .35), (D.tear, .2), (D.hole, .25),
       (D.rip, .3), (D.craquelure, .35), (D.flaking, .25), (D.foxing, .3), (D.crease, .25), (D.dust, .55)]

def damage(img, rng=None):
    rng = rng or np.random.default_rng()
    if rng.random() < 0.7:
        img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    x = img.astype(np.float32); mask = np.zeros(img.shape[:2], np.uint8)
    if rng.random() > 0.08:
        for f, p in OPS:
            if rng.random() < p:
                f(x, mask, rng)
    D.age(x, rng)
    return D.degrade(np.clip(x, 0, 255).astype(np.uint8), rng), mask
