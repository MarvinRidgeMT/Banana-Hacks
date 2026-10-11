import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { fileUrl } from "../lib/api";
import { CLASS_LABEL, kindLabel } from "../lib/format";
import { drawOverlay, loadRegionMap, sampleAt, type RegionMap } from "../lib/regionMap";
import type { HoverInfo, Region, Result } from "../lib/types";

interface Props {
  result: Result;
  showMap: boolean;
  opacity: number;
  onHover: (h: HoverInfo | null) => void;
  busy?: string | null;
}

/** Before/after slider with the Invention Map over the restored side. */
export function PhotoStage({ result, showMap, opacity, onHover, busy }: Props) {
  const frameRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mapRef = useRef<RegionMap | null>(null);
  const draggingRef = useRef(false);

  const [size, setSize] = useState({ w: 0, h: 0 });
  const [pos, setPos] = useState(50);
  const [mapError, setMapError] = useState<string | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number; info: HoverInfo } | null>(null);

  const regionsById = useMemo(() => {
    const m = new Map<number, Region>();
    result.regions.forEach((r) => m.set(r.id, r));
    return m;
  }, [result.regions]);

  // Fit the photo into the available width and ~72% of the screen height.
  useLayoutEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const fit = () => {
      const maxW = el.clientWidth;
      const maxH = Math.max(320, window.innerHeight * 0.72);
      const scale = Math.min(maxW / result.width, maxH / result.height);
      setSize({ w: Math.round(result.width * scale), h: Math.round(result.height * scale) });
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    window.addEventListener("resize", fit);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", fit);
    };
  }, [result.width, result.height]);

  // Load the region/class map once per result and paint the overlay from it.
  useEffect(() => {
    let cancelled = false;
    setMapError(null);
    loadRegionMap(fileUrl(result.key, result.files.regions))
      .then((map) => {
        if (cancelled) return;
        mapRef.current = map;
        if (canvasRef.current) drawOverlay(map, canvasRef.current);
      })
      .catch(() => !cancelled && setMapError("The pixel labels didn't load. Reload the page to try again."));
    return () => {
      cancelled = true;
    };
  }, [result.key, result.files.regions]);

  const setFromClientX = (clientX: number) => {
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPos(Math.min(100, Math.max(0, ((clientX - rect.left) / rect.width) * 100)));
  };

  const handleMove = (e: React.PointerEvent) => {
    if (draggingRef.current) {
      setFromClientX(e.clientX);
      return;
    }
    const rect = stageRef.current?.getBoundingClientRect();
    const map = mapRef.current;
    if (!rect || !map) return;
    const fx = (e.clientX - rect.left) / rect.width;
    const fy = (e.clientY - rect.top) / rect.height;
    if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return;
    const { cls, id } = sampleAt(map, fx * map.width, fy * map.height);
    const info: HoverInfo = {
      x: Math.floor(fx * result.width),
      y: Math.floor(fy * result.height),
      side: fx * 100 < pos ? "original" : "restored",
      cls,
      region: id ? regionsById.get(id) ?? null : null,
    };
    setTip({ x: e.clientX - rect.left, y: e.clientY - rect.top, info });
    onHover(info);
  };

  const clearHover = () => {
    setTip(null);
    onHover(null);
  };

  const onKey = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 10 : 2;
    if (e.key === "ArrowLeft") setPos((p) => Math.max(0, p - step));
    else if (e.key === "ArrowRight") setPos((p) => Math.min(100, p + step));
    else if (e.key === "Home") setPos(0);
    else if (e.key === "End") setPos(100);
    else return;
    e.preventDefault();
  };

  const src = (f: string) => fileUrl(result.key, f);

  return (
    <div ref={frameRef} className="w-full">
      <div
        ref={stageRef}
        className="exhibit-frame relative mx-auto select-none overflow-hidden"
        style={{ width: size.w, height: size.h, touchAction: "none" }}
        onPointerMove={handleMove}
        onPointerLeave={clearHover}
        onPointerUp={() => (draggingRef.current = false)}
      >
        <img
          src={src(result.files.restored)}
          crossOrigin="anonymous"
          alt="Restored photo"
          className="absolute inset-0 h-full w-full"
          draggable={false}
        />
        <canvas
          ref={canvasRef}
          aria-hidden
          className="pointer-events-none absolute inset-0 h-full w-full transition-opacity duration-200"
          style={{ opacity: showMap ? opacity : 0 }}
        />
        <img
          src={src(result.files.original)}
          crossOrigin="anonymous"
          alt="Original damaged scan"
          className="absolute inset-0 h-full w-full"
          style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
          draggable={false}
        />

        <span className="tag pointer-events-none absolute left-3 top-3">Original</span>
        <span className="tag pointer-events-none absolute right-3 top-3">
          Restored{showMap ? " + labels" : ""}
        </span>

        {/* the slider handle */}
        <div
          className="absolute inset-y-0 -ml-[1px] w-[2px] bg-ground"
          style={{ left: `${pos}%` }}
          aria-hidden
        />
        <button
          type="button"
          role="slider"
          aria-label="Compare original and restored"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(pos)}
          onKeyDown={onKey}
          onPointerDown={(e) => {
            draggingRef.current = true;
            (e.target as HTMLElement).setPointerCapture(e.pointerId);
            setTip(null);
          }}
          onPointerMove={(e) => draggingRef.current && setFromClientX(e.clientX)}
          onPointerUp={() => (draggingRef.current = false)}
          className="absolute top-1/2 grid h-12 w-12 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize place-items-center rounded-full border-2 border-ground bg-ink/85 text-lg text-ground"
          style={{ left: `${pos}%` }}
        >
          <span aria-hidden>⇆</span>
        </button>

        {tip && <Tip {...tip} stageW={size.w} showMap={showMap} />}

        {busy && (
          <div className="absolute inset-0 grid place-items-center bg-ground/70 text-center text-lg">
            <p className="max-w-xs px-4">{busy}</p>
          </div>
        )}
      </div>
      {mapError && <p className="mt-4 text-invented">{mapError}</p>}
    </div>
  );
}

function Tip({ x, y, info, stageW, showMap }: { x: number; y: number; info: HoverInfo; stageW: number; showMap: boolean }) {
  const flip = x > stageW - 230;
  const body =
    info.side === "original" ? (
      <span>Original scan</span>
    ) : (
      <>
        <span className="flex items-center gap-2 font-semibold">
          <Swatch cls={info.cls} />
          {CLASS_LABEL[info.cls]}
        </span>
        {info.region && (
          <span className="block text-sm text-muted">
            {kindLabel(info.region.kind)}, {Math.round(info.region.confidence * 100)}% confident
          </span>
        )}
      </>
    );
  if (info.side === "restored" && !showMap && info.cls === "observed") return null;
  return (
    <div
      className="pointer-events-none absolute z-10 rounded-sm border border-line bg-ground/95 px-3 py-2 text-base shadow-lg"
      style={{ left: flip ? x - 16 : x + 16, top: y + 16, transform: flip ? "translateX(-100%)" : undefined }}
    >
      {body}
    </div>
  );
}

export function Swatch({ cls, className = "h-4 w-4" }: { cls: HoverInfo["cls"]; className?: string }) {
  const style =
    cls === "observed" ? "bg-observed" : cls === "inferred" ? "bg-inferred" : "hatch-invented";
  return <span aria-hidden className={`inline-block shrink-0 rounded-[2px] ${style} ${className}`} />;
}
