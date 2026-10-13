"""Choose the live damage-detection setup on the 90 TRAINING real photos, then score it ONCE on the
40 unseen test photos, at higher resolution (longest side 2048, from extract_artefact.py --max 2048).

Variants: model (v7, v8 if trained) x our segmenter's working size (1024 px, or full 2048) x Microsoft
scratch detector (off, at its reference 256 px, at 512 px) x gate (keep a scratch mark only where our
model's probability >= g). The mask is widened by 2 px per 1024 px, as live.

    python training/extract_artefact.py --max 2048 && python training/eval_variants.py
Prints the server settings for the winner; writes runs/variants_report.json.
"""
import itertools, json, sys
from pathlib import Path
import cv2, numpy as np, torch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_docs import device, load
from train_v5 import thin
from finetune_v7 import load_set
from calibrate import prob as model_prob
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import scratch_ms

HI = ROOT / "data" / "artefact_photos_2048"
GATES = [0.0, 0.05, 0.15, 0.3]


def load_hi(stem):
    p = HI / f"{stem}.png"
    return (cv2.imread(str(p)), cv2.imread(str(HI / f"{stem}_mask.png"), 0) > 127,
            cv2.imread(str(HI / f"{stem}_ignore.png"), 0) > 127)


def configs(models):
    for m, res, ms in itertools.product(models, ["1024", "full"], ["off", "256", "512"]):
        for g in (GATES if ms != "off" else [0.0]):
            yield (m, res, ms, g)


def main():
    dev = device()
    models = {"v7": load(str(ROOT / "weights" / "seg_v7_best.pth"), dev)}
    if (ROOT / "runs" / "seg_v8.pth").exists():
        models["v8"] = load(str(ROOT / "runs" / "seg_v8.pth"), dev)
    train, test = load_set()
    split = {"train_90": [s for s, *_ in train], "test_40": [s for s, *_ in test]}
    cfgs = list(configs(models))
    acc = {k: {c: np.zeros(6, np.int64) for c in cfgs} for k in split}   # I, U, tp, pp, gg, thin hits / thin
    thin_n = {k: {c: 0 for c in cfgs} for k in split}
    for sname, stems in split.items():
        for i, stem in enumerate(stems):
            img, gt, ign = load_hi(stem)
            h, w = gt.shape
            keep = ~ign; gtk = gt & keep; t = thin(gtk)
            k = min(1.0, 1024 / max(h, w))
            small = cv2.resize(img, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)
            P = {}
            for name, m in models.items():
                P[(name, "1024")] = cv2.resize(model_prob(m, small, dev), (w, h), interpolation=cv2.INTER_LINEAR)
                P[(name, "full")] = model_prob(m, img, dev)
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            MS = {"256": scratch_ms.detect_prob(rgb, 256) >= 0.4, "512": scratch_ms.detect_prob(rgb, 512) >= 0.4}
            it = max(1, round(2 * max(h, w) / 1024))
            ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * it + 1, 2 * it + 1))
            for c in cfgs:
                name, res, ms, g = c
                p = P[(name, res)]
                m = p > 0.5
                if ms != "off":
                    x = MS[ms]
                    if g > 0:
                        x = x & (p >= g)
                    m = m | x
                m = cv2.dilate(m.astype(np.uint8), ker) > 0
                m &= keep
                a = acc[sname][c]
                a[0] += int((m & gtk).sum()); a[1] += int((m | gtk).sum()); a[2] += int((m & gtk).sum())
                a[3] += int(m.sum()); a[4] += int(gtk.sum()); a[5] += int((m & t).sum()); thin_n[sname][c] += int(t.sum())
            print(f"{sname} {i + 1}/{len(stems)}", flush=True)

    def sc(sname, c):
        a = acc[sname][c]
        return {"iou": round(float(a[0] / max(a[1], 1)), 3), "recall": round(float(a[2] / max(a[4], 1)), 3),
                "precision": round(float(a[2] / max(a[3], 1)), 3), "thin_recall": round(float(a[5] / max(thin_n[sname][c], 1)), 3)}
    base = ("v7", "1024", "256", 0.0)
    best = max(cfgs, key=lambda c: sc("train_90", c)["iou"])
    name = lambda c: f"{c[0]} @{c[1]} + MS {c[2]}" + (f" gate {c[3]}" if c[3] else "")
    rep = {"live_now": {"config": name(base), "train_90": sc("train_90", base), "test_40": sc("test_40", base)},
           "chosen_on_train": {"config": name(best), "train_90": sc("train_90", best), "test_40": sc("test_40", best)},
           "all_on_train": sorted(({"config": name(c), **sc("train_90", c)} for c in cfgs), key=lambda r: -r["iou"])}
    better = bool(rep["chosen_on_train"]["test_40"]["iou"] > rep["live_now"]["test_40"]["iou"])
    rep["adopt"] = better
    (ROOT / "runs" / "variants_report.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: rep[k] for k in ("live_now", "chosen_on_train", "adopt")}, indent=2))
    if better:
        m, res, ms, g = best
        wpath = "weights/seg_v7_best.pth" if m == "v7" else "weights/seg_v8_best.pth"
        if m == "v8":
            import shutil; shutil.copy2(ROOT / "runs" / "seg_v8.pth", ROOT / "weights" / "seg_v8_best.pth")
        print(f"\nBetter on the 40 unseen photos. Start the server with:\n  SEG_WEIGHTS={wpath} SEG_RES={0 if res == 'full' else 1024} "
              f"SEG_WITH_MS={int(ms != 'off')} MS_SCALE={ms if ms != 'off' else 256} MS_GATE={g} DOC_WEIGHTS=weights/seg_doc_v2.pth uvicorn api:app --port 8000")
    else:
        print("\nThe setup chosen on the training photos did not beat the live one on the unseen photos: keep the live setup.")


if __name__ == "__main__":
    main()
