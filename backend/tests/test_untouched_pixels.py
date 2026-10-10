"""The untouched-pixel guarantee: whatever the generative models output, pixels outside the
damage mask are byte-for-byte identical to the input. Models are replaced with random noise,
so this tests the pipeline's own compositing, not the models' behaviour."""
import sys
from pathlib import Path
import numpy as np, cv2, pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))
from damage_synth import damage
import backend.pipeline.inpaint as inp
import backend.pipeline.codeformer as cf

@pytest.fixture(autouse=True)
def fake_models(monkeypatch):
    rng = np.random.default_rng(0)
    monkeypatch.setattr(inp, "_sdxl",
        lambda crop, cmask, seed, steps, guidance, prompt: rng.integers(0, 256, crop.shape, dtype=np.uint8))
    monkeypatch.setattr(cf, "restore_face",
        lambda face, fidelity=0.5: rng.integers(0, 256, face.shape, dtype=np.uint8))

SAMPLES = sorted((ROOT / "samples").glob("*.jpg"))[:8]

@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_pixels_outside_mask_never_change(path):
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    s = 512 / max(h, w)
    img = cv2.resize(img, (round(w * s), round(h * s)))
    dmg, mask = damage(img, np.random.default_rng(1))
    rgb = cv2.cvtColor(dmg, cv2.COLOR_BGR2RGB)
    outs, used, thin, thick = inp.inpaint(rgb, mask.astype(bool), seeds=(1, 2))
    for o in outs:
        inp.add_grain(o, rgb, thin, used)
    H, W = used.shape
    face_box = (W // 4, H // 4, W // 2, H // 2, 1.0)
    outs = [cf.face_pass(o, rgb, [face_box], used, strict=True) for o in outs]
    assert used[mask.astype(bool)].all(), "every damaged pixel must be inside the edit mask"
    for o in outs:
        changed_outside = int(((o != rgb).any(-1) & ~used).sum())
        assert changed_outside == 0, f"{changed_outside} pixels changed outside the mask"
