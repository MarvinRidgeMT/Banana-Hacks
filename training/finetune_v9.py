"""v9: thousands of realistic training images + an honest tuning split.

Data mix per batch (all with exact masks):
  40%  real ARTeFACT photos   (70 TRAIN photos)
  30%  real damage pasted onto clean Library of Congress photos (damage_paste.py, 4,500+ real pieces
       from the 70 train photos x 600+ clean photos x random placement = effectively unlimited)
  30%  procedural damage (damage_v5) for large losses: tears, holes, broken corners
Split of the 130 ARTeFACT photos: TRAIN 70 / VAL 20 (checkpoint selection) / TEST 40 (the same 40
unseen photos as every earlier report; scored ONCE at the end). The 20 VAL photos come out of the old
90, so v9 sees 20 fewer real photos than v7 did; that is the price of choosing honestly.

Scored with the LIVE recipe (model > 0.5, + Microsoft scratch detector, widened 2 px), against v7.
weights/seg_v9_best.pth is written only if v9 beats v7 on the 40 test photos.

    python training/finetune_v9.py --minutes 40                         # continue from v7 (ResNet-34)
    python training/finetune_v9.py --minutes 60 --encoder tu-convnext_tiny   # ImageNet ConvNeXt, fresh
"""
import argparse, json, random, shutil, sys, time
from pathlib import Path
import cv2, numpy as np, torch
from torch.utils.data import ConcatDataset, DataLoader, Dataset, WeightedRandomSampler
import segmentation_models_pytorch as smp
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_docs import device, to_tensor, load
from train_v5 import Crops
from finetune_v6 import truncated
from finetune_v7 import load_set, RealCrops
from finetune_v8 import cldice_loss
from damage_paste import DamageBank
from calibrate import prob as model_prob
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import scratch_ms


class PasteCrops(Dataset):
    def __init__(self, files, bank, size=512, per=4):
        self.files, self.bank, self.size, self.per = files, bank, size, per
    def __len__(self):
        return len(self.files) * self.per
    def __getitem__(self, i):
        rng = np.random.default_rng()
        img = cv2.imread(str(self.files[i % len(self.files)]))
        f = rng.uniform(0.5, 1.2)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
        h, w = img.shape[:2]
        if min(h, w) < self.size:
            img = cv2.copyMakeBorder(img, 0, max(0, self.size - h), 0, max(0, self.size - w), cv2.BORDER_REFLECT)
            h, w = img.shape[:2]
        y, x = rng.integers(0, h - self.size + 1), rng.integers(0, w - self.size + 1)
        crop = np.ascontiguousarray(img[y:y + self.size, x:x + self.size])
        d, m = self.bank.paste(crop, rng)
        d = np.clip((d.astype(np.float32) - 128) * rng.uniform(0.85, 1.15) + 128 + rng.uniform(-12, 12), 0, 255).astype(np.uint8)
        return to_tensor(d), torch.from_numpy(m[None].astype(np.float32))


def build(encoder, init, dev):
    if encoder == "resnet34":
        return load(init, dev)
    m = smp.Unet(encoder, encoder_weights="imagenet", classes=1)
    return m.to(dev)


def live_score(model, items, ms_cache, dev):
    I = U = tp = pp = gg = 0
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    for name, img, gt, ign in items:
        p = model_prob(model, img, dev) > 0.5
        m = cv2.dilate((p | ms_cache[name]).astype(np.uint8), ker) > 0
        keep = ~ign; m &= keep; g = gt & keep
        a = int((m & g).sum()); I += a; U += int((m | g).sum()); tp += a; pp += int(m.sum()); gg += int(g.sum())
    return {"iou": round(I / max(U, 1), 3), "recall": round(tp / max(gg, 1), 3), "precision": round(tp / max(pp, 1), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=40)
    ap.add_argument("--encoder", default="resnet34")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--init", default=str(ROOT / "weights" / "seg_v7_best.pth"))
    a = ap.parse_args()
    dev = device(); print("device:", dev, flush=True)
    train90, test = load_set()
    rng = random.Random(7); idx = list(range(len(train90))); rng.shuffle(idx)
    val = [train90[i] for i in idx[:20]]; train = [train90[i] for i in idx[20:]]
    bank = DamageBank(train)
    damaged = {"loc_" + p.stem for p in (ROOT / "data" / "real_eval").glob("loc_*.png") if not p.stem.endswith("_mask")}
    clean = [p for p in sorted((ROOT / "data" / "loc_clean").glob("*.jpg")) if not truncated(p) and ("loc_" + p.stem) not in damaged]
    print(f"real: {len(train)} train / {len(val)} val / {len(test)} test; {len(bank)} real damage pieces; {len(clean)} clean canvases", flush=True)
    ms_cache = {n: scratch_ms.detect_prob(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), 256) >= 0.4 for n, img, _, _ in val + test}

    rd, pd, sd = RealCrops(train), PasteCrops(clean, bank), Crops(clean)
    w = [0.4 / len(rd)] * len(rd) + [0.3 / len(pd)] * len(pd) + [0.3 / len(sd)] * len(sd)
    dl = DataLoader(ConcatDataset([rd, pd, sd]), batch_size=a.batch, num_workers=a.workers, drop_last=True,
                    persistent_workers=a.workers > 0, sampler=WeightedRandomSampler(w, num_samples=a.batch * 150, replacement=True))
    model = build(a.encoder, a.init, dev).train()
    lr = a.lr or (5e-5 if a.encoder == "resnet34" else 2e-4)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    bce = torch.nn.BCEWithLogitsLoss(); dice = smp.losses.DiceLoss("binary", from_logits=True)
    out = ROOT / "runs" / f"seg_v9_{a.encoder.replace('/', '_')}.pth"
    best, best_val = -1.0, None
    start = time.time(); end = start + a.minutes * 60; ep = 0
    while time.time() < end:
        ep += 1; tot = n = 0
        for x, y in dl:
            for g in opt.param_groups:
                g["lr"] = lr * (0.05 + 0.95 * 0.5 * (1 + np.cos(np.pi * min(1, (time.time() - start) / (a.minutes * 60)))))
            x, y = x.to(dev), y.to(dev)
            o = model(x); loss = bce(o, y) + dice(o, y) + 0.2 * cldice_loss(o, y)
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); tot += loss.item(); n += 1
            if time.time() > end: break
        if ep % 3 == 0 or time.time() > end:
            model.eval(); v = live_score(model, val, ms_cache, dev); model.train()
            print(f"  epoch {ep}: loss {tot / max(n, 1):.3f}  val IoU {v['iou']} recall {v['recall']}", flush=True)
            if v["iou"] > best:
                best, best_val = v["iou"], v; torch.save(model.state_dict(), out)
        else:
            print(f"  epoch {ep}: loss {tot / max(n, 1):.3f}", flush=True)
    v7 = load(a.init, dev)
    if a.encoder == "resnet34":
        v9 = load(str(out), dev)
    else:
        v9 = smp.Unet(a.encoder, encoder_weights=None, classes=1); v9.load_state_dict(torch.load(out, map_location="cpu")); v9 = v9.to(dev).eval()
    rep = {"encoder": a.encoder, "val_20": {"v7": live_score(v7, val, ms_cache, dev), "v9": best_val},
           "test_40": {"v7": live_score(v7, test, ms_cache, dev), "v9": live_score(v9, test, ms_cache, dev)}}
    rep["adopt"] = bool(rep["test_40"]["v9"]["iou"] > rep["test_40"]["v7"]["iou"])
    if rep["adopt"]:
        shutil.copy2(out, ROOT / "weights" / "seg_v9_best.pth")
    (ROOT / "runs" / f"v9_report_{a.encoder.replace('/', '_')}.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))
    if rep["adopt"]:
        arch = "" if a.encoder == "resnet34" else f" SEG_ENCODER={a.encoder}"
        print(f"\nv9 beats v7 on the 40 unseen photos. Restart with SEG_WEIGHTS=weights/seg_v9_best.pth{arch}")
    else:
        print("\nv9 did not beat v7 on the 40 unseen photos; keep v7.")


if __name__ == "__main__":
    main()
