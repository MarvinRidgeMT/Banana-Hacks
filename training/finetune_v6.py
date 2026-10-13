"""v6: fine-tune the damage detector on hand-checked REAL damage, mixed 50/50 with v5 synthetic damage.

Real photos: data/real_eval/<name>.png + <name>_mask.png (white = lost). Photos still marked
<name>_unchecked (a model guess nobody has corrected) are skipped: they are not labels.

Honest score: k-fold cross-validation. Each fold trains on the other real photos and scores real photos
it never saw, for both v5 (before) and the fine-tuned model (after). Then a final model is trained on
all real photos and is adopted only if it beat v5 on the held-out folds.

    python training/paint_mask.py data/real_eval/loc_*.png      # correct the pre-filled masks first
    python training/finetune_v6.py                              # ~35 min on an M-series Mac
"""
import argparse, json, random, shutil, sys, time
from pathlib import Path
import cv2, numpy as np, torch
from torch.utils.data import ConcatDataset, DataLoader, Dataset, WeightedRandomSampler
import segmentation_models_pytorch as smp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_docs import device, to_tensor, predict, load
from train_v5 import Crops, score, fit

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "data" / "real_eval"


def truncated(path):
    """Half-downloaded JPEGs end in a flat grey block; they teach nothing and are dropped."""
    g = cv2.imread(str(path), 0)
    if g is None:
        return True
    rows = (g.std(1) < 1.0) & (np.abs(g.mean(1) - 128) < 8)
    return rows.mean() > 0.05


def real_items():
    items = []
    for p in sorted(REAL.glob("*.png")):
        if p.stem.endswith("_mask"):
            continue
        mp = p.with_name(p.stem + "_mask.png")
        if not mp.exists() or p.with_name(p.stem + "_unchecked").exists():
            continue
        img = fit(cv2.imread(str(p)))
        gt = cv2.resize(cv2.imread(str(mp), 0), img.shape[1::-1], interpolation=cv2.INTER_NEAREST) > 127
        items.append((p.name, img, gt))
    return items


class RealCrops(Dataset):
    def __init__(self, items, size=512, per=8):
        self.items, self.size, self.per = items, size, per
    def __len__(self):
        return len(self.items) * self.per
    def __getitem__(self, i):
        _, img, gt = self.items[i % len(self.items)]
        rng = np.random.default_rng()
        f = rng.uniform(0.6, 1.3)
        im = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)
        m = cv2.resize(gt.astype(np.uint8), im.shape[1::-1], interpolation=cv2.INTER_NEAREST)
        ph, pw = max(0, self.size - im.shape[0]), max(0, self.size - im.shape[1])
        if ph or pw:
            im = cv2.copyMakeBorder(im, 0, ph, 0, pw, cv2.BORDER_REFLECT); m = np.pad(m, ((0, ph), (0, pw)))
        y = rng.integers(0, im.shape[0] - self.size + 1); x = rng.integers(0, im.shape[1] - self.size + 1)
        im = im[y:y + self.size, x:x + self.size]; m = m[y:y + self.size, x:x + self.size]
        if rng.random() < 0.5:
            im = im[:, ::-1]; m = m[:, ::-1]
        im = np.clip((im.astype(np.float32) - 128) * rng.uniform(0.8, 1.2) + 128 + rng.uniform(-15, 15), 0, 255).astype(np.uint8)
        return to_tensor(np.ascontiguousarray(im)), torch.from_numpy(np.ascontiguousarray(m[None])).float()


def synth_files(exclude):
    fs = [p for p in sorted((ROOT / "data" / "loc_clean").glob("*.jpg")) if ("loc_" + p.stem) not in exclude]
    fs = [p for p in fs if not truncated(p)]
    random.Random(5).shuffle(fs)
    return fs


def train(init, real, synth, minutes, dev, batch, workers):
    rd, sd = RealCrops(real), Crops(synth)
    ds = ConcatDataset([rd, sd])
    w = [0.5 / len(rd)] * len(rd) + [0.5 / len(sd)] * len(sd)
    dl = DataLoader(ds, batch_size=batch, num_workers=workers, drop_last=True, persistent_workers=workers > 0,
                    sampler=WeightedRandomSampler(w, num_samples=batch * 150, replacement=True))
    model = load(init, dev).train()
    opt = torch.optim.AdamW(model.parameters(), lr=5e-5, weight_decay=1e-4)
    bce = torch.nn.BCEWithLogitsLoss(); dice = smp.losses.DiceLoss("binary", from_logits=True)
    end, ep = time.time() + minutes * 60, 0
    while time.time() < end:
        ep += 1; tot = n = 0
        for x, y in dl:
            x, y = x.to(dev), y.to(dev)
            o = model(x); loss = bce(o, y) + dice(o, y)
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); tot += loss.item(); n += 1
            if time.time() > end: break
        print(f"    epoch {ep}: loss {tot / max(n, 1):.3f}", flush=True)
    return model.eval()


def main():
    global REAL
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--fold-minutes", type=float, default=6)
    ap.add_argument("--final-minutes", type=float, default=10)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--init", default=str(ROOT / "weights" / "seg_v5_best.pth"))
    ap.add_argument("--real-dir", default=str(REAL))
    a = ap.parse_args()
    REAL = Path(a.real_dir)
    dev = device(); print("device:", dev, flush=True)
    real = real_items()
    unchecked = len(list(REAL.glob("*_unchecked")))
    print(f"{len(real)} hand-checked real photos ({unchecked} still unchecked, skipped)", flush=True)
    assert len(real) >= 6, "need at least 6 hand-checked real photos: run training/paint_mask.py first"
    random.Random(11).shuffle(real)
    synth = synth_files({p.stem for p in REAL.glob("*.png") if not p.stem.endswith("_mask")})
    print(f"{len(synth)} clean photos for synthetic damage (half-downloaded ones dropped)", flush=True)

    base = load(a.init, dev)
    before, after, per = [], [], []
    for k in range(a.folds):
        test = [it for i, it in enumerate(real) if i % a.folds == k]
        tr = [it for i, it in enumerate(real) if i % a.folds != k]
        print(f"fold {k + 1}/{a.folds}: train on {len(tr)} real, test on {len(test)} unseen real", flush=True)
        m = train(a.init, tr, synth, a.fold_minutes, dev, a.batch, a.workers)
        for name, img, gt in test:
            pb, pa = predict(base, img, dev), predict(m, img, dev)
            before.append((pb, gt)); after.append((pa, gt))
            per.append({"photo": name, "iou_v5": score([(pb, gt)])["iou"], "iou_v6": score([(pa, gt)])["iou"]})
        del m
    cv = {"v5": score(before), "v6": score(after), "per_photo": per, "n_real": len(real)}
    print("cross-validated on unseen real photos:", json.dumps({k: cv[k] for k in ("v5", "v6")}), flush=True)

    print("final model on all real photos", flush=True)
    final = train(a.init, real, synth, a.final_minutes, dev, a.batch, a.workers)
    out = ROOT / "runs" / "seg_v6_best.pth"; out.parent.mkdir(exist_ok=True)
    torch.save(final.state_dict(), out)
    val = synth[: max(20, len(synth) // 10)]
    syn = {}
    for name, m in (("v5", base), ("v6", final)):
        pairs = []
        for i, p in enumerate(val):
            from damage_v5 import damage
            dmg, gt = damage(fit(cv2.imread(str(p))), np.random.default_rng(70_000 + i))
            pairs.append((predict(m, dmg, dev), gt.astype(bool)))
        syn[name] = score(pairs)
    adopt = cv["v6"]["iou"] > cv["v5"]["iou"] and syn["v6"]["iou"] >= syn["v5"]["iou"] - 0.05
    report = {"cross_validated_real": cv, "synthetic_check": syn, "v6_adopted": adopt}
    (ROOT / "runs" / "v6_report.json").write_text(json.dumps(report, indent=2))
    if adopt:
        shutil.copy2(out, ROOT / "weights" / "seg_v6_best.pth")
    print(json.dumps({"real_v5": cv["v5"], "real_v6": cv["v6"], "synthetic": syn, "adopted": adopt}, indent=2))
    print("\nv6 is better on real damage -> weights/seg_v6_best.pth (SEG_WEIGHTS=weights/seg_v6_best.pth)" if adopt
          else "\nv6 did not beat v5 on unseen real photos; keep seg_v5_best.pth")


if __name__ == "__main__":
    main()
