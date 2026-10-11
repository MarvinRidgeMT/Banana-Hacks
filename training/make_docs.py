"""Synthetic clean document pages for training a document damage detector.

Each page is drawn from scratch (paper texture + typed, printed, handwritten-style text,
forms, ledgers, signatures, stamps), so we also know EXACTLY where the ink is:
<name>.png is the clean page, <name>_ink.png marks ink. Damage is added at training time
by damage_synth.py (the same generator as the photo model), so masks stay exact.

    python training/make_docs.py --n 800 --val 80 --out data/docs_clean
"""
import argparse, json, math, random
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = {
    "print": ["LiberationSerif-Regular.ttf", "DejaVuSerif.ttf", "C059-Roman.otf", "P052-Roman.otf",
              "lmroman10-regular.otf", "URWBookman-Light.otf", "Lora-Variable.ttf", "Carlito-Regular.ttf",
              "LiberationSans-Regular.ttf", "Lato-Regular.ttf"],
    "italic": ["LiberationSerif-Italic.ttf", "DejaVuSerif-Italic.ttf", "C059-Italic.otf",
               "lmromanslant10-regular.otf", "URWBookman-LightItalic.otf"],
    "mono": ["LiberationMono-Regular.ttf", "NimbusMonoPS-Regular.otf", "DejaVuSansMono.ttf"],
    "hand": ["Z003-MediumItalic.otf", "URWBookman-LightItalic.otf", "C059-Italic.otf"],
}
WORDS = ("the of and to in a is that for it as was with be by on not he this are or his from at which "
         "but have an they you were her she all there their been one has more would will if so no when who "
         "dear sir madam received letter county society record deed hereby witness signed date year month "
         "december january march april june august october november estate property farm road street town "
         "church school family father mother son daughter brother sister married born died buried children "
         "dollars cents paid account balance total amount received payment rent tax office clerk court "
         "certify certificate registry number page volume book entry name residence age occupation farmer "
         "teacher merchant carpenter laborer widow pension soldier company regiment discharged service "
         "respectfully yours truly sincerely obedient servant regards please kindly inform forward copy").split()

def find_fonts():
    import subprocess
    try:
        files = subprocess.run(["fc-list", ":", "file"], capture_output=True, text=True).stdout.split()
    except Exception:
        files = []
    files = [f.rstrip(":") for f in files]
    found = {}
    for kind, names in FONT_CANDIDATES.items():
        found[kind] = [f for n in names for f in files if f.endswith("/" + n)]
    return found

def paper(rng, w, h):
    base = np.array(rng.choice([(246, 243, 235), (238, 232, 214), (250, 249, 245), (232, 222, 196), (240, 236, 226)]),
                    np.float32)
    low = np.array(Image.fromarray((rng.random((h // 64 + 2, w // 64 + 2)) * 255).astype(np.uint8))
                   .resize((w, h), Image.BICUBIC), np.float32) / 255 - 0.5
    fib = rng.normal(0, 1, (h, w)).astype(np.float32)
    img = base[None, None] + low[..., None] * rng.uniform(4, 14) + fib[..., None] * rng.uniform(1, 4)
    return np.clip(img, 0, 255)

def text_line(draw, xy, words, font, fill, hand=False, rng=None, max_w=10_000):
    x, y = xy
    for wd in words:
        dy = rng.normal(0, 1.2) if hand else 0
        bbox = draw.textbbox((0, 0), wd, font=font)
        ww = bbox[2] - bbox[0]
        if x + ww > max_w:
            break
        draw.text((x, y + dy), wd, font=font, fill=fill)
        x += ww + font.size * (0.35 + (rng.uniform(-0.05, 0.15) if hand else 0))
    return x

def signature(draw, rng, x, y, s):
    pts = [(x + i * s * 0.25 + rng.normal(0, s * 0.05), y + rng.normal(0, s * 0.18)) for i in range(int(rng.integers(6, 12)))]
    for a, b in zip(pts, pts[1:]):
        mid = ((a[0] + b[0]) / 2 + rng.normal(0, s * .1), (a[1] + b[1]) / 2 + rng.normal(0, s * .2))
        draw.line([a, mid, b], fill=255, width=int(rng.integers(1, 4)), joint="curve")

def stamp(rng, w, h):
    lay = Image.new("L", (w, h), 0); d = ImageDraw.Draw(lay)
    r = int(rng.integers(45, 80)); cx, cy = int(rng.integers(r, w - r)), int(rng.integers(h // 2, h - r))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=255, width=4)
    d.ellipse([cx - r + 9, cy - r + 9, cx + r - 9, cy + r - 9], outline=255, width=2)
    return lay.rotate(float(rng.uniform(-25, 25)), center=(cx, cy))

def page(rng, fonts, w=800, h=1040):
    ink = Image.new("L", (w, h), 0); d = ImageDraw.Draw(ink)
    kind = rng.choice(["letter", "typed", "form", "ledger", "news"], p=[.3, .2, .2, .15, .15])
    m = int(rng.integers(50, 90)); y = m
    pick = lambda k: str(rng.choice(fonts[k]))
    if kind in ("letter",):
        hand = rng.random() < 0.6
        f = ImageFont.truetype(pick("hand" if hand else "print"), int(rng.integers(22, 32)))
        lh = int(f.size * rng.uniform(1.4, 1.9))
        while y < h - m - 120:
            n = int(rng.integers(5, 12))
            text_line(d, (m + (rng.integers(0, 40) if rng.random() < .15 else 0), y), list(rng.choice(WORDS, n)), f, 255, hand, rng, w - m)
            y += lh
            if rng.random() < 0.12: y += lh
        signature(d, rng, w - m - 260, h - m - 60, 60)
    elif kind == "typed":
        f = ImageFont.truetype(pick("mono"), int(rng.integers(16, 22)))
        lh = int(f.size * rng.choice([1.3, 2.0]))
        while y < h - m:
            text_line(d, (m, y), list(rng.choice(WORDS, int(rng.integers(6, 14)))), f, 255, False, rng, w - m)
            y += lh
    elif kind == "form":
        fl = ImageFont.truetype(pick("print"), int(rng.integers(14, 20)))
        fh = ImageFont.truetype(pick("hand"), int(rng.integers(20, 28)))
        rows, cols = int(rng.integers(8, 16)), int(rng.integers(2, 5))
        rh = (h - 2 * m) // rows; cw = (w - 2 * m) // cols
        for r in range(rows + 1): d.line([(m, m + r * rh), (w - m, m + r * rh)], fill=255, width=int(rng.integers(1, 3)))
        for c in range(cols + 1): d.line([(m + c * cw, m), (m + c * cw, m + rows * rh)], fill=255, width=int(rng.integers(1, 3)))
        for r in range(rows):
            for c in range(cols):
                d.text((m + c * cw + 5, m + r * rh + 3), str(rng.choice(WORDS)).title(), font=fl, fill=255)
                if rng.random() < 0.7:
                    text_line(d, (m + c * cw + 10, m + r * rh + rh * 0.4), list(rng.choice(WORDS, int(rng.integers(1, 3)))), fh, 255, True, rng, m + (c + 1) * cw - 5)
    elif kind == "ledger":
        f = ImageFont.truetype(pick(rng.choice(["mono", "hand"])), int(rng.integers(16, 24)))
        lh = int(f.size * 1.6)
        for xx in np.linspace(m, w - m, int(rng.integers(3, 6))): d.line([(xx, m), (xx, h - m)], fill=255, width=1)
        while y < h - m:
            d.line([(m, y + lh - 4), (w - m, y + lh - 4)], fill=255, width=1)
            d.text((m + 6, y), str(rng.choice(WORDS)).title(), font=f, fill=255)
            d.text((w - m - 120, y), f"{rng.integers(1, 999)}.{rng.integers(0, 99):02d}", font=f, fill=255)
            y += lh
    else:  # news: two columns of small print + headline
        fh = ImageFont.truetype(pick("print"), int(rng.integers(34, 48)))
        text_line(d, (m, y), list(rng.choice(WORDS, 4)), fh, 255, False, rng, w - m); y += int(fh.size * 1.8)
        f = ImageFont.truetype(pick("print"), int(rng.integers(12, 16))); lh = int(f.size * 1.35)
        col_w = (w - 2 * m - 20) // 2
        for c in range(2):
            yy = y
            while yy < h - m:
                text_line(d, (m + c * (col_w + 20), yy), list(rng.choice(WORDS, 8)), f, 255, False, rng, m + c * (col_w + 20) + col_w)
                yy += lh
    if rng.random() < 0.25:
        ink = Image.fromarray(np.maximum(np.array(ink), (np.array(stamp(rng, w, h)) * 0.8).astype(np.uint8)))
    if rng.random() < 0.5:
        ink = ink.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.3, 0.9))))
    a = np.array(ink, np.float32) / 255
    img = paper(rng, w, h)
    col = np.array(rng.choice([(25, 22, 20), (30, 35, 70), (70, 45, 25), (60, 55, 50), (20, 20, 20)]), np.float32)
    strength = rng.uniform(0.6, 1.0)
    img = img * (1 - a[..., None] * strength) + col[None, None] * a[..., None] * strength
    return np.clip(img, 0, 255).astype(np.uint8), (a > 0.25)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=800); ap.add_argument("--val", type=int, default=80)
    ap.add_argument("--out", default="data/docs_clean")
    a = ap.parse_args()
    fonts = find_fonts()
    missing = [k for k, v in fonts.items() if not v]
    if missing:
        raise SystemExit(f"no fonts found for {missing}; install some or edit FONT_CANDIDATES")
    print({k: len(v) for k, v in fonts.items()})
    for split, n, seed in (("train", a.n, 1), ("val", a.val, 999)):
        out = Path(a.out) / split; out.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            if (out / f"doc{i:04d}_ink.png").exists():
                continue                          # resume: each page has its own seed
            rng = np.random.default_rng(seed * 100_000 + i)
            img, ink = page(rng, fonts)
            Image.fromarray(img).save(out / f"doc{i:04d}.png")
            Image.fromarray(ink.astype(np.uint8) * 255).save(out / f"doc{i:04d}_ink.png")
        print(split, n, "pages ->", out)

if __name__ == "__main__":
    main()
