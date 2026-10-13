import { useEffect, useRef } from "react";
import { fileUrl } from "../lib/api";
import type { Region, Result } from "../lib/types";

/** "Why is this Invented?": the damaged scan and every restoration attempt of one region, side by side.
 * Where the attempts disagree, Cold Case labels the pixels Invented. */
export function AttemptsPanel({
  result,
  region,
  onPick,
  onClose,
}: {
  result: Result;
  region: Region | null;
  onPick: (r: Region) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  const spots = result.regions.filter((r) => r.alternatives).sort((a, b) => b.invented_px - a.invented_px);
  useEffect(() => {
    if (region) ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [region]);
  if (!spots.length) return null;

  const alt = region?.alternatives;
  const n = alt ? alt.seeds.length + 1 : 0;
  const shownIdx = alt && alt.shown_seed != null ? alt.seeds.indexOf(alt.shown_seed) : -1;
  const inventedPct = region ? Math.round((region.invented_px / Math.max(1, region.area_px)) * 100) : 0;

  return (
    <section ref={ref} aria-labelledby="attempts-h" className="rounded-sm border border-line bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="attempts-h" className="font-serif text-2xl">
          Why is this Invented?
        </h2>
        {region && (
          <button type="button" onClick={onClose} className="text-sm text-muted underline underline-offset-4 hover:text-ink">
            Close
          </button>
        )}
      </div>
      <p className="mt-2 max-w-[62ch] text-body">
        Click a red area on the photo, or pick a spot below, to see every restoration attempt of it. Where the
        attempts agree, the pixels are Rebuilt; where they disagree, nobody can know the original, so they
        are Invented.
      </p>
      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Spots with the most invented pixels">
        {spots.map((r, i) => (
          <button
            key={r.id}
            type="button"
            aria-pressed={region?.id === r.id}
            onClick={() => onPick(r)}
            className={`rounded-full border px-3 py-1.5 text-sm transition ${
              region?.id === r.id ? "border-ink bg-ink text-ground" : "border-line hover:bg-tag"
            }`}
          >
            Spot {i + 1} · {Math.round((r.invented_px / Math.max(1, r.area_px)) * 100)}% invented
          </button>
        ))}
      </div>

      {region && alt && (
        <div className="mt-6">
          <p className="text-sm text-muted">
            {inventedPct}% of this spot is Invented. {alt.seeds.length} attempts with different random seeds; the
            one marked "shown" is in the restoration (the most typical one).
          </p>
          <ul className="mt-3 grid grid-cols-3 gap-3 sm:grid-cols-5" aria-label="The damaged scan and every attempt">
            {Array.from({ length: n }, (_, i) => (
              <li key={i} className="min-w-0">
                <div
                  role="img"
                  aria-label={i === 0 ? "The damaged scan" : `Attempt ${i}${i - 1 === shownIdx ? ", shown" : ""}`}
                  className={`w-full bg-mat bg-no-repeat ${i - 1 === shownIdx ? "ring-2 ring-inferred" : ""} ${
                    i === 0 ? "ring-2 ring-invented" : ""
                  }`}
                  style={{
                    aspectRatio: `${alt.tile[0]} / ${alt.tile[1]}`,
                    backgroundImage: `url("${fileUrl(result.key, alt.file)}")`,
                    backgroundSize: `${n * 100}% 100%`,
                    backgroundPosition: `${n > 1 ? (i / (n - 1)) * 100 : 0}% 0`,
                  }}
                />
                <p className="mt-1 truncate text-xs text-muted">
                  {i === 0 ? "Damaged scan" : `Attempt ${i}`}
                  {i - 1 === shownIdx && <span className="ml-1 font-semibold text-inferred">· shown</span>}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
