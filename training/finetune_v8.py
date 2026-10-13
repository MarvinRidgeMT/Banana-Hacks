"""v8: continue v7 with a loss that cares about THIN damage. Plain BCE + Dice scores every pixel
equally, so missing a whole 2-px crack costs almost nothing. v8 adds:
  * Tversky loss (alpha 0.3, beta 0.7): a missed damaged pixel costs more than a false alarm;
  * soft clDice (Shit et al., CVPR 2021): compares skeletons, so a crack must be found end to end.
Same data and split as v7 (90 real ARTeFACT photos + synthetic damage). Not adopted here: it is scored
against v7 by eval_variants.py on the same 40 unseen photos.

    python training/finetune_v8.py --minutes 20
"""
import argparse, sys, time
from pathlib import Path
import numpy as np, torch
import torch.nn.functional as F
from torch.utils.data import ConcatDataset, DataLoader, WeightedRandomSampler
import segmentation_models_pytorch as smp
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_docs import device, load
from train_v5 import Crops
from finetune_v6 import truncated
from finetune_v7 import load_set, RealCrops

ROOT = Path(__file__).resolve().parents[1]


def _erode(x):
    return -F.max_pool2d(-x, 3, 1, 1)


def _open(x):
    return F.max_pool2d(_erode(x), 3, 1, 1)


def soft_skel(x, iters=10):
    skel = F.relu(x - _open(x))
    for _ in range(iters):
        x = _erode(x)
        delta = F.relu(x - _open(x))
        skel = skel + F.relu(delta - skel * delta)
    return skel


def cldice_loss(logits, y, eps=1.0):
    p = torch.sigmoid(logits)
    sp, sy = soft_skel(p), soft_skel(y)
    tprec = ((sp * y).sum((1, 2, 3)) + eps) / (sp.sum((1, 2, 3)) + eps)
    tsens = ((sy * p).sum((1, 2, 3)) + eps) / (sy.sum((1, 2, 3)) + eps)
    return (1 - 2 * tprec * tsens / (tprec + tsens)).mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--init", default=str(ROOT / "weights" / "seg_v7_best.pth"))
    a = ap.parse_args()
    dev = device(); print("device:", dev, flush=True)
    train, _ = load_set()
    synth = [p for p in sorted((ROOT / "data" / "loc_clean").glob("*.jpg")) if not truncated(p)]
    rd, sd = RealCrops(train), Crops(synth)
    w = [0.5 / len(rd)] * len(rd) + [0.5 / len(sd)] * len(sd)
    dl = DataLoader(ConcatDataset([rd, sd]), batch_size=a.batch, num_workers=a.workers, drop_last=True,
                    persistent_workers=a.workers > 0,
                    sampler=WeightedRandomSampler(w, num_samples=a.batch * 150, replacement=True))
    model = load(a.init, dev).train()
    opt = torch.optim.AdamW(model.parameters(), lr=5e-5, weight_decay=1e-4)
    bce = torch.nn.BCEWithLogitsLoss()
    tv = smp.losses.TverskyLoss("binary", from_logits=True, alpha=0.3, beta=0.7)
    out = ROOT / "runs" / "seg_v8.pth"
    start = time.time(); end = start + a.minutes * 60; ep = 0
    print(f"v8: {len(train)} real + {len(synth)} synthetic-source photos, {a.minutes:.0f} min from {Path(a.init).name}", flush=True)
    while time.time() < end:
        ep += 1; tot = n = 0
        for x, y in dl:
            for g in opt.param_groups:
                g["lr"] = 5e-5 * (0.05 + 0.95 * 0.5 * (1 + np.cos(np.pi * min(1, (time.time() - start) / (a.minutes * 60)))))
            x, y = x.to(dev), y.to(dev)
            o = model(x)
            loss = bce(o, y) + tv(o, y) + 0.5 * cldice_loss(o, y)
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); tot += loss.item(); n += 1
            if time.time() > end: break
        print(f"  epoch {ep}: loss {tot / max(n, 1):.3f}", flush=True)
        torch.save(model.state_dict(), out)
    print("saved", out, "- now run: python training/eval_variants.py", flush=True)


if __name__ == "__main__":
    main()
