import type { ClassName } from "./types";

/** regions.png from the API: R,G = region id (16-bit, little-endian), B = class 0/1/2. */
export interface RegionMap {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

const CLASS_BY_VALUE: ClassName[] = ["observed", "inferred", "invented"];

export async function loadRegionMap(url: string): Promise<RegionMap> {
  const img = new Image();
  img.crossOrigin = "anonymous"; // the API sends CORS headers; needed to read pixels
  img.src = url;
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("This browser can't read the map image.");
  ctx.drawImage(img, 0, 0);
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  return { width: canvas.width, height: canvas.height, data };
}

export function sampleAt(map: RegionMap, x: number, y: number): { cls: ClassName; id: number } {
  const xi = Math.min(map.width - 1, Math.max(0, Math.floor(x)));
  const yi = Math.min(map.height - 1, Math.max(0, Math.floor(y)));
  const i = (yi * map.width + xi) * 4;
  return {
    cls: CLASS_BY_VALUE[map.data[i + 2]] ?? "observed",
    id: map.data[i] | (map.data[i + 1] << 8),
  };
}

const RGBA: Record<number, [number, number, number, number]> = {
  0: [154, 146, 130, 0], // real: left clear, so the original pixels read as themselves
  1: [44, 90, 160, 175], // rebuilt: blue
  2: [179, 38, 30, 205], // invented: stamp red, plus pink hatching below
};

/** Paint the Invention Map onto `canvas` at the photo's full resolution.
 * The page scales it with CSS, so it lines up with the photo exactly. */
export function drawOverlay(map: RegionMap, canvas: HTMLCanvasElement): void {
  canvas.width = map.width;
  canvas.height = map.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const out = ctx.createImageData(map.width, map.height);
  const o = out.data;
  // Stripe width follows the photo size so hatching stays visible when scaled down.
  const period = Math.max(10, Math.round(Math.max(map.width, map.height) / 70));
  const stripe = Math.max(3, Math.round(period * 0.32));
  for (let y = 0; y < map.height; y++) {
    for (let x = 0; x < map.width; x++) {
      const i = (y * map.width + x) * 4;
      const cls = map.data[i + 2];
      const c = RGBA[cls] ?? RGBA[0];
      if (cls === 2 && (x + y) % period < stripe) {
        o[i] = 231;
        o[i + 1] = 183;
        o[i + 2] = 177;
        o[i + 3] = 225;
      } else {
        o[i] = c[0];
        o[i + 1] = c[1];
        o[i + 2] = c[2];
        o[i + 3] = c[3];
      }
    }
  }
  ctx.putImageData(out, 0, 0);
}
