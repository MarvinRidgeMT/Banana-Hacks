"""Pick real damaged Library of Congress plates for hand labelling and pre-fill each mask with the
current model's guess, so a person only corrects it (python training/paint_mask.py data/real_eval/loc_*.png).

A pre-filled mask is NOT a label until a person saves it: each gets a <name>_unchecked marker that
paint_mask.py deletes on save, and finetune_v6.py skips any photo still marked unchecked."""
import sys, cv2, numpy as np, torch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_docs import device, predict, load

ROOT = Path(__file__).resolve().parents[1]
# Chosen by eye from data/loc_clean: visible cracks, flaking, chips, flecks (indices into the sorted list).
PICKS = [44, 47, 48, 49, 57, 59, 64, 80, 81, 82, 159, 168, 173, 177, 178, 180, 181, 189,
         262, 290, 291, 293, 298, 303, 322, 323, 337, 338, 340, 352, 381]

def main():
    files = sorted((ROOT / "data" / "loc_clean").glob("*.jpg"))
    out = ROOT / "data" / "real_eval"; out.mkdir(parents=True, exist_ok=True)
    dev = device(); m = load(str(ROOT / "weights" / "seg_v5_best.pth"), dev)
    for i in PICKS:
        src = files[i]; name = "loc_" + src.stem
        img = cv2.imread(str(src)); dst = out / f"{name}.png"
        cv2.imwrite(str(dst), img)
        mp = out / f"{name}_mask.png"
        if mp.exists() and not (out / f"{name}_unchecked").exists():
            print("kept hand-checked", mp.name); continue
        guess = predict(m, img, dev)
        cv2.imwrite(str(mp), np.where(guess, 255, 0).astype(np.uint8))
        (out / f"{name}_unchecked").write_text("model guess, not yet checked by a person\n")
        print(f"{name}: guess covers {guess.mean():.1%}", flush=True)
    print(f"\n{len(PICKS)} photos in {out}. Correct them with:\n  python training/paint_mask.py data/real_eval/loc_*.png")

if __name__ == "__main__":
    main()
