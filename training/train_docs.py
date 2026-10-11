"""Fine-tune the damage segmenter (v4) for DOCUMENTS, on Apple GPU (MPS), CUDA or CPU.

Pages come from make_docs.py (clean page + exact ink mask); damage is added on the fly by
damage_synth.py, the same generator as the photo model, so damage masks are exact.
The key extra metric: how much INK the model wrongly calls damage (we must never erase text).

    python training/make_docs.py                       # once: data/docs_clean/{train,val}
    python training/train_docs.py --minutes 40         # -> runs/seg_doc_best.pth (+ weights/)
    python training/train_docs.py --eval-only          # v4 vs doc model on the held-out pages
"""
import argparse, json, shutil, sys, time
from pathlib import Path
import cv2, numpy as np, torch
from torch.utils.data import DataLoader, Dataset
import segmentation_models_pytorch as smp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from damage_synth import damage
from dataset import MEAN, STD

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "docs_clean"

def device():
    if torch.cuda.is_available(): return "cuda"
    if torch.backends.mps.is_available(): return "mps"
    return "cpu"

def pages(split):
    return sorted(p for p in (DATA / split).glob("doc*.png") if not p.stem.endswith("_ink"))

def to_tensor(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    return torch.from_numpy(((rgb - MEAN) / STD).transpose(2, 0, 1).copy()).float()

class DocCrops(Dataset):
    def __init__(self, files, size=512):
        self.files, self.size = files, size
    def __len__(self):
        return len(self.files)
    def __getitem__(self, i):
        rng = np.random.default_rng()
        img = cv2.imread(str(self.files[i]))
        f = rng.uniform(0.6, 1.25)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
        h, w = img.shape[:2]
        if min(h, w) < self.size:
            img = cv2.copyMakeBorder(img, 0, max(0, self.size - h), 0, max(0, self.size - w), cv2.BORDER_REFLECT)
            h, w = img.shape[:2]
        y, x = rng.integers(0, h - self.size + 1), rng.integers(0, w - self.size + 1)
        crop = np.ascontiguousarray(img[y:y + self.size, x:x + self.size])
        dmg, mask = damage(crop, rng)
        return to_tensor(dmg), torch.from_numpy(mask[None].astype(np.float32))

@torch.no_grad()
def predict(model, bgr, dev, win=512, stride=384):
    h, w = bgr.shape[:2]
    x = cv2.copyMakeBorder(bgr, 0, max(0, win - h), 0, max(0, win - w), cv2.BORDER_REFLECT)
    H, W = x.shape[:2]
    ys = list(range(0, H - win + 1, stride)); xs = list(range(0, W - win + 1, stride))
    if ys[-1] != H - win: ys.append(H - win)
    if xs[-1] != W - win: xs.append(W - win)
    prob = np.zeros((H, W), np.float32); cnt = np.zeros((H, W), np.float32)
    for yy in ys:
        for xx in xs:
            t = to_tensor(np.ascontiguousarray(x[yy:yy + win, xx:xx + win]))[None].to(dev)
            prob[yy:yy + win, xx:xx + win] += torch.sigmoid(model(t))[0, 0].float().cpu().numpy()
            cnt[yy:yy + win, xx:xx + win] += 1
    return (prob / cnt)[:h, :w] > 0.5

def load(path, dev):
    m = smp.Unet("resnet34", encoder_weights=None, classes=1)
    m.load_state_dict(torch.load(path, map_location="cpu")); return m.to(dev).eval()

def evaluate(models, dev, n=None):
    files = pages("val")[:n]
    res = {name: {"I": 0, "U": 0, "ink_hit": 0, "ink": 0} for name in models}
    for i, p in enumerate(files):
        clean = cv2.imread(str(p)); ink = cv2.imread(str(p.with_name(p.stem + "_ink.png")), 0) > 127
        dmg, gt = damage(clean, np.random.default_rng(10_000 + i)); gt = gt.astype(bool)
        keep = ink & ~gt                        # ink that survived the damage: must NOT be flagged
        for name, m in models.items():
            pr = predict(m, dmg, dev); r = res[name]
            r["I"] += int((pr & gt).sum()); r["U"] += int((pr | gt).sum())
            r["ink_hit"] += int((pr & keep).sum()); r["ink"] += int(keep.sum())
    out = {}
    for name, r in res.items():
        out[name] = {"damage_iou": round(r["I"] / max(r["U"], 1), 3),
                     "ink_flagged_pct": round(100 * r["ink_hit"] / max(r["ink"], 1), 2)}
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=40)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--init", default=str(ROOT / "weights" / "seg_v4_best.pth"))
    ap.add_argument("--eval-only", action="store_true")
    a = ap.parse_args()
    dev = device(); print("device:", dev, flush=True)
    out_path = ROOT / "runs" / "seg_doc_best.pth"; out_path.parent.mkdir(exist_ok=True)
    if not a.eval_only:
        train = pages("train"); assert train, f"no pages in {DATA}/train (run make_docs.py)"
        dl = DataLoader(DocCrops(train), batch_size=a.batch, shuffle=True, num_workers=a.workers,
                        drop_last=True, persistent_workers=a.workers > 0)
        model = load(a.init, dev).train()
        opt = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
        bce = torch.nn.BCEWithLogitsLoss(); dice = smp.losses.DiceLoss("binary", from_logits=True)
        end, ep = time.time() + a.minutes * 60, 0
        print(f"training on {len(train)} pages for {a.minutes:.0f} min, from {Path(a.init).name}", flush=True)
        while time.time() < end:               # fixed time budget; no model selection on the val pages
            ep += 1; tot = 0.0; t0 = time.time()
            for x, y in dl:
                x, y = x.to(dev), y.to(dev)
                out = model(x); loss = bce(out, y) + dice(out, y)
                opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); tot += loss.item()
                if time.time() > end: break
            print(f"  epoch {ep}: loss {tot / len(dl):.3f}  ({time.time() - t0:.0f}s)", flush=True)
        torch.save(model.state_dict(), out_path)
        shutil.copy2(out_path, ROOT / "weights" / "seg_doc_best.pth")
        print("saved", out_path, "and weights/seg_doc_best.pth", flush=True)
    models = {"v4 (photos)": load(a.init, dev)}
    if out_path.exists():
        models["doc model"] = load(out_path, dev)
    res = evaluate(models, dev)
    (ROOT / "runs" / "doc_eval.json").write_text(json.dumps(res, indent=2))
    print("\nHeld-out synthetic document pages (never trained on):")
    for name, r in res.items():
        print(f"  {name:<12}  damage IoU {r['damage_iou']:.3f}   ink wrongly flagged {r['ink_flagged_pct']:.2f}%")

if __name__ == "__main__":
    main()
