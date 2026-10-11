import cv2, numpy as np, torch
from PIL import Image
from diffusers import StableDiffusionXLInpaintPipeline, AutoencoderKL

INPAINT_VERSION = "6"   # bump this whenever inpainting behavior changes, so old cache entries aren't reused
MODEL = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1"
PROMPT = "old black and white photograph, film grain, natural lighting"
FACE_PROMPT = ("old black and white photograph, close-up portrait of a person's face, "
               "detailed eyes, natural skin, film grain")
NEG = "modern, color, cartoon, painting, deformed, blurry"
THIN_HALF_WIDTH = 4   # damage up to ~8 px wide is filled from context, not generated
MIN_CORE_AREA = 150   # ignore tiny thick bits
GROUP_PX = 48         # thick regions closer than this share one SDXL crop
MIN_CROP = 384
_pipe = None

def device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def get_pipe():
    global _pipe
    if _pipe is None:
        dev = device()
        dt = torch.float16 if dev != "cpu" else torch.float32
        vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=dt)
        try:
            p = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, vae=vae, torch_dtype=dt, variant="fp16")
        except Exception:
            p = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, vae=vae, torch_dtype=dt)
        if dev == "cuda":
            p.enable_model_cpu_offload()
        else:
            p = p.to(dev)
            p.enable_attention_slicing()
        _pipe = p
    return _pipe

def split_thin_thick(raw, m, dilate_px):
    """Decide on the UNDILATED mask: specks and scratches are thin, tears and holes are thick."""
    dist = cv2.distanceTransform(raw.astype(np.uint8), cv2.DIST_L2, 3)
    core = (dist > THIN_HALF_WIDTH).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(core, 8)
    big = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= MIN_CORE_AREA]
    core = np.isin(lab, big).astype(np.uint8)
    r = THIN_HALF_WIDTH + dilate_px + 2
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    thick = (cv2.dilate(core, k) > 0) & m
    return m & ~thick, thick

def thick_groups(thick):
    """Merge nearby thick regions so they share one crop. Returns [(region_mask, (x, y, w, h))]."""
    g = cv2.dilate(thick.astype(np.uint8), np.ones((GROUP_PX, GROUP_PX), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(g, 8)
    return [((lab == i) & thick, stats[i, :4]) for i in range(1, n)]

def _overlaps(a, b):
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

def _crop_box(box, W, H):
    x, y, w, h = box
    side = max(max(w, h) * 2 + 64, MIN_CROP)
    cx, cy = x + w // 2, y + h // 2
    x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
    x1, y1 = min(W, x0 + side), min(H, y0 + side)
    return max(0, x1 - side), max(0, y1 - side), x1, y1

def _sdxl(crop, cmask, seed, steps, guidance, prompt):
    ch, cw = cmask.shape
    s = 1024 / max(ch, cw)   # zoom the crop up so SDXL sees the damage at full detail
    tw, th = max(8, round(cw * s) // 8 * 8), max(8, round(ch * s) // 8 * 8)
    g = get_pipe()(prompt=prompt, negative_prompt=NEG,
                   image=Image.fromarray(crop).resize((tw, th), Image.LANCZOS),
                   mask_image=Image.fromarray((cmask * 255).astype(np.uint8)).resize((tw, th), Image.NEAREST),
                   height=th, width=tw, num_inference_steps=steps, guidance_scale=guidance,
                   strength=1.0,   # each seed draws the hole from scratch, not from the blurry pre-fill
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
    return np.asarray(g.resize((cw, ch), Image.LANCZOS))

def _poisson(src, dst, region, damaged):
    """Seamless blend (membrane / Poisson-style). `src` holds the generated content INCLUDING the
    model's own redrawn surroundings; `dst` has the real pixels around the region. The mismatch
    dst - src measured on a thin ring just outside the region is spread smoothly over the region
    (normalised convolution) and added to the generated pixels. Generated detail stays; its overall
    brightness and tone meet the photo exactly at the edge, so no pale patch and no seam.
    Only pixels inside the damage mask change in `dst`."""
    m = (cv2.dilate(region.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & damaged
    if m.sum() < 30:
        return False
    edge = (cv2.dilate(m.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0) & ~m
    if edge.sum() < 20:
        return False
    d = dst.astype(np.float32) - src.astype(np.float32)
    w = edge.astype(np.float32)
    sigma = float(np.clip(np.sqrt(m.sum()) / 4, 6, 60))
    num = cv2.GaussianBlur(d * w[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(w, (0, 0), sigma)[..., None]
    # far from any edge pixel the small-sigma estimate is unreliable: fall back to a wider one
    num2 = cv2.GaussianBlur(d * w[..., None], (0, 0), sigma * 3)
    den2 = cv2.GaussianBlur(w, (0, 0), sigma * 3)[..., None]
    t = np.clip(den / 0.05, 0, 1)
    corr = t * num / np.maximum(den, 1e-6) + (1 - t) * num2 / np.maximum(den2, 1e-6)
    res = np.clip(src.astype(np.float32) + corr, 0, 255).astype(np.uint8)
    dst[m] = res[m]
    return True


def _blend_in(out, orig, region, damaged, src=None):
    """Make a generated region sit in the photo:
    1. brightness: Poisson blend of `src` (generated crop incl. its own surroundings) against the
       intact pixels around the region; without `src`, a median brightness shift (old behaviour)
    2. color tint = median tint of the intact ring around it (sepia stays sepia)
    3. grain: add noise so its texture matches the photo's (same noise for every seed,
       so grain can't create fake seed disagreement in the Invention Map)."""
    k = np.ones((15, 15), np.uint8)
    r8 = region.astype(np.uint8)
    ring = (cv2.dilate(r8, k) > 0) & ~damaged
    if ring.sum() < 20:
        return
    lo = cv2.cvtColor(orig, cv2.COLOR_RGB2LAB).astype(np.float32)
    blended = src is not None and _poisson(src, out, region, damaged)
    lab = cv2.cvtColor(out, cv2.COLOR_RGB2LAB).astype(np.float32)
    for c in (1, 2):
        lab[..., c][region] = np.median(lo[..., c][ring])
    L, Lo = lab[..., 0], lo[..., 0]
    if not blended:
        band = region & ~(cv2.erode(r8, k) > 0)
        if band.any():
            L[region] += np.median(Lo[ring]) - np.median(L[band])
    grain_photo = (Lo - cv2.GaussianBlur(Lo, (0, 0), 1.5))[ring].std()
    grain_gen = (L - cv2.GaussianBlur(L, (0, 0), 1.5))[region].std()
    add = max(0.0, grain_photo ** 2 - grain_gen ** 2) ** 0.5
    if add > 0:
        noise = np.random.default_rng(1234).normal(0, add, L.shape).astype(np.float32)
        L[region] += noise[region]
    out[region] = cv2.cvtColor(lab.clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)[region]

def inpaint(img, mask, seeds=(11,), steps=20, guidance=6.0, dilate_px=4, face_boxes=()):
    """img: HxWx3 uint8 RGB. mask: HxW bool (True = content lost).
    Returns (one output per seed, used_mask, thin_mask, thick_mask).
    Thin damage is identical in every seed (inferred from context).
    Thick damage is generated per seed (seeds may disagree: that feeds the Invention Map).
    Regions that overlap a detected face get a face-specific prompt."""
    H, W = mask.shape
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate_px + 1, 2 * dilate_px + 1))
    m = cv2.dilate(mask.astype(np.uint8), k) > 0
    thin, thick = split_thin_thick(mask, m, dilate_px)
    telea = cv2.inpaint(img, m.astype(np.uint8), 5, cv2.INPAINT_TELEA)
    base = img.copy()
    base[m] = telea[m]
    groups = thick_groups(thick)
    is_face = [any(_overlaps(box, fb) for fb in face_boxes) for _, box in groups]
    print(f"SDXL regions: {len(groups)} ({sum(is_face)} on faces)  x  seeds: {len(seeds)}  =  {len(groups) * len(seeds)} runs")
    outs = []
    for seed in seeds:
        out = base.copy()
        for gi, (region, box) in enumerate(groups):
            x0, y0, x1, y1 = _crop_box(box, W, H)
            cm = region[y0:y1, x0:x1]
            prompt = FACE_PROMPT if is_face[gi] else PROMPT
            gen = _sdxl(base[y0:y1, x0:x1], cm, seed + 1000 * gi, steps, guidance, prompt)
            src = out.copy()
            src[y0:y1, x0:x1] = gen          # the whole generated crop: its own surroundings, no seam
            out[y0:y1, x0:x1][cm] = gen[cm]
            _blend_in(out, img, region, m, src=src)
        outs.append(out)
    return outs, m, thin, thick

def add_grain(out, orig, region, damaged, seed=1234):
    """Give context-filled (thin) pixels the photo's own grain, so filled scratches don't read as smooth pale bands.
    Same noise for every seed, so it can't create fake seed disagreement."""
    if not region.any():
        return
    ring = (cv2.dilate(region.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0) & ~damaged
    if ring.sum() < 20:
        return
    Lo = cv2.cvtColor(orig, cv2.COLOR_RGB2LAB).astype(np.float32)[..., 0]
    lab = cv2.cvtColor(out, cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0]
    gp = (Lo - cv2.GaussianBlur(Lo, (0, 0), 1.5))[ring].std()
    gg = (L - cv2.GaussianBlur(L, (0, 0), 1.5))[region].std()
    add = max(0.0, gp ** 2 - gg ** 2) ** 0.5
    if add <= 0:
        return
    noise = np.random.default_rng(seed).normal(0, add, L.shape).astype(np.float32)
    L[region] += noise[region]
    out[region] = cv2.cvtColor(lab.clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)[region]
