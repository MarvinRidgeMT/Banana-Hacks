import { useEffect, useRef, useState } from "react";
import { fileUrl } from "../lib/api";
import { loadRegionMap } from "../lib/regionMap";
import type { Result } from "../lib/types";

/** "Take it apart": one real restoration, separated into the evidence it's made of.
 * Scroll drives a flat photo into an exploded 3D stack; every layer is computed from
 * this case's own files (scan, damage mask, label map, restoration), nothing is drawn by hand. */

type Layer = { key: string; title: string; body: string; src?: string; canvas?: HTMLCanvasElement | null };

const MAX = 640; // layer canvases are built at most this wide; CSS scales them

function tint(img: CanvasImageSource, w: number, h: number, pick: (r: number, g: number, b: number) => boolean,
  rgba: [number, number, number, number], hatch = false): HTMLCanvasElement {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0, w, h);
  const d = ctx.getImageData(0, 0, w, h); const p = d.data;
  const period = Math.max(8, Math.round(w / 60)); const stripe = Math.round(period * 0.4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    if (pick(p[i], p[i + 1], p[i + 2])) {
      const light = hatch && (x + y) % period >= stripe;
      p[i] = light ? 231 : rgba[0]; p[i + 1] = light ? 183 : rgba[1]; p[i + 2] = light ? 177 : rgba[2]; p[i + 3] = rgba[3];
    } else p[i + 3] = 0;
  }
  ctx.putImageData(d, 0, 0);
  return c;
}

async function loadImg(url: string) {
  const im = new Image(); im.crossOrigin = "anonymous"; im.src = url; await im.decode(); return im;
}

export function ExplodedView({ result }: { result: Result }) {
  const sectionRef = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0);
  const [layers, setLayers] = useState<Layer[] | null>(null);
  const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  const pct = (k: "observed" | "inferred" | "invented") => Math.round(100 * (result.pixel_summary?.[k] ?? 0) * 10) / 10;

  useEffect(() => {
    let live = true;
    (async () => {
      const w = Math.min(MAX, result.width); const h = Math.round(result.height * (w / result.width));
      let damage: HTMLCanvasElement | null = null, rebuilt: HTMLCanvasElement | null = null, invented: HTMLCanvasElement | null = null;
      try {
        if (result.files.mask) {
          const m = await loadImg(fileUrl(result.key, result.files.mask));
          damage = tint(m, w, h, (r) => r > 127, [217, 164, 65, 235]);
        }
        const map = await loadRegionMap(fileUrl(result.key, result.files.regions));
        const c = document.createElement("canvas"); c.width = map.width; c.height = map.height;
        c.getContext("2d")!.putImageData(new ImageData(new Uint8ClampedArray(map.data), map.width, map.height), 0, 0);
        rebuilt = tint(c, w, h, (_r, _g, b) => b === 1, [44, 90, 160, 235]);
        invented = tint(c, w, h, (_r, _g, b) => b === 2, [179, 38, 30, 245], true);
      } catch { /* layers that fail just stay empty */ }
      if (!live) return;
      const seeds = (result as Result & { seeds?: number }).seeds ?? 8;
      setLayers([
        { key: "scan", title: "The scan, as it arrived", body: "Untouched. Every later layer is measured against these pixels.", src: fileUrl(result.key, result.files.original) },
        { key: "damage", title: "What's lost", body: "The damage mask: proposed by the detector we trained, checked by a person.", canvas: damage },
        { key: "rebuilt", title: `Rebuilt · ${pct("inferred")}%`, body: `Repaired, and all ${seeds} independent attempts agreed.`, canvas: rebuilt },
        { key: "invented", title: `Invented · ${pct("invented")}%`, body: "The attempts disagreed. These pixels are a guess, and we say so.", canvas: invented },
        { key: "restored", title: "The restoration", body: `${pct("observed")}% of it is the original, byte for byte. Signed into the file as a C2PA receipt.`, src: fileUrl(result.key, result.files.restored) },
      ]);
    })();
    return () => { live = false; };
  }, [result]);

  useEffect(() => {
    if (reduce) { setProgress(1); return; }
    const onScroll = () => {
      const el = sectionRef.current; if (!el) return;
      const r = el.getBoundingClientRect();
      const span = r.height - window.innerHeight;
      setProgress(Math.min(1, Math.max(0, -r.top / Math.max(1, span))));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
  }, [reduce]);

  // 0 → 0.35: tilt and separate; 0.35 → 1: walk through the layers one by one.
  const open = Math.min(1, progress / 0.35);
  const ease = open * open * (3 - 2 * open);
  const step = layers ? Math.min(layers.length - 1, Math.floor(Math.max(0, progress - 0.3) / 0.7 * layers.length)) : 0;
  const active = progress < 0.3 ? -1 : step;
  const aspect = result.width / result.height;
  const ghost = fileUrl(result.key, result.files.original);

  return (
    <div ref={sectionRef} style={{ height: reduce ? "auto" : "320vh" }} className="relative">
      <div className={`${reduce ? "" : "sticky top-0"} flex min-h-screen items-center py-6`}>
        <div className="grid w-full items-center gap-10 overflow-hidden rounded-md bg-mat px-6 py-10 text-ground shadow-[0_30px_80px_rgba(31,27,22,0.35)] sm:px-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]"
          style={{ backgroundImage: "radial-gradient(ellipse at 70% 45%, rgba(250,246,236,0.10), transparent 60%)" }}>
          <div>
            <p className="tag !bg-ground/10 !text-ground/80">Take it apart</p>
            <h2 className="mt-5 font-serif text-4xl leading-tight sm:text-5xl">
              One restoration. <span className="text-[#E7B7B1]">Five layers of evidence.</span>
            </h2>
            <p className="mt-4 max-w-[52ch] text-lg text-ground/70">
              A real case from our pipeline, separated into what it's made of. Scroll to take it apart.
            </p>
            <ol className="mt-8 space-y-3">
              {(layers ?? []).map((l, i) => (
                <li key={l.key}
                  className={`flex gap-4 rounded-sm border px-4 py-3 transition-all duration-300 ${
                    active === i ? "border-ground/40 bg-ground/10" : "border-transparent opacity-50"}`}>
                  <span className="font-mono text-sm text-ground/60">{String(i + 1).padStart(2, "0")}</span>
                  <span>
                    <span className="block font-semibold">{l.title}</span>
                    <span className="block text-ground/75">{l.body}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <div className="flex justify-center" style={{ perspective: "1800px" }} aria-hidden>
            <div className="relative"
              style={{
                width: "min(78vw, 440px)", aspectRatio: String(aspect), transformStyle: "preserve-3d",
                transform: `rotateX(${ease * 56}deg) rotateZ(${ease * -32}deg) translateY(${ease * -6}%)`,
                transition: reduce ? undefined : "transform 80ms linear",
              }}>
              {(layers ?? []).map((l, i) => {
                const z = (i - 2) * ease * 95;
                const dim = active >= 0 && active !== i;
                return (
                  <div key={l.key} className="absolute inset-0"
                    style={{ transform: `translateZ(${z}px)`, transformStyle: "preserve-3d",
                      transition: "opacity 300ms, transform 80ms linear", opacity: dim ? 0.35 : 1 }}>
                    <div className={`absolute inset-0 overflow-hidden ${l.src ? "" : "border border-ground/25"}`}
                      style={{ background: l.src ? undefined : `rgba(250,246,236,${0.04 + 0.06 * ease})`,
                        boxShadow: ease > 0.05 ? "0 24px 60px rgba(0,0,0,0.45)" : undefined }}>
                      {l.src && <img src={l.src} alt="" crossOrigin="anonymous" className="h-full w-full object-cover" draggable={false} />}
                      {!l.src && ghost && (
                        <img src={ghost} alt="" crossOrigin="anonymous" draggable={false}
                          className="absolute inset-0 h-full w-full object-cover opacity-[0.16] grayscale" />
                      )}
                      {l.canvas && (
                        <div className="absolute inset-0" style={{ filter: "drop-shadow(0 0 6px rgba(255,255,255,0.35))" }}>
                          <CanvasLayer canvas={l.canvas} />
                        </div>
                      )}
                    </div>
                    {ease > 0.6 && (
                      <span className="tag absolute -right-3 top-2 translate-x-full whitespace-nowrap !bg-ground/15 !text-ground"
                        style={{ opacity: (ease - 0.6) / 0.4 }}>
                        {String(i + 1).padStart(2, "0")} · {l.key}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function CanvasLayer({ canvas }: { canvas: HTMLCanvasElement }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = ref.current; if (!host) return;
    canvas.style.width = "100%"; canvas.style.height = "100%"; canvas.style.display = "block";
    host.appendChild(canvas);
    return () => { if (canvas.parentNode === host) host.removeChild(canvas); };
  }, [canvas]);
  return <div ref={ref} className="h-full w-full" />;
}
