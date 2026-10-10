import hashlib, io
import numpy as np
from PIL import Image, ImageOps

WORK = 1024  # SDXL's native size

def ingest(path):
    raw = open(path, "rb").read()                      # original bytes are never modified
    sha = hashlib.sha256(raw).hexdigest()              # cache key for every later stage
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    W, H = img.size
    scale = min(1.0, WORK / max(W, H))
    if scale < 1:
        img = img.resize((round(W * scale), round(H * scale)), Image.LANCZOS)
    arr = np.asarray(img).copy()
    spread = np.abs(arr.astype(np.int16) - arr.mean(2, keepdims=True)).mean()
    return {"sha256": sha, "image": arr, "scale": scale, "orig_size": (W, H),
            "grayscale": bool(spread < 2.0)}               # true B&W: never invent color
