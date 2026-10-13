import { useEffect, useRef, useState } from "react";

/** Animates the first number in `text` from 0 when it scrolls into view. */
export function CountUp({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(text);
  useEffect(() => {
    const m = text.match(/[\d,]+(\.\d+)?/);
    if (!m || !ref.current) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const target = parseFloat(m[0].replace(/,/g, ""));
    const dec = (m[1] ?? "").length ? m[1]!.length - 1 : 0;
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        io.disconnect();
        const t0 = performance.now();
        const tick = (t: number) => {
          const k = Math.min(1, (t - t0) / 1400);
          const v = target * (1 - Math.pow(1 - k, 3));
          setShown(text.replace(m[0], v.toLocaleString("en-US", { maximumFractionDigits: dec, minimumFractionDigits: dec })));
          if (k < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    io.observe(ref.current);
    return () => io.disconnect();
  }, [text]);
  return <span ref={ref}>{shown}</span>;
}
