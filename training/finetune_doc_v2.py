"""Document detector v2: fine-tune seg_doc_best on REAL damaged documents (ARTeFACT paper/parchment
items: manuscripts, maps, letters, posters, prints) mixed 50/50 with the synthetic pages it was trained
on. 70% of the real documents train, 30% are held out and never seen.

Adopted (weights/seg_doc_v2.pth) only if, on the held-out real documents, damage IoU improves AND on the
synthetic pages (where ink is known exactly) the share of surviving ink wrongly flagged does not rise by
more than 0.5 points: document mode must never erase writing.

    python training/extract_artefact.py --docs && python training/finetune_doc_v2.py --minutes 20
"""
import argparse, json, random, shutil, sys, time
from pathlib import Path
import cv2, numpy as np, torch
from torch.utils.data import ConcatDataset, DataLoader, WeightedRandomSampler
import segmentation_models_pytorch as smp
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_docs import device, predict, load, DocCrops, pages, evaluate as synth_eval
from finetune_v7 import RealCrops, scores

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "data" / "artefact_docs"


def load_set():
    items = []
    for p in sorted(ART.glob("*.png")):
        if p.stem.endswith(("_mask", "_ignore")):
            continue
        items.append((p.stem, cv2.imread(str(p)),
                      cv2.imread(str(p.with_name(p.stem + "_mask.png")), 0) > 127,
                      cv2.imread(str(p.with_name(p.stem + "_ignore.png")), 0) > 127))
    random.Random(2027).shuffle(items)
    k = int(len(items) * 0.7)
    return items[:k], items[k:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--init", default=str(ROOT / "weights" / "seg_doc_best.pth"))
    a = ap.parse_args()
    dev = device(); print("device:", dev, flush=True)
    train, test = load_set()
    assert len(train) >= 30, "run: python training/extract_artefact.py --docs"
    print(f"real damaged documents: {len(train)} train, {len(test)} held out", flush=True)
    rd, sd = RealCrops(train), DocCrops(pages("train"))
    w = [0.5 / len(rd)] * len(rd) + [0.5 / len(sd)] * len(sd)
    dl = DataLoader(ConcatDataset([rd, sd]), batch_size=a.batch, num_workers=a.workers, drop_last=True,
                    persistent_workers=a.workers > 0,
                    sampler=WeightedRandomSampler(w, num_samples=a.batch * 150, replacement=True))
    model = load(a.init, dev).train()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
    bce = torch.nn.BCEWithLogitsLoss(); dice = smp.losses.DiceLoss("binary", from_logits=True)
    out = ROOT / "runs" / "seg_doc_v2.pth"; out.parent.mkdir(exist_ok=True)
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
    old, new = load(a.init, dev), load(str(out), dev)
    real = {}
    for name, m in (("doc v1", old), ("doc v2", new)):
        real[name] = scores([(predict(m, img, dev), gt, ign) for _, img, gt, ign in test])
    syn = synth_eval({"doc v1": old, "doc v2": new}, dev)
    adopt = real["doc v2"]["iou"] > real["doc v1"]["iou"] and \
        syn["doc v2"]["ink_flagged_pct"] <= syn["doc v1"]["ink_flagged_pct"] + 0.5
    rep = {"real_heldout": real, "n_real_heldout": len(test), "synthetic_pages": syn, "adopted": adopt}
    if adopt:
        shutil.copy2(out, ROOT / "weights" / "seg_doc_v2.pth")
    (ROOT / "runs" / "doc_v2_report.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))
    print("\ndoc v2 adopted -> weights/seg_doc_v2.pth" if adopt else "\ndoc v2 not better; keep seg_doc_best.pth")


if __name__ == "__main__":
    main()
