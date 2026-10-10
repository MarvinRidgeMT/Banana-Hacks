"""Calibrate the Invention Map: are 'Invented' pixels really further from the truth than 'Inferred' ones?
Usage (from the repo root):  python training/eval_map.py [number_of_photos]"""
import sys, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2, numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from damage_synth import hole, tear, scratches, dust, age
from backend.pipeline.restore import restore
from backend.pipeline.invention_map import to_lab, TAU

K = int(sys.argv[1]) if len(sys.argv) > 1 else 6
OUT = ROOT / "test_inputs"; OUT.mkdir(exist_ok=True)
DOCS = ROOT / "docs"; DOCS.mkdir(exist_ok=True)

def load(f):
    img = cv2.imread(str(f))
    h, w = img.shape[:2]
    s = 1024 / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return img

def make_pair(img, seed):
    """Returns (damaged, truth, mask). The truth gets the SAME aging/tint/grain as the damaged copy,
    so the only difference between them is the damage itself."""
    rng = np.random.default_rng(seed)
    if rng.random() < 0.7:
        img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    x = img.astype(np.float32)
    mask = np.zeros(img.shape[:2], np.uint8)
    for _ in range(2):
        hole(x, mask, rng)                 # thick damage: this is where seeds can disagree
    if rng.random() < 0.6:
        tear(x, mask, rng)
    scratches(x, mask, rng)
    dust(x, mask, rng)
    s = int(rng.integers(1 << 30))
    clean = img.astype(np.float32)
    age(x, np.random.default_rng(s))
    age(clean, np.random.default_rng(s))
    dmg = np.clip(x, 0, 255).astype(np.uint8)
    _, enc = cv2.imencode(".jpg", dmg, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return cv2.imdecode(enc, cv2.IMREAD_COLOR), np.clip(clean, 0, 255).astype(np.uint8), mask

files = sorted((ROOT / "samples").glob("*.jpg"))[:K]
rng = np.random.default_rng(0)
sig_all, err_all, thick_all = [], [], []
for i, f in enumerate(files):
    t = time.time()
    dmg, truth, mask = make_pair(load(f), 100 + i)
    p = OUT / f"cal_{i}.png"
    cv2.imwrite(str(p), dmg)
    cv2.imwrite(str(OUT / f"cal_{i}_mask.png"), mask * 255)
    r = restore(str(p))
    truth_rgb = cv2.cvtColor(truth, cv2.COLOR_BGR2RGB)
    err = np.linalg.norm(to_lab(r["restored"]) - to_lab(truth_rgb), axis=-1)   # true error per pixel
    changed = r["label"] > 0
    idx = np.flatnonzero(changed.ravel())
    if len(idx) > 30000:
        idx = rng.choice(idx, 30000, replace=False)
    sig_all.append(r["sigma"].ravel()[idx])
    err_all.append(err.ravel()[idx])
    thick_all.append(r["thick"].ravel()[idx])
    print(f"[{i + 1}/{len(files)}] {f.name}: {int(changed.sum())} changed px, {time.time() - t:.0f}s", flush=True)

sig, err, thick = np.concatenate(sig_all), np.concatenate(err_all), np.concatenate(thick_all)

rows = []
for tau in np.arange(1.0, 16.5, 0.5):
    inf = sig <= tau
    inv = ~inf
    if inf.sum() < 100 or inv.sum() < 100:
        continue
    rows.append({"tau": float(tau), "err_inferred": float(err[inf].mean()),
                 "err_invented": float(err[inv].mean()), "frac_invented": float(inv.mean())})
cur = min(rows, key=lambda row: abs(row["tau"] - TAU))
rho = float(spearmanr(sig[thick], err[thick])[0]) if thick.sum() > 100 else float("nan")

# error by seed-spread decile, inside SDXL-generated regions only
qs = np.quantile(sig[thick], np.linspace(0, 1, 11)) if thick.sum() > 100 else []
dec = []
for a, b in zip(qs[:-1], qs[1:]):
    m = thick & (sig >= a) & (sig <= b)
    if m.sum():
        dec.append({"spread_lo": float(a), "spread_hi": float(b), "mean_error": float(err[m].mean())})

summary = {"photos": len(files), "pixels_sampled": int(len(err)), "tau_current": TAU,
           "at_current_tau": cur, "spearman_spread_vs_error_in_generated": rho,
           "sweep": rows, "error_by_spread_decile": dec}
(DOCS / "map_calibration.json").write_text(json.dumps(summary, indent=2))

fig, ax = plt.subplots(1, 2, figsize=(11, 4))
ax[0].plot([r_["tau"] for r_ in rows], [r_["err_inferred"] for r_ in rows], label="Inferred")
ax[0].plot([r_["tau"] for r_ in rows], [r_["err_invented"] for r_ in rows], label="Invented")
ax[0].axvline(TAU, ls="--", c="gray")
ax[0].set_xlabel("threshold τ (seed spread, L*)")
ax[0].set_ylabel("mean error vs. true photo (ΔE)")
ax[0].set_title("Invented pixels vs. Inferred pixels")
ax[0].legend()
ax[1].bar(range(len(dec)), [d["mean_error"] for d in dec])
ax[1].set_xlabel("seed-spread decile (generated regions, low → high)")
ax[1].set_ylabel("mean error (ΔE)")
ax[1].set_title(f"More seed disagreement → more error (ρ = {rho:.2f})")
fig.tight_layout()
fig.savefig(DOCS / "map_calibration.png", dpi=150)

ratio = cur["err_invented"] / max(cur["err_inferred"], 1e-6)
print(f"\nAt τ = {cur['tau']}: Inferred pixels are {cur['err_inferred']:.1f} ΔE from the true photo on average, "
      f"Invented pixels {cur['err_invented']:.1f} ΔE ({ratio:.1f}x further).")
print(f"Spearman correlation between seed spread and true error (generated regions): {rho:.2f}")
print("Saved docs/map_calibration.json and docs/map_calibration.png")
