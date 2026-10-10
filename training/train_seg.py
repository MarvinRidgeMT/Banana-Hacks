import argparse, time, torch
from pathlib import Path
from torch.utils.data import DataLoader, RandomSampler
from torch.utils.tensorboard import SummaryWriter
import segmentation_models_pytorch as smp
from dataset import DamageDataset, split_files

VAL_LIST = Path("data/val_files.txt")

def get_split():
    """Freeze the validation photos the first time, so later runs (v2) are scored on the same set."""
    files = sorted(Path("data/clean").glob("*.jpg"))
    if VAL_LIST.exists():
        val = [Path(l) for l in VAL_LIST.read_text().splitlines() if l.strip()]
        vs = {str(v) for v in val}
        train = [f for f in files if str(f) not in vs]
    else:
        train, val = split_files()
        VAL_LIST.write_text("\n".join(map(str, val)))
    return train, val

def evaluate(model, loader, dev):
    model.eval(); inter = union = 0.0
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
        for x, y in loader:
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            p = (model(x) > 0).float()
            inter += (p * y).sum().item()
            union += ((p + y) > 0).float().sum().item()
    model.train()
    return inter / max(union, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="v1")
    ap.add_argument("--hours", type=float, default=2.5)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--samples", type=int, default=2000, help="crops per epoch")
    a = ap.parse_args()
    dev = "cuda"

    train_f, val_f = get_split()
    print(f"train {len(train_f)} photos, val {len(val_f)} photos")
    tr, va = DamageDataset(train_f, train=True), DamageDataset(val_f, train=False)
    tl = DataLoader(tr, batch_size=a.batch, num_workers=a.workers, pin_memory=True,
                    persistent_workers=True, drop_last=True,
                    sampler=RandomSampler(tr, replacement=True, num_samples=a.samples))
    vl = DataLoader(va, batch_size=a.batch, num_workers=a.workers, pin_memory=True)

    model = smp.Unet("resnet34", encoder_weights="imagenet", classes=1).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    bce = torch.nn.BCEWithLogitsLoss()
    dice = smp.losses.DiceLoss("binary", from_logits=True)
    scaler = torch.amp.GradScaler("cuda")
    Path("runs").mkdir(exist_ok=True)
    writer = SummaryWriter(f"runs/seg_{a.name}")

    end, best, ep = time.time() + a.hours * 3600, -1.0, 0
    while time.time() < end:
        ep += 1; t0 = time.time(); total = 0.0
        for x, y in tl:
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.float16):
                out = model(x)
            loss = bce(out.float(), y) + dice(out.float(), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
            total += loss.item()
        iou = evaluate(model, vl, dev)
        writer.add_scalar("loss/train", total / len(tl), ep)
        writer.add_scalar("iou/val", iou, ep)
        if iou > best:
            best = iou
            torch.save(model.state_dict(), f"runs/seg_{a.name}_best.pth")
        print(f"epoch {ep}: loss {total / len(tl):.3f}  val IoU {iou:.3f}  best {best:.3f}  ({time.time() - t0:.0f}s)")
    print("done. best val IoU", round(best, 3))

if __name__ == "__main__":
    main()