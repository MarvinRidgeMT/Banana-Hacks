import { useEffect, useRef, useState } from "react";
import { fileUrl } from "../lib/api";
import { drawOverlay, loadRegionMap, type RegionMap } from "../lib/regionMap";
import type { Result } from "../lib/types";
import { Swatch } from "./PhotoStage";

const SCAN_MS = 3400;

/** Per-row running totals of [real, rebuilt, invented] pixels, so the tally under the
 * photo is the true count of every pixel the scan line has passed, not an animation. */
function rowTotals(map: RegionMap): Int32Array {
  const out = new Int32Array((map.height + 1) * 3);
  for (let y = 0; y < map.height; y++) {
    let a = 0, b = 0, c = 0;
    for (let x = 0; x < map.width; x++) {
      const v = map.data[(y * map.width + x) * 4 + 2];
      if (v === 1) b++;
      else if (v === 2) c++;
      else a++;
    }
    const i = (y + 1) * 3, j = y * 3;
    out[i] = out[j] + a; out[i + 1] = out[j + 1] + b; out[i + 2] = out[j + 2] + c;
  }
  return out;
}

const fmt = (n: number) => n.toLocaleString("en-US");

/** The landing page's examination table: one real case, scanned once, every pixel tallied. */
export function HeroScanner({ result }: { result: Result }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [map, setMap] = useState<RegionMap | null>(null);
  const [totals, setTotals] = useState<Int32Array | null>(null);
  const [p, setP] = useState(0);
  const [peek, setPeek] = useState(false);
  const [labels, setLabels] = useState(true);
  const [run, setRun] = useState(0);

  useEffect(() => {
    let live = true;
    loadRegionMap(fileUrl(result.key, result.files.regions))
      .then((m) => {
        if (!live) return;
        setMap(m);
        setTotals(rowTotals(m));
      })
      .catch(() => live && setP(1));
    return () => {
      live = false;
    };
  }, [result.key, result.files.regions]);

  useEffect(() => {
    if (map && canvasRef.current) drawOverlay(map, canvasRef.current);
  }, [map]);

  // One scan pass when the map is ready (instant with reduced motion). "Scan again" replays it.
  useEffect(() => {
    if (!map) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setP(1);
      return;
    }
    let raf = 0;
    const t0 = performance.now() + 300;
    const tick = (t: number) => {
      const k = Math.max(0, Math.min(1, (t - t0) / SCAN_MS));
      setP(k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    setP(0);
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [map, run]);

  const row = map ? Math.round(p * map.height) : 0;
  const t = totals ? [totals[row * 3], totals[row * 3 + 1], totals[row * 3 + 2]] : [0, 0, 0];
  const seen = t[0] + t[1] + t[2];
  const total = map ? map.width * map.height : result.width * result.height;
  const scanning = p > 0 && p < 1;

  return (
    <figure className="w-full">
      <div className="lightbox relative mx-auto" style={{ aspectRatio: `${result.width} / ${result.height}`, maxHeight: "58vh" }}>
        <img
          src={fileUrl(result.key, result.files.restored)}
          crossOrigin="anonymous"
          alt={`The restored photo${labels ? ", with invented areas marked" : ""}`}
          className="absolute inset-0 h-full w-full"
          draggable={false}
        />
        <canvas
          ref={canvasRef}
          aria-hidden
          className="pointer-events-none absolute inset-0 h-full w-full transition-opacity duration-300"
          style={{ clipPath: `inset(0 0 ${(1 - p) * 100}% 0)`, opacity: labels && !peek ? 0.8 : 0 }}
        />
        <img
          src={fileUrl(result.key, result.files.original)}
          crossOrigin="anonymous"
          alt=""
          aria-hidden
          className="absolute inset-0 h-full w-full transition-opacity duration-200"
          style={{ opacity: peek ? 1 : 0 }}
          draggable={false}
        />
        {scanning && <div className="scan-line" style={{ top: `${p * 100}%` }} aria-hidden />}
        <span className="hud-corner tl" aria-hidden />
        <span className="hud-corner tr" aria-hidden />
        <span className="hud-corner bl" aria-hidden />
        <span className="hud-corner br" aria-hidden />
        {peek && <span className="scanner-chip left-3 top-3">The damaged scan</span>}
      </div>

      <figcaption className="mt-6">
        <dl className="tally grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4" aria-live="off">
          <div>
            <dt>Pixels examined</dt>
            <dd>{fmt(seen)}<span className="of"> / {fmt(total)}</span></dd>
          </div>
          {(["observed", "inferred", "invented"] as const).map((c, i) => (
            <div key={c}>
              <dt className="flex items-center gap-2">
                <Swatch cls={c} className="h-3 w-3" />
                {c === "observed" ? "Real" : c === "inferred" ? "Rebuilt" : "Invented"}
              </dt>
              <dd>
                {fmt(t[i])}
                <span className="of"> {seen ? ((100 * t[i]) / seen).toFixed(1) : "0.0"}%</span>
              </dd>
            </div>
          ))}
        </dl>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            className="scanner-btn"
            onPointerDown={() => setPeek(true)}
            onPointerUp={() => setPeek(false)}
            onPointerLeave={() => setPeek(false)}
            onKeyDown={(e) => (e.key === " " || e.key === "Enter") && setPeek(true)}
            onKeyUp={() => setPeek(false)}
          >
            Hold to see the damaged scan
          </button>
          <button type="button" className="scanner-btn" aria-pressed={labels} onClick={() => setLabels((v) => !v)}>
            {labels ? "Hide the labels" : "Show the labels"}
          </button>
          <button type="button" className="scanner-btn" onClick={() => setRun((r) => r + 1)}>
            Scan again
          </button>
        </div>
      </figcaption>
    </figure>
  );
}
