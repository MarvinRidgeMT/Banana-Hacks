"""Train damage segmenter v5 on hundreds of real Library of Congress photos (MPS / CUDA / CPU).

Starts from v4 and fine-tunes on data/loc_clean (Civil War-era glass plates, fetched by
fetch_loc.py) plus data/clean if present, with the v5 damage generator (adds long plate cracks
and edge chips, the damage v4 missed most on real scans).

    python training/fetch_loc.py --n 900          # once: ~600-900 photos -> data/loc_clean
    python training/train_v5.py --minutes 60      # -> runs/seg_v5_best.pth + runs/v5_report.json
    python training/train_v5.py --eval-only       # compare v4 vs v5 again

Evaluation (photo-level split, the held-out photos are never trained on):
  * synthetic: held-out photos with seeded v5 damage -> IoU and thin-crack recall
  * demos: the masks in backend/demos -> IoU vs those masks
v5 is copied to weights/seg_v5_best.pth only if it beats v4 on BOTH.
"""
import argparse, json, random, shutil, sys, time
from pathlib import Path
import cv2, numpy as np, torch
from torch.utils.data import DataLoader, Dataset
import segmentation_models_pytorch as smp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from damage_v5 import damage
from train_docs import device, to_tensor, predict, load

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ["inferred", "backup", "light", "study", "hero"]


def photos():
    fs = []
    for d in ("loc_clean", "clean"):
        p = ROOT / "data" / d
        if p.exists():
            fs += sorted(x for x in p.rglob("*") if x.suffix.lower() in (".jpg", ".jpeg", ".png"))
    random.Random(5).shuffle(fs)
    nval = max(20, len(fs) // 10)
    return fs[nval:], fs[:nval]


class Crops(Dataset):
    def __init__(self, files, size=512, per=4):
        self.files, self.size, self.per = files, size, per
    def __len__(self):
        return len(self.files) * self.per
    def __getitem__(self, i):
        rng = np.random.default_rng()
        img = cv2.imread(str(self.files[i % len(self.files)]))
        f = rng.uniform(0.5, 1.2)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
        if rng.random() < .5: img = img[:, ::-1]
        h, w = img.shape[:2]
        if min(h, w) < self.size:
            img = cv2.copyMakeBorder(img, 0, max(0, self.size - h), 0, max(0, self.size - w), cv2.BORDER_REFLECT)
            h, w = img.shape[:2]
        y, x = rng.integers(0, h - self.size + 1), rng.integers(0, w - self.size + 1)
        crop = np.ascontiguousarray(img[y:y + self.size, x:x + self.size])
        dmg, mask = damage(crop, rng)
        return to_tensor(dmg), torch.from_numpy(mask[None].astype(np.float32))


def thin(gt):
    """Thin damage (cracks, scratches): the part of the mask a 5x5 opening removes."""
    op = cv2.morphologyEx(gt.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
    return gt & ~op


def score(pairs):
    I = U = ti = tn = 0
    for pr, gt in pairs:
        I += int((pr & gt).sum()); U += int((pr | gt).sum())
        t = thin(gt); ti += int((pr & t).sum()); tn += int(t.sum())
    return {"iou": round(I / max(U, 1), 3), "thin_recall": round(ti / max(tn, 1), 3)}


def fit(img, mx=1024):
    h, w = img.shape[:2]; s = min(1.0, mx / max(h, w))
    return img if s == 1 else cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


def evaluate(models, dev, val):
    out = {}
    for name, m in models.items():
        syn = []
        for i, p in enumerate(val):
            clean = fit(cv2.imread(str(p)))
            dmg, gt = damage(clean, np.random.default_rng(50_000 + i))
            syn.append((predict(m, dmg, dev), gt.astype(bool)))
        dem = []
        for d in DEMOS:
            ip, mp = ROOT / "backend" / "demos" / f"{d}.png", ROOT / "backend" / "demos" / f"{d}_mask.png"
            if not (ip.exists() and mp.exists()): continue
            img = fit(cv2.imread(str(ip)))
            gt = cv2.resize(cv2.imread(str(mp), 0), (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST) > 127
            dem.append((predict(m, img, dev), gt))
        out[name] = {"synthetic_heldout": score(syn), "demo_masks": score(dem) if dem else None,
                     "n_heldout": len(syn), "n_demos": len(dem)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--init", default=str(ROOT / "weights" / "seg_v4_best.pth"))
    ap.add_argument("--eval-only", action="store_true")
    a = ap.parse_args()
    dev = device(); print("device:", dev, flush=True)
    train, val = photos()
    assert len(train) >= 50, "not enough photos: run  python training/fetch_loc.py --n 900  first"
    out_path = ROOT / "runs" / "seg_v5_best.pth"; out_path.parent.mkdir(exist_ok=True)
    if not a.eval_only:
        dl = DataLoader(Crops(train), batch_size=a.batch, shuffle=True, num_workers=a.workers,
                        drop_last=True, persistent_workers=a.workers > 0)
        model = load(a.init, dev).train()
        opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
        total = a.minutes * 60
        bce = torch.nn.BCEWithLogitsLoss(); dice = smp.losses.DiceLoss("binary", from_logits=True)
        start = time.time(); end = start + total; ep = 0
        print(f"training on {len(train)} photos ({len(val)} held out) for {a.minutes:.0f} min, from {Path(a.init).name}", flush=True)
        while time.time() < end:
            ep += 1; tot = n = 0; t0 = time.time()
            for x, y in dl:
                for g in opt.param_groups:   # cosine decay over the time budget
                    g["lr"] = a.lr * (0.05 + 0.95 * 0.5 * (1 + np.cos(np.pi * min(1, (time.time() - start) / total))))
                x, y = x.to(dev), y.to(dev)
                o = model(x); loss = bce(o, y) + dice(o, y)
                opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); tot += loss.item(); n += 1
                if time.time() > end: break
            print(f"  epoch {ep}: loss {tot / max(n, 1):.3f}  ({time.time() - t0:.0f}s, {n} batches)", flush=True)
            torch.save(model.state_dict(), out_path)
        print("saved", out_path, flush=True)
    models = {"v4": load(a.init, dev)}
    if out_path.exists(): models["v5"] = load(out_path, dev)
    res = evaluate(models, dev, val)
    res["photos"] = {"train": len(train), "heldout": len(val)}
    if "v5" in res:
        v4, v5 = res["v4"], res["v5"]
        better = v5["synthetic_heldout"]["iou"] > v4["synthetic_heldout"]["iou"] and (
            v5["demo_masks"] is None or v5["demo_masks"]["iou"] >= v4["demo_masks"]["iou"])
        res["v5_adopted"] = better
        if better:
            shutil.copy2(out_path, ROOT / "weights" / "seg_v5_best.pth")
    (ROOT / "runs" / "v5_report.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    if res.get("v5_adopted"):
        print("\nv5 is better -> weights/seg_v5_best.pth. Start the server with SEG_WEIGHTS=weights/seg_v5_best.pth")
    elif "v5" in res:
        print("\nv5 did NOT beat v4 on both checks; keep using seg_v4_best.pth")


if __name__ == "__main__":
    main()
