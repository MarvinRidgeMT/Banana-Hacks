import cv2, numpy as np

OBSERVED, INFERRED, INVENTED = 0, 1, 2
EPS = 2.0   # Lab units: below this, a pixel counts as unchanged
TAU = 5.0   # L* units: seed spread in lightness above this = Invented (calibrated on Sunday)

def to_lab(x):
    """RGB uint8 -> real CIELAB units, where distances roughly match what people see."""
    l = cv2.cvtColor(x, cv2.COLOR_RGB2LAB).astype(np.float32)
    l[..., 0] *= 100 / 255
    l[..., 1:] -= 128
    return l

def medoid(outs, region):
    """Index of the seed output closest to the per-pixel median of all seeds (sharp, not blurred)."""
    if len(outs) == 1 or not region.any():
        return 0
    stack = np.stack([o[region].astype(np.float32) for o in outs])
    med = np.median(stack, 0)
    return int(np.argmin(((stack - med) ** 2).sum((1, 2))))

def invention_map(original, outs, shown, used):
    lo = to_lab(original)
    delta = np.linalg.norm(to_lab(shown) - lo, axis=-1)            # change vs. original
    if len(outs) > 1:
        sigma = np.stack([to_lab(o)[..., 0] for o in outs]).std(0)  # lightness only: tint is matched across seeds
    else:
        sigma = np.zeros(original.shape[:2], np.float32)
    sigma = cv2.GaussianBlur(sigma, (0, 0), 2)                    # so film grain doesn't read as disagreement
    changed = used | (delta > EPS)
    label = np.full(original.shape[:2], OBSERVED, np.uint8)
    label[changed & (sigma <= TAU)] = INFERRED
    label[changed & (sigma > TAU)] = INVENTED
    return label, delta, sigma

def summary(label):
    t = label.size
    return {"observed": round(float((label == OBSERVED).sum()) / t, 4),
            "inferred": round(float((label == INFERRED).sum()) / t, 4),
            "invented": round(float((label == INVENTED).sum()) / t, 4)}

def regions(label, used, min_px=200):
    """Per-region confidence = 1 - invented / changed. Goes in the manifest and the hover tooltip."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(used.astype(np.uint8), 8)
    out = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_px:
            continue
        comp = lab == i
        inv = int((label[comp] == INVENTED).sum())
        out.append({"id": len(out) + 1, "bbox": [int(v) for v in stats[i, :4]], "kind": "damage",
                    "pixels": int(comp.sum()), "confidence": round(float(1 - inv / comp.sum()), 3)})
    return out

COLORS = {OBSERVED: (46, 160, 67), INFERRED: (240, 170, 0), INVENTED: (220, 40, 40)}

def overlay(img, label, alpha=0.5):
    """Green / amber / red, with diagonal hatching on Invented so it reads without color."""
    out = img.astype(np.float32)
    for k, a in [(OBSERVED, 0.12), (INFERRED, alpha), (INVENTED, alpha + 0.1)]:
        m = label == k
        out[m] = out[m] * (1 - a) + np.array(COLORS[k], np.float32) * a
    h, w = label.shape
    yy, xx = np.mgrid[:h, :w]
    hatch = ((xx + yy) % 10 < 3) & (label == INVENTED)
    out[hatch] *= 0.4
    return out.clip(0, 255).astype(np.uint8)
