import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ErrorNote, PhotoSkeleton } from "./Feedback";

interface Props {
  imageUrl: string;
  initialMaskUrl?: string | null;
  title: string;
  onCancel: () => void;
  onSubmit: (mask: Blob) => void;
  submitting?: boolean;
}

const PAINT = "rgb(179 38 30)";
const MAX_UNDO = 20;

/** Paint (or erase) the damaged areas. Exports a PNG at the photo's full size,
 * white = damaged, black = original. The API logs it as a human-edited mask. */
export function MaskBrush({ imageUrl, initialMaskUrl, title, onCancel, onSubmit, submitting }: Props) {
  const frameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const undoRef = useRef<ImageData[]>([]);
  const lastRef = useRef<{ x: number; y: number } | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [display, setDisplay] = useState({ w: 0, h: 0 });
  const [erase, setErase] = useState(false);
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
          setPainted(true);
        }
      })
      .catch(() => !cancelled && setLoadError("The photo or its damage mask didn't load."));
    return () => {
      cancelled = true;
    };
  }, [imageUrl, initialMaskUrl, attempt]);

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

  const onDown = (e: React.PointerEvent) => {
    if (!natural) return;
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
    if (!lastRef.current || !natural) return;
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
      } else if (e.key === "e") setErase((v) => !v);
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
              className="absolute inset-0 h-full w-full cursor-none opacity-60"
              style={{ touchAction: "none" }}
              onPointerDown={onDown}
              onPointerMove={onMove}
              onPointerUp={onUp}
              onPointerCancel={onUp}
              onPointerLeave={() => setCursor(null)}
            />
            {cursor && (
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
        </div>

        <aside className="space-y-6">
          <div className="grid grid-cols-2 overflow-hidden rounded-sm border border-line" role="radiogroup" aria-label="Brush mode">
            {[
              [false, "Paint"],
              [true, "Erase"],
            ].map(([isErase, label]) => (
              <button
                key={String(label)}
                role="radio"
                aria-checked={erase === isErase}
                onClick={() => setErase(isErase as boolean)}
                className={`py-2 font-semibold not-last:border-r not-last:border-line ${
                  erase === isErase ? "bg-ink text-ground" : "bg-surface hover:bg-tag"
                }`}
              >
                {label as string}
              </button>
            ))}
          </div>
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
          <p className="text-sm text-muted">Keys: E switches paint and erase, [ and ] change the size, Ctrl or ⌘ Z undoes.</p>
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
