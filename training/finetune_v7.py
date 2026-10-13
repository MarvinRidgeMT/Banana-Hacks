"""v7: fine-tune the damage detector on 90 REAL damaged photos with expert masks (ARTeFACT), mixed
50/50 with v5 synthetic damage, and test on 40 other real damaged photos it never sees.

Real data: data/artefact_photos (training/extract_artefact.py). The 130 photos are split once, by
photo, with a fixed seed: 90 train, 40 test. Pixels outside the photo (ARTeFACT "background", e.g. the
mount) are not scored.

Reported on the 40 unseen real photos (and on our 5 demo masks):
  v5 alone | v5 + Microsoft scratch detector (what the site ran before) |
  v7 alone | v7 + Microsoft scratch detector
Each "+ MS" result is widened by 2 px exactly like the live pipeline (restore_hook.propose_mask).
weights/seg_v7_best.pth is written only if v7 + MS beats v5 + MS on the unseen real photos.

    python training/extract_artefact.py && python training/finetune_v7.py --minutes 25
"""
import argparse, json, random, shutil, sys, time
from pathlib import Path
import cv2, numpy as np, torch
from scipy import ndimage
from torch.utils.data import ConcatDataset, DataLoader, Dataset, WeightedRandomSampler
import segmentation_models_pytorch as smp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_docs import device, to_tensor, predict, load
from train_v5 import Crops, thin
from finetune_v6 import truncated

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
ART = ROOT / "data" / "artefact_photos"
DEMOS = ["inferred", "backup", "light", "study", "hero"]


def load_set():
    items = []
    for p in sorted(ART.glob("*.png")):
        if p.stem.endswith(("_mask", "_ignore")):
            continue
        img = cv2.imread(str(p))
        gt = cv2.imread(str(p.with_name(p.stem + "_mask.png")), 0) > 127
        ign = cv2.imread(str(p.with_name(p.stem + "_ignore.png")), 0) > 127
        items.append((p.stem, img, gt, ign))
    random.Random(2026).shuffle(items)
    return items[:90], items[90:]


def demo_set():
    out = []
    for d in DEMOS:
        img = cv2.imread(str(ROOT / "backend" / "demos" / f"{d}.png"))
        s = min(1.0, 1024 / max(img.shape[:2]))
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img
        gt = cv2.resize(cv2.imread(str(ROOT / "backend" / "demos" / f"{d}_mask.png"), 0), img.shape[1::-1],
                        interpolation=cv2.INTER_NEAREST) > 127
        out.append((d, img, gt, np.zeros_like(gt)))
    return out


class RealCrops(Dataset):
    def __init__(self, items, size=512, per=6):
        self.items, self.size, self.per = items, size, per
    def __len__(self):
        return len(self.items) * self.per
    def __getitem__(self, i):
        _, img, gt, _ = self.items[i % len(self.items)]
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
        if rng.random() < 0.6:                                    # most of our users' scans are B&W
            im = cv2.cvtColor(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        im = np.clip((im.astype(np.float32) - 128) * rng.uniform(0.8, 1.2) + 128 + rng.uniform(-15, 15), 0, 255).astype(np.uint8)
        return to_tensor(np.ascontiguousarray(im)), torch.from_numpy(np.ascontiguousarray(m[None])).float()


def scores(pairs):
    I = U = ti = tn = tp = pp = gg = 0
    for pr, gt, ign in pairs:
        keep = ~ign
        pr, gt = pr & keep, gt & keep
        I += int((pr & gt).sum()); U += int((pr | gt).sum())
        t = thin(gt); ti += int((pr & t).sum()); tn += int(t.sum())
        tp += int((pr & gt).sum()); pp += int(pr.sum()); gg += int(gt.sum())
    return {"iou": round(I / max(U, 1), 3), "recall": round(tp / max(gg, 1), 3),
            "precision": round(tp / max(pp, 1), 3), "thin_recall": round(ti / max(tn, 1), 3)}


def evaluate(models, sets, dev):
    from pipeline import scratch_ms
    ms_ok = scratch_ms.available()
    res = {}
    for sname, items in sets.items():
        res[sname] = {}
        cache_ms = {}
        for mname, m in models.items():
            alone, plus = [], []
            for name, img, gt, ign in items:
                p = predict(m, img, dev)
                alone.append((p, gt, ign))
                if ms_ok:
                    if name not in cache_ms:
                        cache_ms[name] = scratch_ms.detect(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                    u = ndimage.binary_dilation(p | cache_ms[name], iterations=2)
                    plus.append((u, gt, ign))
            res[sname][mname] = scores(alone)
            if ms_ok:
                res[sname][mname + " + MS"] = scores(plus)
        res[sname]["n"] = len(items)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=25)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--init", default=str(ROOT / "weights" / "seg_v5_best.pth"))
    ap.add_argument("--eval-only", action="store_true")
    a = ap.parse_args()
    dev = device(); print("device:", dev, flush=True)
    train, test = load_set()
    assert len(train) >= 50, "run training/extract_artefact.py first"
    print(f"real damaged photos: {len(train)} train, {len(test)} test (never trained on)", flush=True)
    out = ROOT / "runs" / "seg_v7_best.pth"; out.parent.mkdir(exist_ok=True)
    if not a.eval_only:
        synth = [p for p in sorted((ROOT / "data" / "loc_clean").glob("*.jpg")) if not truncated(p)]
        rd, sd = RealCrops(train), Crops(synth)
        w = [0.5 / len(rd)] * len(rd) + [0.5 / len(sd)] * len(sd)
        dl = DataLoader(ConcatDataset([rd, sd]), batch_size=a.batch, num_workers=a.workers, drop_last=True,
                        persistent_workers=a.workers > 0,
                        sampler=WeightedRandomSampler(w, num_samples=a.batch * 150, replacement=True))
        model = load(a.init, dev).train()
        opt = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
        bce = torch.nn.BCEWithLogitsLoss(); dice = smp.losses.DiceLoss("binary", from_logits=True)
        start = time.time(); end = start + a.minutes * 60; ep = 0
        while time.time() < end:
            ep += 1; tot = n = 0
            for x, y in dl:
                for g in opt.param_groups:
                    g["lr"] = 1e-4 * (0.05 + 0.95 * 0.5 * (1 + np.cos(np.pi * min(1, (time.time() - start) / (a.minutes * 60)))))
                x, y = x.to(dev), y.to(dev)
                o = model(x); loss = bce(o, y) + dice(o, y)
                opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); tot += loss.item(); n += 1
                if time.time() > end: break
            print(f"  epoch {ep}: loss {tot / max(n, 1):.3f}", flush=True)
            torch.save(model.state_dict(), out)
    models = {"v5": load(a.init, dev)}
    if out.exists():
        models["v7"] = load(str(out), dev)
    res = evaluate(models, {"real_test_40": test, "demo_5": demo_set()}, dev)
    t = res["real_test_40"]
    key5, key7 = ("v5 + MS", "v7 + MS") if "v5 + MS" in t else ("v5", "v7")
    adopt = "v7" in models and t[key7]["iou"] > t[key5]["iou"]
    res["v7_adopted"] = adopt
    if adopt:
        shutil.copy2(out, ROOT / "weights" / "seg_v7_best.pth")
    (ROOT / "runs" / "v7_report.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    print("\nv7 is better on unseen real photos -> weights/seg_v7_best.pth (SEG_WEIGHTS=weights/seg_v7_best.pth)"
          if adopt else "\nv7 did not beat v5 on unseen real photos; keep seg_v5_best.pth")


if __name__ == "__main__":
    main()
