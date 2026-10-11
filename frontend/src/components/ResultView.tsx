import { useCallback, useEffect, useRef, useState } from "react";
import { api, waitForJob } from "../lib/api";
import { fidelityLabel, seconds } from "../lib/format";
import type { HoverInfo, Job, Metrics, Result } from "../lib/types";
import { FIDELITY_STEPS } from "../lib/types";
import { EvidenceNotes } from "./EvidenceNotes";
import { FacesPanel } from "./FacesPanel";
import { FidelityControl } from "./FidelityControl";
import { ManifestPanel } from "./ManifestPanel";
import { MapLegend } from "./MapLegend";
import { PhotoStage } from "./PhotoStage";
import { RegionReadout } from "./RegionReadout";

interface Props {
  photoKey: string;
  title: string;
  initialFidelity: number;
  metrics: Metrics | null;
  onFixMask: (r: Result) => void;
  onFidelity: (f: number) => void;
  onBack: () => void;
}

function jobMessage(j: Job, f: number) {
  const what = `Preparing ${fidelityLabel(f).toLowerCase()} (w = ${f.toFixed(1)})`;
  if (j.status === "queued") return `${what}. Waiting in line${j.position ? `, position ${j.position}` : ""}.`;
  if (j.status === "running") return `${what}. Restoring now, ${seconds(j.elapsed)} so far.`;
  return what;
}

export function ResultView({ photoKey, title, initialFidelity, metrics, onFixMask, onFidelity, onBack }: Props) {
  const [fidelity, setFidelity] = useState(initialFidelity);
  const [results, setResults] = useState<Record<string, Result>>({});
  const [shown, setShown] = useState<Result | null>(null);
  const [busy, setBusy] = useState<string | null>("Loading…");
  const [error, setError] = useState<string | null>(null);
  const [showMap, setShowMap] = useState(true);
  const [opacity, setOpacity] = useState(0.75);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [tab, setTab] = useState<"faces" | "manifest">("faces");
  const abortRef = useRef<AbortController | null>(null);

  const store = useCallback((r: Result) => {
    setResults((prev) => ({ ...prev, [String(r.fidelity)]: r }));
  }, []);

  // Show the requested fidelity: from memory, the cache, or a new job.
  useEffect(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const have = results[String(fidelity)];
    if (have) {
      setShown(have);
      setBusy(null);
      return;
    }
    setError(null);
    setBusy(`Preparing ${fidelityLabel(fidelity).toLowerCase()}…`);
    (async () => {
      try {
        let r = await api.result(photoKey, fidelity);
        if (!r) {
          const job = await api.restore({ key: photoKey, fidelity });
          const done = await waitForJob(job, (j) => setBusy(jobMessage(j, fidelity)), ctrl.signal);
          if (done.status === "error") throw new Error(done.error ?? "The restoration failed.");
          r = done.result ?? (await api.result(photoKey, fidelity));
        }
        if (ctrl.signal.aborted || !r) return;
        store(r);
        setShown(r);
        setBusy(null);
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setBusy(null);
        setError((e as Error).message);
      }
    })();
    return () => ctrl.abort();
    // `results` is read but not a dependency: re-running on every store would loop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [photoKey, fidelity, store]);

  // Quietly pick up the other fidelity steps as the queue finishes them.
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      for (const f of FIDELITY_STEPS) {
        if (stop || results[String(f)]) continue;
        try {
          const r = await api.result(photoKey, f);
          if (r && !stop) store(r);
        } catch {
          /* the main view reports connection problems */
        }
      }
    };
    tick();
    const t = setInterval(tick, 3000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [photoKey, results, store]);

  const ready = FIDELITY_STEPS.filter((f) => results[String(f)]);

  if (!shown) {
    return (
      <div className="py-24 text-center text-xl">
        {error ? (
          <>
            <p className="text-invented">{error}</p>
            <button onClick={onBack} className="mt-6 underline">
              Back to photos
            </button>
          </>
        ) : (
          <p>{busy}</p>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <button onClick={onBack} className="text-muted underline-offset-4 hover:underline">
            ← All photos
          </button>
          <p className="case-label mt-4">Case {photoKey.slice(0, 8)} · the evidence</p>
          <h2 className="mt-1 font-serif text-5xl">{title}</h2>
        </div>
        <p className="text-muted">
          Restored in {seconds(shown.seconds)}
          {!shown.fidelity_applied && " (this pipeline ignores the fidelity setting)"}
        </p>
      </div>

      <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <PhotoStage result={shown} showMap={showMap} opacity={opacity} onHover={setHover} busy={busy} />

        <aside className="space-y-8">
          <section className="space-y-4">
            <label className="flex cursor-pointer items-center justify-between gap-4">
              <span className="font-serif text-2xl">Show the evidence</span>
              <input
                type="checkbox"
                role="switch"
                checked={showMap}
                onChange={(e) => setShowMap(e.target.checked)}
                className="h-6 w-11 cursor-pointer appearance-none rounded-full bg-line transition-colors before:mt-0.5 before:block before:h-5 before:w-5 before:translate-x-0.5 before:rounded-full before:bg-surface before:shadow before:transition-transform checked:bg-inferred checked:before:translate-x-5"
              />
            </label>
            <label className={`block ${showMap ? "" : "opacity-40"}`}>
              <span className="text-sm text-muted">Map strength</span>
              <input
                type="range"
                min={0.2}
                max={1}
                step={0.05}
                value={opacity}
                disabled={!showMap}
                onChange={(e) => setOpacity(Number(e.target.value))}
                className="block w-full"
              />
            </label>
            <MapLegend summary={shown.pixel_summary} />
          </section>

          <RegionReadout hover={hover} />

          <FidelityControl
            value={fidelity}
            ready={ready}
            onChange={(f) => {
              setFidelity(f);
              onFidelity(f);
            }}
          />

          <div className="space-y-3">
            <EvidenceNotes metrics={metrics} maskSource={shown.mask_source} />
            <button
              onClick={() => onFixMask(shown)}
              className="rounded-sm border border-line px-4 py-2 hover:bg-tag"
            >
              Correct the damage mask
            </button>
          </div>

          {error && <p className="text-invented">{error}</p>}
          {shown.warnings.length > 0 && (
            <details className="text-sm text-muted">
              <summary className="cursor-pointer">Pipeline notes ({shown.warnings.length})</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {shown.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </details>
          )}
        </aside>
      </div>

      <div className="mt-14">
        <div role="tablist" className="mb-6 flex gap-8 border-b border-line">
          {(
            [
              ["faces", "Three faces"],
              ["manifest", "The receipt"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              role="tab"
              aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={`-mb-px border-b-2 pb-3 font-serif text-2xl ${
                tab === id ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div role="tabpanel">
          {tab === "faces" ? <FacesPanel result={shown} /> : <ManifestPanel result={shown} />}
        </div>
      </div>
    </div>
  );
}
