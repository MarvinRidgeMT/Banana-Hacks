"""Real-damage copy-paste: cut real damage (flakes, cracks, scratches, dust, losses) out of expert-labelled
ARTeFACT TRAINING photos and paste it onto clean Library of Congress photos. Every pasted pixel's mask is
exact, so thousands of training images with realistic damage come for free, and the damage looks like
real damage instead of our procedural approximations.

    bank = DamageBank(train_items)          # (name, bgr, mask, ignore) tuples, TRAINING photos only
    damaged, mask = bank.paste(clean_bgr, rng)
"""
import cv2, numpy as np


class DamageBank:
    def __init__(self, items, min_area=12, max_frac=0.01, max_side=220, pad=3):
        self.stamps = []
        for _, img, gt, ign in items:
            g = (gt & ~ign).astype(np.uint8)
            n, lab, st, _ = cv2.connectedComponentsWithStats(g, 8)
            H, W = g.shape
            for k in range(1, n):
                x, y, w, h, a = st[k]
                if a < min_area or a > max_frac * H * W or max(w, h) > max_side:
                    continue       # big losses come from the procedural generator; real pieces stay small
                x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
                m = (lab[y0:y1, x0:x1] == k).astype(np.uint8)
                self.stamps.append((img[y0:y1, x0:x1].copy(), m))
        if not self.stamps:
            raise ValueError("no damage found in the bank photos")
        areas = np.array([m.sum() for _, m in self.stamps], np.float64)
        self.p = np.sqrt(areas) / np.sqrt(areas).sum()      # favour bigger pieces a little

    def __len__(self):
        return len(self.stamps)

    def paste(self, clean, rng, n=None):
        x = clean.copy(); H, W = x.shape[:2]
        mask = np.zeros((H, W), np.uint8)
        n = n or int(rng.integers(3, 30))
        gray = rng.random() < 0.7
        if gray:
            x = cv2.cvtColor(cv2.cvtColor(x, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        for i in rng.choice(len(self.stamps), size=n, p=self.p):
            s, m = self.stamps[i]
            f = rng.uniform(0.6, 1.3)
            s = cv2.resize(s, None, fx=f, fy=f, interpolation=cv2.INTER_LINEAR)
            m = cv2.resize(m, (s.shape[1], s.shape[0]), interpolation=cv2.INTER_NEAREST)
            k = int(rng.integers(0, 4))
            s, m = np.rot90(s, k), np.rot90(m, k)
            if rng.random() < 0.5:
                s, m = s[:, ::-1], m[:, ::-1]
            h, w = m.shape
            if h >= H or w >= W:
                continue
            y0, x0 = int(rng.integers(0, H - h)), int(rng.integers(0, W - w))
            if gray:
                s = cv2.cvtColor(cv2.cvtColor(np.ascontiguousarray(s), cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
            a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.6)[..., None]   # soft 1-px edge
            roi = x[y0:y0 + h, x0:x0 + w].astype(np.float32)
            x[y0:y0 + h, x0:x0 + w] = (roi * (1 - a) + s.astype(np.float32) * a).astype(np.uint8)
            mask[y0:y0 + h, x0:x0 + w] |= m
        return x, mask
