import { useCallback, useEffect, useRef, useState } from "react";
import { api, waitForJob } from "../lib/api";
import { failure, fidelityLabel, seconds } from "../lib/format";
import { href } from "../lib/router";
import type { ColorResult, HoverInfo, Job, Metrics, Result } from "../lib/types";
import { FIDELITY_STEPS } from "../lib/types";
import { ColorPanel } from "./ColorPanel";
import { CopyLink } from "./CopyLink";
import { EvidenceNotes } from "./EvidenceNotes";
import { FacesPanel } from "./FacesPanel";
import { Bone, ErrorNote, LegendSkeleton, PhotoSkeleton } from "./Feedback";
import { FidelityControl } from "./FidelityControl";
import { Link } from "./Link";
import { ManifestPanel } from "./ManifestPanel";
import { MapLegend } from "./MapLegend";
import { PhotoStage } from "./PhotoStage";
import { ReadingHint } from "./ReadingHint";
import { RegionReadout } from "./RegionReadout";

interface Props {
  photoKey: string;
  title: string;
  initialFidelity: number;
  metrics: Metrics | null;
  onFixMask: (r: Result) => void;
  onFidelity: (f: number) => void;
}

function jobMessage(j: Job, f: number) {
  const what = `Preparing ${fidelityLabel(f).toLowerCase()} (w = ${f.toFixed(1)})`;
  if (j.status === "queued") return `${what}. Waiting in line${j.position ? `, position ${j.position}` : ""}.`;
  if (j.status === "running") return `${what}. Restoring now, ${seconds(j.elapsed)} so far.`;
  return what;
}

export function ResultView({ photoKey, title, initialFidelity, metrics, onFixMask, onFidelity }: Props) {
  const [fidelity, setFidelity] = useState(initialFidelity);
  const [results, setResults] = useState<Record<string, Result>>({});
  const [shown, setShown] = useState<Result | null>(null);
  const [busy, setBusy] = useState<string | null>("Loading the case…");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [showMap, setShowMap] = useState(false);
  const [opacity, setOpacity] = useState(0.75);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [tab, setTab] = useState<"faces" | "manifest">("faces");
  const [colors, setColors] = useState<Record<string, ColorResult>>({});
  const [colorOn, setColorOn] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const store = useCallback((r: Result) => {
    setResults((prev) => ({ ...prev, [String(r.fidelity)]: r }));
  }, []);

  const retry = () => {
    setError(null);
    setAttempt((a) => a + 1);
  };

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
        setError(failure(`Couldn't load the ${fidelityLabel(fidelity)} version of this photo`, e));
      }
    })();
    return () => ctrl.abort();
    // `results` is read but not a dependency: re-running on every store would loop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [photoKey, fidelity, store, attempt]);

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

  const header = (
    <div className="mb-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <nav aria-label="Breadcrumb" className="case-label">
          <ol className="flex flex-wrap items-center">
            <li>
              <Link to={href.restore} className="underline-offset-4 hover:text-ink hover:underline">
                Cases
              </Link>
            </li>
            <li>
              <span aria-hidden className="mx-2">
                /
              </span>
              <span aria-current="page" className="text-ink">
                Case {photoKey.slice(0, 8)}
              </span>
            </li>
          </ol>
        </nav>
        <CopyLink />
      </div>
      <div className="mt-4 flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-serif text-4xl sm:text-5xl">{title}</h1>
        {shown ? (
          <p className="text-muted">
            Restored in {seconds(shown.seconds)}
            {!shown.fidelity_applied && " (this pipeline ignores the fidelity setting)"}
          </p>
        ) : (
          !error && <Bone className="h-5 w-40" />
        )}
      </div>
    </div>
  );

  if (!shown) {
    return (
      <div>
        {header}
        {error ? (
          <ErrorNote message={error} onRetry={retry} className="py-12" />
        ) : (
          <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_24rem]">
            <div className="space-y-6">
              <ReadingHint />
              <PhotoSkeleton>{busy}</PhotoSkeleton>
            </div>
            <aside className="space-y-8" aria-hidden>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Bone className="h-7 w-48" />
                  <Bone className="h-6 w-11 rounded-full" />
                </div>
                <Bone className="h-2 w-full" />
                <LegendSkeleton />
              </div>
              <Bone className="h-36 w-full" />
              <div className="space-y-3">
                <Bone className="h-5 w-32" />
                <Bone className="h-16 w-full" />
              </div>
            </aside>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      {header}

      <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="space-y-6">
          {shown.kind === "document" ? (
            <p className="rounded-sm border border-line bg-surface px-5 py-4 text-body">
              <span className="font-semibold">Document mode.</span> No text was generated. Blue areas are paper
              filled in from its surroundings; red areas touched writing, so text was probably lost there and the
              blank fill is not the original.
            </p>
          ) : (
            <ReadingHint />
          )}
          <PhotoStage
            result={shown}
            showMap={showMap}
            opacity={opacity}
            onHover={setHover}
            busy={busy}
            colorFile={colorOn ? colors[`${shown.key}:${shown.fidelity}`]?.files.colorized : null}
            colorMapFile={colorOn ? colors[`${shown.key}:${shown.fidelity}`]?.files.map : null}
          />
        </div>

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

          {shown.kind !== "document" && (
            <ColorPanel
              result={shown}
              color={colors[`${shown.key}:${shown.fidelity}`] ?? null}
              on={colorOn}
              onColor={(c) => c && setColors((prev) => ({ ...prev, [`${shown.key}:${shown.fidelity}`]: c }))}
              onToggle={setColorOn}
            />
          )}

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

          {error && <ErrorNote message={error} onRetry={retry} />}
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
