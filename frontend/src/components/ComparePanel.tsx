import { useEffect, useState } from "react";
import { api, fileUrl } from "../lib/api";
import { failure } from "../lib/format";
import type { CompareResult, Result } from "../lib/types";
import { ErrorNote } from "./Feedback";

/** Side by side: Cold Case vs a typical whole-image "AI enhance" restorer on the same scan. */
export function ComparePanel({ result }: { result: Result }) {
  const [cmp, setCmp] = useState<CompareResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showChanged, setShowChanged] = useState(true);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setCmp(await api.compare(result.key, result.fidelity));
    } catch (e) {
      setError(failure("Couldn't run the comparison", e));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    setCmp(null);
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result.key, result.fidelity]);

  return (
    <section className="space-y-8">
      <div className="max-w-[70ch]">
        <h3 className="font-serif text-3xl">What a typical restorer would have done</h3>
        <p className="mt-3 text-lg text-body">
          Most "AI enhance" restorers process the whole frame: they fill the damage, smooth and sharpen everything,
          and repaint every face. We ran that recipe on the same scan so you can see what it changes that nobody asked
          it to.
        </p>
      </div>
      {error && <ErrorNote message={error} onRetry={run} />}
      {!cmp && !error && <p className="text-muted">{busy ? "Running the typical restorer… (a few seconds)" : ""}</p>}
      {cmp && (
        <>
          <dl className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-sm border border-invented/50 bg-surface p-5">
              <dt className="case-label">Typical restorer</dt>
              <dd className="mt-2 font-serif text-5xl text-invented">{cmp.undamaged_changed_pct}%</dd>
              <dd className="mt-1 text-sm text-body">of undamaged pixels changed</dd>
            </div>
            <div className="rounded-sm border border-inferred/50 bg-surface p-5">
              <dt className="case-label">Cold Case</dt>
              <dd className="mt-2 font-serif text-5xl text-inferred">0%</dd>
              <dd className="mt-1 text-sm text-body">undamaged pixels are copied byte for byte (tested)</dd>
            </div>
            <div className="rounded-sm border border-line bg-surface p-5">
              <dt className="case-label">Average color shift outside the damage</dt>
              <dd className="mt-2 font-serif text-5xl">ΔE {cmp.mean_delta_e_undamaged}</dd>
              <dd className="mt-1 text-sm text-body">
                {cmp.undamaged_changed.toLocaleString("en-US")} of {cmp.undamaged_pixels.toLocaleString("en-US")} pixels
              </dd>
            </div>
          </dl>
          <div className="grid gap-6 md:grid-cols-2">
            <figure>
              <img
                src={fileUrl(result.key, result.files.restored)}
                crossOrigin="anonymous"
                alt="Cold Case restoration"
                className="exhibit-frame w-full object-contain"
              />
              <figcaption className="mt-3 font-semibold">Cold Case: only the damage is repaired, and labeled</figcaption>
            </figure>
            <figure>
              <div className="exhibit-frame relative">
                <img
                  src={fileUrl(result.key, cmp.files.typical)}
                  crossOrigin="anonymous"
                  alt="Typical whole-image restorer"
                  className="block w-full object-contain"
                />
                <img
                  src={fileUrl(result.key, cmp.files.changed)}
                  crossOrigin="anonymous"
                  alt=""
                  aria-hidden
                  className="absolute inset-0 h-full w-full object-contain transition-opacity"
                  style={{ opacity: showChanged ? 0.85 : 0 }}
                />
              </div>
              <figcaption className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <span className="font-semibold">Typical restorer: red = changed although it wasn't damaged</span>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={showChanged} onChange={(e) => setShowChanged(e.target.checked)} />
                  Show changes
                </label>
              </figcaption>
            </figure>
          </div>
          <p className="max-w-[70ch] text-sm text-muted">
            Method: {cmp.method}. This is a representative recipe, not any specific product. Blue in the map is the
            damage both tools fill.
          </p>
        </>
      )}
    </section>
  );
}
