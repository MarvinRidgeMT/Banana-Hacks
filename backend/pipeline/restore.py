import time, hashlib
import numpy as np
from pathlib import Path
from PIL import Image
from .ingest import ingest
from .inpaint import inpaint, INPAINT_VERSION
from .editlog import EditLog
from .invention_map import invention_map, medoid, summary, regions, overlay
from .manifest import write_manifest
from .faces import face_report, faces_that_could_have_been, detect_faces_damaged, load_face_hints

CACHE = Path("cache")

def get_mask(path, img):
    """Use <name>_mask.png if it exists (synthetic tests with known damage); otherwise run our segmenter."""
    shape = img.shape[:2]
    mp = Path(path).with_name(Path(path).stem + "_mask.png")
    if mp.exists():
        m = Image.open(mp).convert("L")
        if m.size != (shape[1], shape[0]):
            m = m.resize((shape[1], shape[0]), Image.NEAREST)
        return np.asarray(m) > 127, "provided mask file"
    from .segment import segment, MODEL_NAME
    m, _ = segment(img)
    return m, MODEL_NAME

def _cache_key(sha, mask, seeds, steps):
    mh = hashlib.sha256(np.packbits(mask).tobytes()).hexdigest()[:12]
    return CACHE / f"{sha[:16]}_{mh}_s{'-'.join(map(str, seeds))}_n{steps}_v{INPAINT_VERSION}.npz"

def restore(path, seeds=(11, 12, 13, 14), steps=20):
    d = ingest(path)
    img = d["image"]
    mask, mask_source = get_mask(path, img)
    log = EditLog(img)
    fboxes = load_face_hints(path) or detect_faces_damaged(img, mask)
    key = _cache_key(d["sha256"], mask, seeds, steps)
    if key.exists():   # same photo + mask + settings: skip SDXL entirely
        z = np.load(key)
        outs, used, thin, thick = list(z["outs"]), z["used"], z["thin"], z["thick"]
    else:
        outs, used, thin, thick = inpaint(img, mask, seeds=seeds, steps=steps, face_boxes=fboxes)
        CACHE.mkdir(exist_ok=True)
        np.savez_compressed(key, outs=np.stack(outs), used=used, thin=thin, thick=thick)
    if d["grayscale"]:   # grayscale lock: regenerated pixels can't introduce color
        for o in outs:
            g = o[used].mean(1, keepdims=True).round().astype(np.uint8)
            o[used] = np.repeat(g, 3, 1)
    k = medoid(outs, thick)
    out = outs[k]
    label, delta, sigma = invention_map(img, outs, out, used)
    faces = face_report(out, label, fboxes)
    log.record("inpainting", img, out, {
        "mask_source": mask_source,
        "model_thick": "sdxl-inpainting-0.1", "model_thin": "opencv-telea",
        "seeds": list(seeds), "displayed_seed": seeds[k], "steps": steps, "dilation_px": 4,
        "thin_px": int(thin.sum()), "thick_px": int(thick.sum())})
    return {"sha256": d["sha256"], "original": img, "restored": out, "seed_outputs": outs,
            "displayed_seed": seeds[k], "damage_mask": mask, "mask_source": mask_source,
            "mask": used, "thin": thin, "thick": thick,
            "label": label, "sigma": sigma, "pixel_summary": summary(label),
            "regions": regions(label, used), "face_regions": faces, "log": log}

if __name__ == "__main__":
    import sys
    p = sys.argv[1]
    t = time.time()
    r = restore(p)
    out = Path("outputs"); out.mkdir(exist_ok=True)
    stem = Path(p).stem
    Image.fromarray(r["restored"]).save(out / f"{stem}_restored.png")
    Image.fromarray(r["label"]).save(out / f"{stem}_map.png")   # 0/1/2 label PNG for other tools
    Image.fromarray((r["damage_mask"] * 255).astype(np.uint8)).save(out / f"{stem}_damage.png")
    ov = overlay(r["restored"], r["label"])
    Image.fromarray(np.hstack([r["original"], r["restored"], ov])).save(out / f"{stem}_compare.png")
    Image.fromarray(np.hstack(r["seed_outputs"])).save(out / f"{stem}_seeds.png")
    write_manifest(r, out / f"{stem}_manifest.json")
    if r["face_regions"]:
        fr = max(r["face_regions"], key=lambda f: f["invented_fraction"])
        if fr["invented_fraction"] > 0:
            grid, idx = faces_that_could_have_been(r["seed_outputs"], fr["bbox"])
            if grid is not None:
                Image.fromarray(grid).save(out / f"{stem}_faces.png")
                print(f"faces that could have been: {fr['id']}, seeds {idx}, "
                      f"{fr['invented_fraction']:.0%} of the face invented")
    th = r["thick"]
    if th.any():
        s = r["sigma"][th]
        print(f"seed spread inside generated regions: median {np.median(s):.1f}, 90th pct {np.percentile(s, 90):.1f}")
    outside = ((r["original"] != r["restored"]).any(-1) & ~r["mask"]).sum()
    print(f"mask from: {r['mask_source']}")
    print(f"done in {time.time() - t:.0f}s, displayed seed {r['displayed_seed']}")
    print(f"changed pixels outside the mask: {outside} (must be 0)")
    print("pixel summary:", r["pixel_summary"])
    for reg in r["regions"] + r["face_regions"]:
        print("  region", reg)
