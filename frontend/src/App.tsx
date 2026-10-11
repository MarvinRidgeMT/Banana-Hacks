import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNote } from "./components/Feedback";
import { JobProgress } from "./components/JobProgress";
import { MaskBrush } from "./components/MaskBrush";
import { ResultView } from "./components/ResultView";
import { SiteFooter } from "./components/SiteFooter";
import { SiteHeader } from "./components/SiteHeader";
import { UploadView } from "./components/UploadView";
import { api, fileUrl, waitForJob } from "./lib/api";
import { href, navigate, useRouter, type Route } from "./lib/router";
import { failure } from "./lib/format";
import type { Demo, Job, Metrics, Result } from "./lib/types";
import { DEFAULT_FIDELITY } from "./lib/types";
import { About } from "./pages/About";
import { Evidence } from "./pages/Evidence";
import { Home } from "./pages/Home";
import { HowItWorks } from "./pages/HowItWorks";
import { NotFound } from "./pages/NotFound";

type JobOpts = { file?: File; key?: string; mask?: Blob };

/** A brush or job screen shown in place of the current page. It isn't a route:
 * any navigation ends it. */
type Task =
  | { name: "brush"; title: string; imageUrl: string; maskUrl?: string | null; file?: File; key?: string }
  | { name: "job"; title: string; job: Job | null };

const PAGE_TITLE: Record<Exclude<Route["name"], "result">, string> = {
  home: "Cold Case",
  restore: "Cold Case · Restore a photo",
  "how-it-works": "Cold Case · How it works",
  evidence: "Cold Case · Evidence",
  about: "Cold Case · About",
  "not-found": "Cold Case · No record of this page",
};

export default function App() {
  const { route, seq } = useRouter();
  const [task, setTask] = useState<Task | null>(null);
  const [demos, setDemos] = useState<Demo[] | null>(null);
  const [demosError, setDemosError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [pipeline, setPipeline] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  /** Titles of uploaded photos, by key, so their result page can be named. */
  const [titles, setTitles] = useState<Record<string, string>>({});
  const jobAbort = useRef<AbortController | null>(null);
  const objectUrl = useRef<string | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  const lastJob = useRef<{ title: string; opts: JobOpts } | null>(null);

  const loadDemos = useCallback(() => {
    setDemos(null);
    setDemosError(null);
    api
      .demos()
      .then(setDemos)
      .catch((e) => setDemosError(failure("Couldn't load the demo photos", e)));
  }, []);

  useEffect(() => {
    loadDemos();
    api.metrics().then(setMetrics).catch(() => setMetrics(null));
    api.health().then((h) => setPipeline(h.pipeline)).catch(() => setPipeline(null));
  }, [loadDemos]);

  const endTask = useCallback(() => {
    jobAbort.current?.abort();
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
    setSubmitting(false);
    setTask(null);
  }, []);

  // Every navigation leaves any brush or job screen, drops the banner and starts at the top.
  // Focus moves to the new page too, so screen readers don't stay on the old link.
  useEffect(() => {
    endTask();
    setBanner(null);
    window.scrollTo(0, 0);
    if (seq > 0) mainRef.current?.focus({ preventScroll: true });
  }, [seq, endTask]);

  const resultTitle =
    route.name === "result"
      ? (demos?.find((d) => d.key === route.key)?.title ?? titles[route.key] ?? "Restored photo")
      : null;

  useEffect(() => {
    document.title = resultTitle ? `Cold Case · ${resultTitle}` : PAGE_TITLE[route.name as keyof typeof PAGE_TITLE];
  }, [route.name, resultTitle]);

  const runJob = useCallback(
    async (title: string, opts: JobOpts) => {
      lastJob.current = { title, opts };
      jobAbort.current?.abort();
      const ctrl = new AbortController();
      jobAbort.current = ctrl;
      setBanner(null);
      setTask({ name: "job", title, job: null });
      try {
        const first = await api.restore({ ...opts, fidelity: DEFAULT_FIDELITY });
        const done = await waitForJob(first, (j) => setTask({ name: "job", title, job: j }), ctrl.signal);
        if (done.status === "error") throw new Error(done.error ?? "The restoration failed.");
        setTitles((t) => ({ ...t, [done.key]: title }));
        navigate(href.result(done.key, DEFAULT_FIDELITY));
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setBanner(failure(`Couldn't restore ${title}`, e));
        setTask(null);
      } finally {
        setSubmitting(false);
      }
    },
    [],
  );

  const onUpload = async (file: File, markMyself: boolean) => {
    if (markMyself) {
      // Show the segmenter's proposed mask in the brush so a person can fix it before restoring.
      setBanner(null);
      setTask({ name: "job", title: file.name, job: null });
      try {
        const p = await api.propose(file);
        setTask({
          name: "brush",
          title: file.name,
          key: p.key,
          imageUrl: fileUrl(p.key, p.original),
          maskUrl: p.mask ? fileUrl(p.key, p.mask) : null,
        });
      } catch {
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
        objectUrl.current = URL.createObjectURL(file);
        setTask({ name: "brush", title: file.name, imageUrl: objectUrl.current, file });
      }
    } else {
      runJob(file.name, { file });
    }
  };

  const onFixMask = (r: Result, title: string) => {
    setTask({
      name: "brush",
      title,
      key: r.key,
      imageUrl: fileUrl(r.key, r.files.original),
      maskUrl: r.files.mask ? fileUrl(r.key, r.files.mask) : null,
    });
  };

  const page = () => {
    if (task?.name === "job") return <JobProgress job={task.job} name={task.title} onCancel={endTask} />;
    if (task?.name === "brush") {
      return (
        <MaskBrush
          key={task.imageUrl}
          imageUrl={task.imageUrl}
          initialMaskUrl={task.maskUrl}
          title={task.title}
          submitting={submitting}
          onCancel={endTask}
          onSubmit={(mask) => {
            setSubmitting(true);
            runJob(task.title, { file: task.file, key: task.key, mask });
          }}
        />
      );
    }
    switch (route.name) {
      case "home":
        return <Home demos={demos} demosError={demosError} onRetryDemos={loadDemos} />;
      case "restore":
        return (
          <UploadView
            demos={demos}
            demosError={demosError}
            onRetryDemos={loadDemos}
            onOpenDemo={(d) => navigate(href.result(d.key, DEFAULT_FIDELITY))}
            onUpload={onUpload}
          />
        );
      case "result":
        return (
          <ResultView
            key={`${route.key}:${seq}`}
            photoKey={route.key}
            title={resultTitle ?? "Restored photo"}
            initialFidelity={route.fidelity}
            metrics={metrics}
            onFixMask={(r) => onFixMask(r, resultTitle ?? "Restored photo")}
            onFidelity={(f) => navigate(href.result(route.key, f), { replace: true })}
          />
        );
      case "how-it-works":
        return <HowItWorks />;
      case "evidence":
        return <Evidence metrics={metrics} />;
      case "about":
        return <About demos={demos} demosError={demosError} />;
      case "not-found":
        return <NotFound hash={route.hash} />;
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          mainRef.current?.focus();
        }}
        className="sr-only z-50 rounded-sm bg-ink px-4 py-3 font-semibold text-ground focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to content
      </a>
      {pipeline === "stub" && (
        <p className="bg-warn px-6 py-2 text-center font-semibold text-ink sm:px-10">
          Test mode: the server is running a fake pipeline. These results are not real restorations.
        </p>
      )}
      <SiteHeader route={route} seq={seq} />

      {banner && (
        <div className="mx-auto mt-6 flex w-full max-w-[110rem] flex-wrap items-center justify-between gap-4 px-6 sm:px-10">
          <ErrorNote
            message={banner}
            onRetry={() => lastJob.current && runJob(lastJob.current.title, lastJob.current.opts)}
          />
          <button onClick={() => setBanner(null)} className="text-muted underline">
            Dismiss
          </button>
        </div>
      )}

      <main
        ref={mainRef}
        id="main-content"
        tabIndex={-1}
        className="mx-auto w-full max-w-[110rem] flex-1 px-6 py-12 outline-none sm:px-10"
      >
        {page()}
      </main>

      <SiteFooter />
    </div>
  );
}
