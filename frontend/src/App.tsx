import { useCallback, useEffect, useRef, useState } from "react";
import { JobProgress } from "./components/JobProgress";
import { MaskBrush } from "./components/MaskBrush";
import { ResultView } from "./components/ResultView";
import { UploadView } from "./components/UploadView";
import { api, fileUrl, waitForJob } from "./lib/api";
import type { Demo, Job, Metrics, Result } from "./lib/types";
import { DEFAULT_FIDELITY, FIDELITY_STEPS } from "./lib/types";

type Screen =
  | { name: "home" }
  | { name: "brush"; title: string; imageUrl: string; maskUrl?: string | null; file?: File; key?: string }
  | { name: "job"; title: string; job: Job | null }
  | { name: "result"; key: string; title: string; fidelity: number };

/** #/p/<key>/<fidelity> opens a result directly, so a link can go in the Devpost write-up. */
function parseHash(): { key: string; fidelity: number } | null {
  const m = window.location.hash.match(/^#\/p\/([0-9a-f]{64})(?:\/([\d.]+))?$/);
  if (!m) return null;
  const f = Number(m[2]);
  return { key: m[1], fidelity: (FIDELITY_STEPS as readonly number[]).includes(f) ? f : DEFAULT_FIDELITY };
}

export default function App() {
  const [screen, setScreen] = useState<Screen>(() => {
    const h = parseHash();
    return h ? { name: "result", key: h.key, title: "Restored photo", fidelity: h.fidelity } : { name: "home" };
  });
  const [demos, setDemos] = useState<Demo[] | null>(null);
  const [demosError, setDemosError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [pipeline, setPipeline] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const jobAbort = useRef<AbortController | null>(null);
  const objectUrl = useRef<string | null>(null);

  useEffect(() => {
    api.demos().then(setDemos).catch((e) => setDemosError(e.message));
    api.metrics().then(setMetrics).catch(() => setMetrics(null));
    api.health().then((h) => setPipeline(h.pipeline)).catch(() => setPipeline(null));
  }, []);

  // Keep the address bar in step with the result being shown.
  useEffect(() => {
    if (screen.name === "result") {
      const want = `#/p/${screen.key}/${screen.fidelity}`;
      if (window.location.hash !== want) history.replaceState(null, "", want);
    } else if (screen.name === "home" && window.location.hash) {
      history.replaceState(null, "", window.location.pathname);
    }
  }, [screen]);

  // A demo opened from a link gets its real title once the demo list arrives.
  useEffect(() => {
    if (screen.name !== "result" || !demos) return;
    const d = demos.find((x) => x.key === screen.key);
    if (d && d.title !== screen.title) setScreen({ ...screen, title: d.title });
  }, [demos, screen]);

  const goHome = useCallback(() => {
    jobAbort.current?.abort();
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
    setSubmitting(false);
    setScreen({ name: "home" });
  }, []);

  const runJob = useCallback(
    async (title: string, opts: { file?: File; key?: string; mask?: Blob }) => {
      jobAbort.current?.abort();
      const ctrl = new AbortController();
      jobAbort.current = ctrl;
      setBanner(null);
      setScreen({ name: "job", title, job: null });
      try {
        const first = await api.restore({ ...opts, fidelity: DEFAULT_FIDELITY });
        const done = await waitForJob(first, (j) => setScreen({ name: "job", title, job: j }), ctrl.signal);
        if (done.status === "error") throw new Error(done.error ?? "The restoration failed.");
        setScreen({ name: "result", key: done.key, title, fidelity: DEFAULT_FIDELITY });
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setBanner(`Couldn't restore ${title}: ${(e as Error).message}`);
        setScreen({ name: "home" });
      } finally {
        setSubmitting(false);
      }
    },
    [],
  );

  const onUpload = (file: File, markMyself: boolean) => {
    if (markMyself) {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = URL.createObjectURL(file);
      setScreen({ name: "brush", title: file.name, imageUrl: objectUrl.current, file });
    } else {
      runJob(file.name, { file });
    }
  };

  const onFixMask = (r: Result, title: string) => {
    setScreen({
      name: "brush",
      title,
      key: r.key,
      imageUrl: fileUrl(r.key, r.files.original),
      maskUrl: r.files.mask ? fileUrl(r.key, r.files.mask) : null,
    });
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-[110rem] flex-wrap items-baseline justify-between gap-4 px-6 py-5 sm:px-10">
          <button onClick={goHome} className="stamp text-2xl" aria-label="Cold Case, back to all photos">
            Cold Case
          </button>
          <p className="text-muted">Every guess, on the record.</p>
        </div>
      </header>

      {pipeline === "stub" && (
        <p className="bg-warn px-6 py-2 text-center font-semibold text-ink sm:px-10">
          Test mode: the server is running a fake pipeline. These results are not real restorations.
        </p>
      )}
      {banner && (
        <div className="mx-auto mt-6 flex max-w-[110rem] items-start justify-between gap-4 px-6 sm:px-10">
          <p className="text-invented">{banner}</p>
          <button onClick={() => setBanner(null)} className="text-muted underline">
            Dismiss
          </button>
        </div>
      )}

      <main className="mx-auto max-w-[110rem] px-6 py-12 sm:px-10">
        {screen.name === "home" && (
          <UploadView
            demos={demos}
            demosError={demosError}
            onOpenDemo={(d) => setScreen({ name: "result", key: d.key, title: d.title, fidelity: DEFAULT_FIDELITY })}
            onUpload={onUpload}
          />
        )}
        {screen.name === "job" && <JobProgress job={screen.job} name={screen.title} onCancel={goHome} />}
        {screen.name === "brush" && (
          <MaskBrush
            key={screen.imageUrl}
            imageUrl={screen.imageUrl}
            initialMaskUrl={screen.maskUrl}
            title={screen.title}
            submitting={submitting}
            onCancel={goHome}
            onSubmit={(mask) => {
              setSubmitting(true);
              runJob(screen.title, { file: screen.file, key: screen.key, mask });
            }}
          />
        )}
        {screen.name === "result" && (
          <ResultView
            key={screen.key}
            photoKey={screen.key}
            title={screen.title}
            initialFidelity={screen.fidelity}
            metrics={metrics}
            onFixMask={(r) => onFixMask(r, screen.title)}
            onFidelity={(f) => setScreen({ ...screen, fidelity: f })}
            onBack={goHome}
          />
        )}
      </main>
    </div>
  );
}
