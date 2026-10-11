"""Fine-tune the segmenter on hand-labelled REAL damage (mixed 50/50 with synthetic).
Honest evaluation: --fold k trains on 2/3 of the real photos and scores the held-out 1/3 (never seen).
--fold -1 trains the final model on all real photos (no score)."""
import argparse, json, time, cv2, numpy as np, torch
from pathlib import Path
from torch.utils.data import Dataset, DataLoader, ConcatDataset, WeightedRandomSampler
import segmentation_models_pytorch as smp
from dataset import DamageDataset, MEAN, STD
from train_seg import get_split

def load_real(folds, fold):
    photos = sorted(p for p in Path("data/real_eval").glob("*.png") if not p.stem.endswith("_mask"))
    photos = [p for p in photos if p.with_name(p.stem + "_mask.png").exists()]
    items = []
    for i, p in enumerate(photos):
        img = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
        s = 1024 / max(img.shape[:2])                     # same working size as the pipeline
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_LANCZOS4)
        gt = cv2.resize(cv2.imread(str(p.with_name(p.stem + "_mask.png")), 0), img.shape[1::-1],
                        interpolation=cv2.INTER_NEAREST) > 127
        items.append((p.name, img, gt.astype(np.uint8), i % folds))
    train = [it for it in items if fold < 0 or it[3] != fold]
    test = [it for it in items if fold >= 0 and it[3] == fold]
    return train, test

class RealCrops(Dataset):
    def __init__(self, items, size=512):
        self.items, self.size = items, size
    def __len__(self):
        return len(self.items)
    def __getitem__(self, i):
        _, img, gt, _ = self.items[i]
        rng = np.random.default_rng()
        f = rng.uniform(0.7, 1.3)
        im = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_LINEAR)
        m = cv2.resize(gt, im.shape[1::-1], interpolation=cv2.INTER_NEAREST)
        ph, pw = max(0, self.size - im.shape[0]), max(0, self.size - im.shape[1])
        if ph or pw:
            im = np.pad(im, ((0, ph), (0, pw), (0, 0)), mode="reflect")
            m = np.pad(m, ((0, ph), (0, pw)))
        y = rng.integers(0, im.shape[0] - self.size + 1); x = rng.integers(0, im.shape[1] - self.size + 1)
        im = im[y:y + self.size, x:x + self.size]; m = m[y:y + self.size, x:x + self.size]
        if rng.random() < 0.5:
            im = im[:, ::-1]; m = m[:, ::-1]
        if rng.random() < 0.5:
            g = im.mean(2, keepdims=True); im = np.repeat(g, 3, 2)
        im = np.clip((im.astype(np.float32) - 128) * rng.uniform(0.8, 1.2) + 128 + rng.uniform(-15, 15), 0, 255)
        x = (im / 255 - MEAN) / STD
        return (torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1))).float(),
                torch.from_numpy(np.ascontiguousarray(m[None])).float())

@torch.no_grad()
def predict(model, img, win=512, stride=384):
    h, w = img.shape[:2]
    x = np.pad(img, ((0, max(0, win - h)), (0, max(0, win - w)), (0, 0)), mode="edge")
    H, W = x.shape[:2]
    t = torch.from_numpy(((x.astype(np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1))[None].cuda()
    ys = list(range(0, H - win + 1, stride)); xs = list(range(0, W - win + 1, stride))
    if ys[-1] != H - win: ys.append(H - win)
    if xs[-1] != W - win: xs.append(W - win)
    prob = np.zeros((H, W), np.float32); cnt = np.zeros((H, W), np.float32)
    for y in ys:
        for x0 in xs:
            p = torch.sigmoid(model(t[..., y:y + win, x0:x0 + win]))[0, 0].float().cpu().numpy()
            prob[y:y + win, x0:x0 + win] += p; cnt[y:y + win, x0:x0 + win] += 1
    return (prob / cnt)[:h, :w] > 0.5

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--init", default="runs/seg_v3_best.pth")
    a = ap.parse_args()
    train_real, test_real = load_real(a.folds, a.fold)
    synth_files, _ = get_split()
    real_ds, synth_ds = RealCrops(train_real), DamageDataset(synth_files, train=True)
    ds = ConcatDataset([real_ds, synth_ds])
    wts = [0.5 / len(real_ds)] * len(real_ds) + [0.5 / len(synth_ds)] * len(synth_ds)
    dl = DataLoader(ds, batch_size=8, num_workers=6, drop_last=True, pin_memory=True, persistent_workers=True,
                    sampler=WeightedRandomSampler(wts, num_samples=800, replacement=True))
    model = smp.Unet("resnet34", encoder_weights=None, classes=1)
    model.load_state_dict(torch.load(a.init, map_location="cpu")); model = model.cuda()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
    bce = torch.nn.BCEWithLogitsLoss(); dice = smp.losses.DiceLoss("binary", from_logits=True)
    scaler = torch.amp.GradScaler("cuda")
    end, ep = time.time() + a.minutes * 60, 0
    print(f"fold {a.fold}: training on {len(train_real)} real photos, testing on {len(test_real)} unseen")
    model.train()
    while time.time() < end:                               # fixed time budget; NO model selection on the test photos
        ep += 1; tot = 0.0
        for x, y in dl:
            x, y = x.cuda(non_blocking=True), y.cuda(non_blocking=True)
            with torch.autocast("cuda", dtype=torch.float16):
                out = model(x)
            loss = bce(out.float(), y) + dice(out.float(), y)
            opt.zero_grad(set_to_none=True); scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
            tot += loss.item()
        print(f"  epoch {ep}: loss {tot / len(dl):.3f}", flush=True)
    model.eval()
    name = "seg_v4_best.pth" if a.fold < 0 else f"ft_fold{a.fold}.pth"
    torch.save(model.state_dict(), f"runs/{name}")
    if test_real:
        I = U = 0; per = []
        for pname, img, gt, _ in test_real:
            pred = predict(model, img); g = gt.astype(bool)
            i, u = int((pred & g).sum()), int((pred | g).sum()); I += i; U += u
            per.append({"photo": pname, "iou": round(i / max(u, 1), 3)})
        res = {"fold": a.fold, "I": I, "U": U, "iou": round(I / max(U, 1), 3), "per_photo": per}
        Path(f"runs/ft_fold{a.fold}.json").write_text(json.dumps(res, indent=2))
        print(f"fold {a.fold}: held-out real IoU {res['iou']}  {per}")
    print("saved", f"runs/{name}")

if __name__ == "__main__":
    main()
