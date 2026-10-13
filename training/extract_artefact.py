"""Extract the real damaged PHOTOS from ARTeFACT (Ivanova et al., "ARTeFACT: Benchmarking Segmentation
Models on Diverse Analogue Media Damage", 2024; huggingface.co/datasets/danielaivanova/damaged-media,
Academic Free License 3.0) into data/artefact_photos/<id>.png + <id>_mask.png + <id>_ignore.png.

Our mask means "content lost / covered, must be rebuilt": material loss, peel, dust, scratch, hair,
dirt, fold, cracks, puncture, burn marks. Not damage for us (left as is, like fading): writing, staining,
stamp, sticker, light leak. ARTeFACT's 255 (outside the photo, e.g. the mount) is ignored."""
import glob, io, sys
from pathlib import Path
import numpy as np, pyarrow.parquet as pq
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "artefact"
DOCS = "--docs" in sys.argv   # paper / parchment items that are not photos -> data/artefact_docs
OUT = ROOT / "data" / ("artefact_docs" if DOCS else "artefact_photos"); OUT.mkdir(parents=True, exist_ok=True)


def wanted(r):
    if DOCS:
        return r["type"] != "Photo" and r["material"] in ("Paper", "Parchment")
    return r["type"] == "Photo"

LOST = [1, 2, 3, 4, 5, 6, 7, 9, 13, 14]
MAX = 1024
import gc
n = 0
for f in sorted(glob.glob(str(SRC / "*.parquet"))):
    meta = pq.read_table(f, columns=["id", "type", "material"]).to_pylist()
    rows = [(i, r["id"]) for i, r in enumerate(meta) if wanted(r)]
    n += len(rows)
    todo = [(i, rid) for i, rid in rows if not (OUT / f"{rid}.png").exists()]
    if not todo:
        continue
    sizes = {}
    col = pq.read_table(f, columns=["annotation"]).column("annotation")   # one column at a time: low memory
    for i, rid in todo:
        ann = np.array(Image.open(io.BytesIO(col[i].as_py()["bytes"])))
        k = min(1.0, MAX / max(ann.shape))
        size = (max(1, round(ann.shape[1] * k)), max(1, round(ann.shape[0] * k)))
        sizes[rid] = size
        Image.fromarray(np.isin(ann, LOST).astype(np.uint8) * 255).resize(size, Image.NEAREST).save(OUT / f"{rid}_mask.png")
        Image.fromarray((ann == 255).astype(np.uint8) * 255).resize(size, Image.NEAREST).save(OUT / f"{rid}_ignore.png")
        del ann
    del col; gc.collect()
    col = pq.read_table(f, columns=["image"]).column("image")
    for i, rid in todo:
        img = Image.open(io.BytesIO(col[i].as_py()["bytes"])).convert("RGB")
        img.resize(sizes[rid], Image.LANCZOS).save(OUT / f"{rid}.png")
        del img
    del col; gc.collect()
    print(Path(f).name, "photos so far", n, flush=True)
print("items:", n, "->", OUT)
