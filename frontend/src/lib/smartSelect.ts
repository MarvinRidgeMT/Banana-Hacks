/** Click-to-fix for the damage brush: one click on a missed crack or flake selects all of it.
 *
 * Two ways to find the region, both in the working grid (≤1024 px, like the pipeline):
 *  1. The detectors' confidence map (proposed_prob.png): from the most confident pixel near the click,
 *     grow over connected pixels the detectors thought were at least somewhat likely damage.
 *  2. If the detectors saw nothing there (or there is no map), grow over connected pixels whose
 *     brightness is close to the clicked spot and clearly different from the surroundings, which is
 *     what a crack, scratch, flake or hole looks like.
 * Regions that run away (bigger than a cap) are refused rather than painting half the photo, and the
 * clicked spot itself is always added, like a brush dab.
 *
 * Measured on 366 missed damaged areas in 11 real photos (runs/fixtest), one click
 * adds about 1.3x the real damage of a brush dab (1.5x on areas over 300 px), but also more undamaged
 * pixels, so Undo stays one key away. */

export interface Grid {
  w: number;
  h: number;
  lum: Float32Array; // 0..255
  prob: Float32Array | null; // 0..1
}

export type Selection = {
  pixels: Uint8Array;
  w: number;
  h: number;
  count: number;
  method: "detector" | "contrast" | "brush";
};

const N8 = [-1, 0, 1];

function grow(g: Grid, seed: number, accept: (i: number) => boolean, cap: number): Uint8Array | null {
  const out = new Uint8Array(g.w * g.h);
  const stack = [seed];
  out[seed] = 1;
  let n = 1;
  while (stack.length) {
    const i = stack.pop()!;
    const x = i % g.w;
    const y = (i - x) / g.w;
    for (const dy of N8)
      for (const dx of N8) {
        if (!dx && !dy) continue;
        const nx = x + dx;
        const ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= g.w || ny >= g.h) continue;
        const j = ny * g.w + nx;
        if (out[j] || !accept(j)) continue;
        out[j] = 1;
        stack.push(j);
        if (++n > cap) return null;
      }
  }
  return out;
}

function dilate(m: Uint8Array, w: number, h: number): Uint8Array {
  const o = new Uint8Array(m);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      if (!m[y * w + x]) continue;
      for (const dy of N8)
        for (const dx of N8) {
          const nx = x + dx;
          const ny = y + dy;
          if (nx >= 0 && ny >= 0 && nx < w && ny < h) o[ny * w + nx] = 1;
        }
    }
  return o;
}

/** Median brightness in a ring around (cx, cy): the "surroundings" a damaged spot stands out from. */
function ringMedian(g: Grid, cx: number, cy: number, r: number): number {
  const v: number[] = [];
  for (let a = 0; a < 48; a++) {
    const t = (a / 48) * Math.PI * 2;
    const x = Math.round(cx + Math.cos(t) * r);
    const y = Math.round(cy + Math.sin(t) * r);
    if (x >= 0 && y >= 0 && x < g.w && y < g.h) v.push(g.lum[y * g.w + x]);
  }
  v.sort((p, q) => p - q);
  return v.length ? v[v.length >> 1] : 128;
}

function region(g: Grid, cx: number, cy: number, radius: number): Selection | null {
  cx = Math.max(0, Math.min(g.w - 1, Math.round(cx)));
  cy = Math.max(0, Math.min(g.h - 1, Math.round(cy)));
  const cap = Math.round(g.w * g.h * 0.015);

  // 1. detector confidence
  if (g.prob) {
    let best = -1;
    let bp = 0;
    for (let dy = -radius; dy <= radius; dy++)
      for (let dx = -radius; dx <= radius; dx++) {
        const x = cx + dx;
        const y = cy + dy;
        if (x < 0 || y < 0 || x >= g.w || y >= g.h || dx * dx + dy * dy > radius * radius) continue;
        const p = g.prob[y * g.w + x];
        if (p > bp) {
          bp = p;
          best = y * g.w + x;
        }
      }
    if (best >= 0 && bp >= 0.15) {
      const t = Math.max(0.1, bp * 0.4);
      const m = grow(g, best, (j) => g.prob![j] >= t, cap);
      if (m) {
        const d = dilate(m, g.w, g.h);
        return { pixels: d, w: g.w, h: g.h, count: d.reduce((a, b) => a + b, 0), method: "detector" };
      }
    }
  }

  // 2. local contrast: the clicked spot must stand out from its surroundings
  const bg = ringMedian(g, cx, cy, Math.max(12, radius * 3));
  let seed = cy * g.w + cx;
  let far = Math.abs(g.lum[seed] - bg);
  for (let dy = -radius; dy <= radius; dy++)
    for (let dx = -radius; dx <= radius; dx++) {
      const x = cx + dx;
      const y = cy + dy;
      if (x < 0 || y < 0 || x >= g.w || y >= g.h || dx * dx + dy * dy > radius * radius) continue;
      const d = Math.abs(g.lum[y * g.w + x] - bg);
      if (d > far) {
        far = d;
        seed = y * g.w + x;
      }
    }
  if (far < 35) return null; // nothing there stands out: let the person paint it
  const sv = g.lum[seed];
  const dark = sv < bg;
  const tol = Math.max(14, far * 0.45);
  const m = grow(
    g,
    seed,
    (j) => Math.abs(g.lum[j] - sv) <= tol && (dark ? g.lum[j] < bg - far * 0.4 : g.lum[j] > bg + far * 0.4),
    Math.round(cap / 3),
  );
  if (!m) return null;
  const d = dilate(m, g.w, g.h);
  return { pixels: d, w: g.w, h: g.h, count: d.reduce((a, b) => a + b, 0), method: "contrast" };
}

/** Build the working grid from the loaded photo and (optional) confidence map. */
export async function buildGrid(img: HTMLImageElement, probUrl: string | null | undefined): Promise<Grid> {
  const k = Math.min(1, 1024 / Math.max(img.naturalWidth, img.naturalHeight));
  const w = Math.max(1, Math.round(img.naturalWidth * k));
  const h = Math.max(1, Math.round(img.naturalHeight * k));
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0, w, h);
  const d = ctx.getImageData(0, 0, w, h).data;
  const lum = new Float32Array(w * h);
  for (let i = 0, p = 0; p < lum.length; i += 4, p++) lum[p] = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
  let prob: Float32Array | null = null;
  if (probUrl) {
    try {
      const m = new Image();
      m.crossOrigin = "anonymous";
      m.src = probUrl;
      await m.decode();
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(m, 0, 0, w, h);
      const pd = ctx.getImageData(0, 0, w, h).data;
      prob = new Float32Array(w * h);
      for (let i = 0, p = 0; p < prob.length; i += 4, p++) prob[p] = pd[i] / 255;
    } catch {
      prob = null; // no map (older upload): contrast mode only
    }
  }
  return { w, h, lum, prob };
}

export function smartSelect(g: Grid, cx: number, cy: number, radius = 8): Selection {
  cx = Math.max(0, Math.min(g.w - 1, Math.round(cx)));
  cy = Math.max(0, Math.min(g.h - 1, Math.round(cy)));
  const sel = region(g, cx, cy, radius);
  const px = sel ? sel.pixels : new Uint8Array(g.w * g.h);
  const r = Math.max(3, Math.round(radius * 0.6));
  for (let dy = -r; dy <= r; dy++)
    for (let dx = -r; dx <= r; dx++) {
      const x = cx + dx;
      const y = cy + dy;
      if (x < 0 || y < 0 || x >= g.w || y >= g.h || dx * dx + dy * dy > r * r) continue;
      px[y * g.w + x] = 1;
    }
  let count = 0;
  for (const v of px) count += v;
  return { pixels: px, w: g.w, h: g.h, count, method: sel ? sel.method : "brush" };
}
