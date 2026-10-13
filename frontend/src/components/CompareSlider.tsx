import { useState } from "react";

interface Props {
  left: string;
  right: string;
  leftLabel: string;
  rightLabel: string;
  /** Drawn over the left image when `showOverlay` is on. */
  overlay?: string | null;
  showOverlay?: boolean;
  alt: string;
  initial?: number;
}

/** Drag (or arrow-key) between two images of the same size. */
export function CompareSlider({ left, right, leftLabel, rightLabel, overlay, showOverlay, alt, initial = 50 }: Props) {
  const [pos, setPos] = useState(initial);
  return (
    <div className="cmp-slider relative mx-auto w-fit max-w-full select-none overflow-hidden">
      <img src={right} alt={alt} crossOrigin="anonymous" className="block max-h-[72vh] w-auto max-w-full" draggable={false} />
      <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
        <img src={left} alt="" crossOrigin="anonymous" className="block h-full w-full" draggable={false} />
        {overlay && (
          <img
            src={overlay}
            alt=""
            crossOrigin="anonymous"
            className={`absolute inset-0 h-full w-full transition-opacity duration-500 ${showOverlay ? "opacity-75" : "opacity-0"}`}
            draggable={false}
          />
        )}
      </div>
      <div className="cmp-line" style={{ left: `${pos}%` }} aria-hidden>
        <span className="cmp-knob">⟷</span>
      </div>
      <span className="cmp-tag left-3">{leftLabel}</span>
      <span className="cmp-tag right-3">{rightLabel}</span>
      <input
        type="range"
        min={0}
        max={100}
        step={0.5}
        value={pos}
        onChange={(e) => setPos(Number(e.target.value))}
        aria-label={`Compare ${leftLabel} and ${rightLabel}`}
        className="cmp-range"
      />
    </div>
  );
}
