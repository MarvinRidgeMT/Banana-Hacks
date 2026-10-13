import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ErrorNote, PhotoSkeleton } from "./Feedback";
import { buildGrid, smartSelect, type Grid } from "../lib/smartSelect";

interface Props {
  imageUrl: string;
  initialMaskUrl?: string | null;
  /** The detectors' confidence map, for click-to-fix. */
  probUrl?: string | null;
  title: string;
  onCancel: () => void;
  onSubmit: (mask: Blob) => void;
  submitting?: boolean;
}

const PAINT = "rgb(179 38 30)";
const MAX_UNDO = 20;

/** Paint (or erase) the damaged areas. Exports a PNG at the photo's full size,
 * white = damaged, black = original. The API logs it as a human-edited mask. */
type Tool = "paint" | "erase" | "fix";

/** Detection levels, measured on 20 real damaged photos the model never saw (training/recall_mode.py):
 * Standard finds 68% of the damage, More 83% (mask about 2x the true damage area), Most 90% (about 3.5x). */
const LEVELS = [
  { id: "standard", label: "Standard", note: "Finds about 2 in 3 damaged pixels. Tightest mask.", t: 0, d: 0 },
  { id: "more", label: "More", note: "Finds about 83% of the damage; the mask is about twice the real damage.", t: 0.03, d: 4 },
  { id: "most", label: "Most", note: "Finds about 90% of the damage; the mask is about 3.5x the real damage, so more of the photo is regenerated. Erase what isn't damaged.", t: 0.03, d: 12 },
] as const;

export function MaskBrush({ imageUrl, initialMaskUrl, probUrl, title, onCancel, onSubmit, submitting }: Props) {
  const frameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const undoRef = useRef<ImageData[]>([]);
  const lastRef = useRef<{ x: number; y: number } | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [display, setDisplay] = useState({ w: 0, h: 0 });
  const [tool, setTool] = useState<Tool>(probUrl ? "fix" : "paint");
  const erase = tool === "erase";
  const gridRef = useRef<Grid | null>(null);
  const initialRef = useRef<ImageData | null>(null);
  const [level, setLevel] = useState<(typeof LEVELS)[number]["id"]>("standard");
  const [flash, setFlash] = useState<string | null>(null);
  const [size, setSize] = useState(24); // brush diameter in screen pixels
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const [undoCount, setUndoCount] = useState(0);
  const [painted, setPainted] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [note, setNote] = useState<string | null>(null);

  // Reads back pixels for undo and export, so ask for a readback-friendly context.
  const ctx2d = () => canvasRef.current!.getContext("2d", { willReadFrequently: true })!;

  // Load the photo (for its size) and any existing mask.
  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = imageUrl;
    img
      .decode()
      .then(async () => {
        if (cancelled) return;
        const w = img.naturalWidth;
        const h = img.naturalHeight;
        setNatural({ w, h });
        buildGrid(img, probUrl).then((g) => {
          if (!cancelled) gridRef.current = g;
        });
        const canvas = canvasRef.current!;
        canvas.width = w;
        canvas.height = h;
        if (initialMaskUrl) {
          const m = new Image();
          m.crossOrigin = "anonymous";
          m.src = initialMaskUrl;
          await m.decode();
          if (cancelled) return;
          const tmp = document.createElement("canvas");
          tmp.width = w;
          tmp.height = h;
          const tctx = tmp.getContext("2d", { willReadFrequently: true })!;
          tctx.drawImage(m, 0, 0, w, h);
          const src = tctx.getImageData(0, 0, w, h);
          const ctx = ctx2d();
          const out = ctx.createImageData(w, h);
          for (let i = 0; i < src.data.length; i += 4) {
            if (src.data[i] > 127) {
              out.data[i] = 179;
              out.data[i + 1] = 38;
              out.data[i + 2] = 30;
              out.data[i + 3] = 255;
            }
          }
          ctx.putImageData(out, 0, 0);
          initialRef.current = out;
          setPainted(true);
        }
      })
      .catch(() => !cancelled && setLoadError("The photo or its damage mask didn't load."));
    return () => {
      cancelled = true;
    };
  }, [imageUrl, initialMaskUrl, probUrl, attempt]);

  useLayoutEffect(() => {
    const el = frameRef.current;
    if (!el || !natural) return;
    const fit = () => {
      const scale = Math.min(el.clientWidth / natural.w, (window.innerHeight * 0.7) / natural.h);
      setDisplay({ w: Math.round(natural.w * scale), h: Math.round(natural.h * scale) });
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [natural]);

  const toNatural = (e: React.PointerEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const k = natural!.w / rect.width;
    return { x: (e.clientX - rect.left) * k, y: (e.clientY - rect.top) * k, k };
  };

  const stroke = (from: { x: number; y: number }, to: { x: number; y: number }, k: number) => {
    const ctx = ctx2d();
    ctx.globalCompositeOperation = erase ? "destination-out" : "source-over";
    ctx.strokeStyle = PAINT;
    ctx.fillStyle = PAINT;
    ctx.lineWidth = size * k;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(to.x, to.y, (size * k) / 2, 0, Math.PI * 2);
    ctx.fill();
  };

  const applyLevel = (id: (typeof LEVELS)[number]["id"]) => {
    const g = gridRef.current;
    if (!natural) return;
    const L = LEVELS.find((l) => l.id === id)!;
    const ctx = ctx2d();
    undoRef.current.push(ctx.getImageData(0, 0, natural.w, natural.h));
    if (undoRef.current.length > MAX_UNDO) undoRef.current.shift();
    setUndoCount(undoRef.current.length);
    setLevel(id);
    if (L.id === "standard" || !g?.prob) {
      ctx.clearRect(0, 0, natural.w, natural.h);
      if (initialRef.current) ctx.putImageData(initialRef.current, 0, 0);
      setFlash(L.id === "standard" ? "Back to the detectors' standard mask." : "No confidence map for this photo; showing the standard mask.");
      return;
    }
    // threshold the detectors' confidence map, then widen by d px (in the 1024-px grid)
    const { w, h, prob } = g;
    let m = new Uint8Array(w * h);
    for (let i = 0; i < m.length; i++) m[i] = prob[i] >= L.t ? 1 : 0;
    for (let it = 0; it < L.d; it++) {
      const o = new Uint8Array(m);
      for (let y = 0; y < h; y++)
        for (let x = 0; x < w; x++) {
          if (m[y * w + x]) continue;
          const yes =
            (x > 0 && m[y * w + x - 1]) || (x < w - 1 && m[y * w + x + 1]) || (y > 0 && m[(y - 1) * w + x]) || (y < h - 1 && m[(y + 1) * w + x]);
          if (yes) o[y * w + x] = 1;
        }
      m = o;
    }
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    const cx = c.getContext("2d")!;
    const id2 = cx.createImageData(w, h);
    for (let i = 0; i < m.length; i++)
      if (m[i]) {
        id2.data[i * 4] = 179;
        id2.data[i * 4 + 1] = 38;
        id2.data[i * 4 + 2] = 30;
        id2.data[i * 4 + 3] = 255;
      }
    cx.putImageData(id2, 0, 0);
    ctx.clearRect(0, 0, natural.w, natural.h);
    if (initialRef.current) ctx.putImageData(initialRef.current, 0, 0); // never drop what the standard mask had
    ctx.globalCompositeOperation = "source-over";
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(c, 0, 0, natural.w, natural.h);
    setPainted(true);
    setFlash(`${L.label}: ${L.note}`);
  };

  const fixAt = (e: React.PointerEvent) => {
    const g = gridRef.current;
    if (!g || !natural) {
      setFlash("Still loading; try again in a second.");
      return;
    }
    const p = toNatural(e);
    const k = g.w / natural.w;
    const sel = smartSelect(g, p.x * k, p.y * k, Math.max(4, Math.round(10 * k * p.k)));
    const ctx = ctx2d();
    undoRef.current.push(ctx.getImageData(0, 0, natural.w, natural.h));
    if (undoRef.current.length > MAX_UNDO) undoRef.current.shift();
    setUndoCount(undoRef.current.length);
    const c = document.createElement("canvas");
    c.width = sel.w;
    c.height = sel.h;
    const cx = c.getContext("2d")!;
    const id = cx.createImageData(sel.w, sel.h);
    for (let i = 0; i < sel.pixels.length; i++)
      if (sel.pixels[i]) {
        id.data[i * 4] = 179;
        id.data[i * 4 + 1] = 38;
        id.data[i * 4 + 2] = 30;
        id.data[i * 4 + 3] = 255;
      }
    cx.putImageData(id, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(c, 0, 0, natural.w, natural.h);
    setPainted(true);
    setFlash(
      sel.method === "detector"
        ? "Added the damaged area the detectors found there. Undo (⌘Z) if it took too much."
        : sel.method === "contrast"
          ? "Added the spot that stands out from its surroundings. Undo (⌘Z) if it took too much."
          : "Nothing there stands out, so only the spot you clicked was added. Paint the rest by hand.",
    );
  };

  const onDown = (e: React.PointerEvent) => {
    if (!natural) return;
    if (tool === "fix") {
      fixAt(e);
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    const ctx = ctx2d();
    undoRef.current.push(ctx.getImageData(0, 0, natural.w, natural.h));
    if (undoRef.current.length > MAX_UNDO) undoRef.current.shift();
    setUndoCount(undoRef.current.length);
    const p = toNatural(e);
    lastRef.current = p;
    stroke(p, p, p.k);
    setPainted(true);
  };

  const onMove = (e: React.PointerEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    setCursor({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    if (!lastRef.current || !natural || tool === "fix") return;
    const events = "getCoalescedEvents" in e.nativeEvent ? e.nativeEvent.getCoalescedEvents() : [];
    const points = events.length ? events : [e.nativeEvent];
    for (const ev of points) {
      const k = natural.w / rect.width;
      const p = { x: (ev.clientX - rect.left) * k, y: (ev.clientY - rect.top) * k };
      stroke(lastRef.current, p, k);
      lastRef.current = p;
    }
  };

  const onUp = () => {
    lastRef.current = null;
  };

  const undo = useCallback(() => {
    const snap = undoRef.current.pop();
    if (snap) ctx2d().putImageData(snap, 0, 0);
    setUndoCount(undoRef.current.length);
  }, []);

  const clear = () => {
    if (!natural) return;
    const ctx = ctx2d();
    undoRef.current.push(ctx.getImageData(0, 0, natural.w, natural.h));
    setUndoCount(undoRef.current.length);
    ctx.clearRect(0, 0, natural.w, natural.h);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "z") {
        e.preventDefault();
        undo();
      } else if (e.key === "e") setTool((t) => (t === "erase" ? "paint" : "erase"));
      else if (e.key === "f") setTool("fix");
      else if (e.key === "[") setSize((s) => Math.max(4, s - 4));
      else if (e.key === "]") setSize((s) => Math.min(120, s + 4));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo]);

  const exportMask = () => {
    if (!natural) return;
    const src = ctx2d().getImageData(0, 0, natural.w, natural.h);
    const out = document.createElement("canvas");
    out.width = natural.w;
    out.height = natural.h;
    const octx = out.getContext("2d")!;
    const img = octx.createImageData(natural.w, natural.h);
    let any = false;
    for (let i = 0; i < src.data.length; i += 4) {
      const v = src.data[i + 3] > 127 ? 255 : 0;
      if (v) any = true;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
    if (!any) {
      setNote("Paint at least one damaged area first.");
      return;
    }
    setNote(null);
    octx.putImageData(img, 0, 0);
    out.toBlob((b) => b && onSubmit(b), "image/png");
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <button onClick={onCancel} className="text-muted underline-offset-4 hover:underline">
            ← Cancel
          </button>
          <h1 className="mt-1 font-serif text-4xl break-words">Mark the damage on {title}</h1>
          <p className="mt-2 max-w-[60ch] text-muted">
            Paint over every spot where the original picture is gone: tears, missing emulsion, deep
            scratches. Leave fading and stains unpainted; only lost content counts. The manifest will
            record that a person drew this mask.
          </p>
        </div>
      </div>

      <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div ref={frameRef} className="w-full">
          {!natural && !loadError && <PhotoSkeleton>Loading the photo…</PhotoSkeleton>}
          <div
            className={`exhibit-frame relative ${natural ? "" : "hidden"}`}
            style={{ width: display.w, height: display.h }}
          >
            <img
              src={imageUrl}
              crossOrigin="anonymous"
              alt="Photo to mark"
              className="absolute inset-0 h-full w-full"
              draggable={false}
            />
            <canvas
              ref={canvasRef}
              className={`absolute inset-0 h-full w-full opacity-60 ${tool === "fix" ? "cursor-crosshair" : "cursor-none"}`}
              style={{ touchAction: "none" }}
              onPointerDown={onDown}
              onPointerMove={onMove}
              onPointerUp={onUp}
              onPointerCancel={onUp}
              onPointerLeave={() => setCursor(null)}
            />
            {cursor && tool !== "fix" && (
              <div
                aria-hidden
                className="pointer-events-none absolute rounded-full border-2 border-ground shadow-[0_0_0_1px_var(--color-ink)]"
                style={{
                  width: size,
                  height: size,
                  left: cursor.x - size / 2,
                  top: cursor.y - size / 2,
                  borderStyle: erase ? "dashed" : "solid",
                }}
              />
            )}
          </div>
          {loadError && (
            <ErrorNote message={loadError} onRetry={() => setAttempt((a) => a + 1)} className={natural ? "mt-6" : ""} />
          )}
          {note && <p className="mt-4 text-invented">{note}</p>}
          {flash && (
            <p className="mt-4 text-body" role="status">
              {flash}
            </p>
          )}
        </div>

        <aside className="space-y-6">
          {probUrl && (
            <div>
              <p className="text-sm font-semibold">How much damage to catch</p>
              <div className="mt-2 grid grid-cols-3 overflow-hidden rounded-sm border border-line" role="radiogroup" aria-label="Detection level">
                {LEVELS.map((l) => (
                  <button
                    key={l.id}
                    role="radio"
                    aria-checked={level === l.id}
                    onClick={() => applyLevel(l.id)}
                    className={`py-2 text-sm font-semibold not-last:border-r not-last:border-line ${
                      level === l.id ? "bg-ink text-ground" : "bg-surface hover:bg-tag"
                    }`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-sm text-muted">{LEVELS.find((l) => l.id === level)!.note}</p>
            </div>
          )}
          <div className="grid grid-cols-3 overflow-hidden rounded-sm border border-line" role="radiogroup" aria-label="Brush mode">
            {(
              [
                ["fix", "Click to fix"],
                ["paint", "Paint"],
                ["erase", "Erase"],
              ] as const
            ).map(([t, label]) => (
              <button
                key={t}
                role="radio"
                aria-checked={tool === t}
                onClick={() => setTool(t)}
                className={`py-2 text-sm font-semibold not-last:border-r not-last:border-line ${
                  tool === t ? "bg-ink text-ground" : "bg-surface hover:bg-tag"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {tool === "fix" && (
            <p className="text-sm text-body">
              Click a crack, scratch or flake the mask missed: the whole thing is selected, not just where you
              clicked.
            </p>
          )}
          <label className="block">
            <span className="text-sm text-muted">Brush size</span>
            <input
              type="range"
              min={4}
              max={120}
              value={size}
              onChange={(e) => setSize(Number(e.target.value))}
              className="block w-full"
            />
          </label>
          <div className="flex gap-3">
            <button
              onClick={undo}
              disabled={undoCount === 0}
              className="rounded-sm border border-line px-4 py-2 hover:bg-tag disabled:opacity-40"
            >
              Undo
            </button>
            <button onClick={clear} className="rounded-sm border border-line px-4 py-2 hover:bg-tag">
              Clear
            </button>
          </div>
          <p className="text-sm text-muted">
            Keys: F click to fix, E switches paint and erase, [ and ] change the size, Ctrl or ⌘ Z undoes.
          </p>
          <button
            onClick={exportMask}
            disabled={!painted || submitting}
            className="w-full rounded-sm bg-ink px-4 py-3 text-lg font-semibold text-ground hover:bg-ink/90 disabled:opacity-40"
          >
            {submitting ? "Sending…" : "Restore with this mask"}
          </button>
        </aside>
      </div>
    </div>
  );
}
