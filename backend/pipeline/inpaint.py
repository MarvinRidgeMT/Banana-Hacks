import cv2, numpy as np, torch
from PIL import Image
from diffusers import StableDiffusionXLInpaintPipeline, AutoencoderKL

MODEL = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1"
PROMPT = "old black and white photograph, film grain, natural lighting"
NEG = "modern, color, cartoon, painting"
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
    """Decide on the UNDILATED mask: specks and scratches are thin, tears and holes are thick.
    Returns (thin, thick) as parts of the dilated mask m."""
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

def _crop_box(box, W, H):
    x, y, w, h = box
    side = max(max(w, h) * 2 + 64, MIN_CROP)
    cx, cy = x + w // 2, y + h // 2
    x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
    x1, y1 = min(W, x0 + side), min(H, y0 + side)
    return max(0, x1 - side), max(0, y1 - side), x1, y1

def _sdxl(crop, cmask, seed, steps, guidance):
    ch, cw = cmask.shape
    s = 1024 / max(ch, cw)   # zoom the crop up so SDXL sees the damage at full detail
    tw, th = max(8, round(cw * s) // 8 * 8), max(8, round(ch * s) // 8 * 8)
    g = get_pipe()(prompt=PROMPT, negative_prompt=NEG,
                   image=Image.fromarray(crop).resize((tw, th), Image.LANCZOS),
                   mask_image=Image.fromarray((cmask * 255).astype(np.uint8)).resize((tw, th), Image.NEAREST),
                   height=th, width=tw, num_inference_steps=steps, guidance_scale=guidance,
                   strength=0.99, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
    return np.asarray(g.resize((cw, ch), Image.LANCZOS))

def _match_tone(out, orig, region, damaged):
    """Give generated pixels the same color tint as the intact pixels around them (sepia stays sepia)."""
    ring = (cv2.dilate(region.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0) & ~damaged
    if ring.sum() < 20:
        return
    lo = cv2.cvtColor(orig, cv2.COLOR_RGB2LAB)
    lab = cv2.cvtColor(out, cv2.COLOR_RGB2LAB)
    for c in (1, 2):
        lab[..., c][region] = np.median(lo[..., c][ring])
    out[region] = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)[region]

def inpaint(img, mask, seeds=(11,), steps=20, guidance=6.0, dilate_px=4):
    """img: HxWx3 uint8 RGB. mask: HxW bool (True = content lost).
    Returns (one output per seed, used_mask, thin_mask, thick_mask).
    Thin damage is identical in every seed (inferred from context).
    Thick damage is generated per seed (seeds may disagree: that feeds the Invention Map)."""
    H, W = mask.shape
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate_px + 1, 2 * dilate_px + 1))
    m = cv2.dilate(mask.astype(np.uint8), k) > 0
    thin, thick = split_thin_thick(mask, m, dilate_px)
    telea = cv2.inpaint(img, m.astype(np.uint8), 5, cv2.INPAINT_TELEA)
    base = img.copy()
    base[m] = telea[m]
    groups = thick_groups(thick)
    print(f"SDXL regions: {len(groups)}  x  seeds: {len(seeds)}  =  {len(groups) * len(seeds)} runs")
    outs = []
    for seed in seeds:
        out = base.copy()
        for gi, (region, box) in enumerate(groups):
            x0, y0, x1, y1 = _crop_box(box, W, H)
            cm = region[y0:y1, x0:x1]
            gen = _sdxl(base[y0:y1, x0:x1], cm, seed + 1000 * gi, steps, guidance)
            out[y0:y1, x0:x1][cm] = gen[cm]
        if thick.any():
            _match_tone(out, img, thick, m)
        outs.append(out)
    return outs, m, thin, thick
