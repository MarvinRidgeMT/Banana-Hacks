import { useEffect, useMemo, useState } from "react";
import { apiMode, fileUrl } from "../lib/api";
import { href } from "../lib/router";
import type { Demo } from "../lib/types";
import { CompareSlider } from "./CompareSlider";
import { Link } from "./Link";

interface Measured {
  demo: Demo;
  pct: number;
  deltaE: number;
  faces: number;
}

const DIR = "f070";

/** The headline measurement: how much of the UNDAMAGED photo each approach changes.
 * Numbers are read from each demo's compare.json, made by backend/archive_demos.py. */
export function ProofSection({ demos }: { demos: Demo[] | null }) {
  const [rows, setRows] = useState<Measured[] | null>(null);
  const [pick, setPick] = useState<string | null>(null);
  const [overlay, setOverlay] = useState(true);

  useEffect(() => {
    if (!demos) return;
    let live = true;
    const photos = demos.filter((d) => d.kind !== "document");
    void apiMode().then(() =>
      Promise.all(
        photos.map(async (d) => {
          try {
            const r = await fetch(fileUrl(d.key, `${DIR}/compare/compare.json`));
            if (!r.ok) return null;
            const c = await r.json();
            return { demo: d, pct: c.undamaged_changed_pct, deltaE: c.mean_delta_e_undamaged, faces: c.faces_restored } as Measured;
          } catch {
            return null;
          }
        }),
      ).then((all) => {
        if (!live) return;
        const ok = all.filter((x): x is Measured => !!x && typeof x.pct === "number").sort((a, b) => b.pct - a.pct);
        setRows(ok);
        setPick((p) => p ?? (ok.find((x) => x.demo.id === "backup") ?? ok[0])?.demo.key ?? null);
      }),
    );
    return () => {
      live = false;
    };
  }, [demos]);

  const current = useMemo(() => rows?.find((r) => r.demo.key === pick) ?? null, [rows, pick]);
  if (!rows || rows.length === 0 || !current) return null;
  const lo = Math.min(...rows.map((r) => r.pct));
  const hi = Math.max(...rows.map((r) => r.pct));

  return (
    <section data-tour="proof" id="proof" aria-labelledby="proof-h" className="bleed proof-section scroll-mt-20">
      <div className="mx-auto grid max-w-[110rem] gap-14 px-6 py-24 [&>*]:min-w-0 sm:px-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center">
        <div>
          <p className="eyebrow flex items-center gap-3 text-muted">
            <span className="hud-tick" aria-hidden /> The measurement
          </p>
          <h2 id="proof-h" className="display mt-6 text-[clamp(2.6rem,5vw,5rem)] text-ink">
            They repaint the whole photo. We don't.
          </h2>
          <p className="mt-6 max-w-[48ch] text-lg leading-relaxed text-body">
            Share of the <em>undamaged</em> photo that gets changed, on our {rows.length} demo photos:
          </p>
          <div className="mt-8 grid grid-cols-2 gap-4">
            <div className="proof-stat proof-them">
              <p className="readout text-[0.68rem] text-muted">A typical restorer</p>
              <p className="mt-3 whitespace-nowrap font-serif text-[clamp(2rem,4vw,3.6rem)] leading-none text-invented">
                {Math.round(lo)}–{Math.round(hi)}%
              </p>
            </div>
            <div className="proof-stat proof-us">
              <p className="readout text-[0.68rem] text-muted">Cold Case</p>
              <p className="mt-3 font-serif text-[clamp(2rem,4vw,3.6rem)] leading-none text-ink">0%</p>
            </div>
          </div>
          <ul className="mt-8 space-y-2" aria-label="Per photo">
            {rows.map((r) => (
              <li key={r.demo.key}>
                <button
                  type="button"
                  onClick={() => setPick(r.demo.key)}
                  aria-pressed={r.demo.key === pick}
                  className="proof-row group w-full text-left"
                >
                  <span className="truncate text-sm text-body">{r.demo.title.replace(/^Document: (.)/, (_, c) => c.toUpperCase())}</span>
                  <span className="proof-bar" aria-hidden>
                    <span style={{ width: `${r.pct}%` }} />
                  </span>
                  <span className="readout w-28 shrink-0 text-right text-xs text-muted">
                    {r.pct.toFixed(1)}% <span className="text-faint">vs 0</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-6 text-sm text-muted">
            &ldquo;Typical restorer&rdquo; is a representative recipe, not a named product: denoise and sharpen the
            whole frame, fill the damage, and run a face restorer on every face. Cold Case copies every undamaged
            pixel byte for byte.{" "}
            <Link to={href.evidence} className="underline underline-offset-4 hover:text-ink">
              How we measured
            </Link>
          </p>
        </div>

        <div>
          <div className="proof-frame mx-auto w-fit max-w-full">
            <CompareSlider
              key={current.demo.key}
              left={fileUrl(current.demo.key, `${DIR}/compare/typical.png`)}
              right={fileUrl(current.demo.key, `${DIR}/restored.png`)}
              overlay={fileUrl(current.demo.key, `${DIR}/compare/changed.png`)}
              showOverlay={overlay}
              leftLabel="Typical restorer"
              rightLabel="Cold Case"
              alt={`${current.demo.title}, restored by Cold Case`}
              initial={55}
            />
          </div>
          <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
            <label className="flex cursor-pointer items-center gap-3 text-body">
              <input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} className="h-5 w-5 accent-[#e5483d]" />
              Show what the typical restorer changed
            </label>
            <p className="flex items-center gap-4 text-sm text-muted">
              <span className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-sm bg-invented" /> changed, but wasn't damaged
              </span>
              <span className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-sm bg-inferred" /> damage
              </span>
            </p>
          </div>
          <p className="mt-3 text-sm text-muted">
            {current.demo.title.replace(/^Document: (.)/, (_, c) => c.toUpperCase())}: the typical restorer changed {current.pct.toFixed(1)}% of
            the undamaged pixels (average color shift ΔE {current.deltaE.toFixed(1)}). Drag to compare.
          </p>
        </div>
      </div>
    </section>
  );
}
