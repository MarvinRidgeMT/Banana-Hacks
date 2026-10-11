import { seconds } from "../lib/format";
import type { Job } from "../lib/types";

export function JobProgress({ job, name, onCancel }: { job: Job | null; name: string; onCancel: () => void }) {
  let line = "Uploading…";
  if (job?.status === "queued") {
    line = job.position && job.position > 1
      ? `Waiting in line, position ${job.position}. Only one photo is restored at a time.`
      : "Starting the restoration…";
  } else if (job?.status === "running") {
    line = `Restoring now, ${seconds(job.elapsed)} so far. Each damaged area is regenerated several times so the map can compare them.`;
  }
  return (
    <div className="mx-auto max-w-2xl py-24 text-center">
      <h2 className="font-serif text-4xl">{name}</h2>
      <p className="mt-6 text-xl" aria-live="polite">
        {line}
      </p>
      <div className="mx-auto mt-8 h-1 w-64 overflow-hidden rounded-full bg-line">
        <div className="h-full w-1/3 animate-[slide_1.4s_ease-in-out_infinite] bg-inferred" />
      </div>
      <button onClick={onCancel} className="mt-10 text-muted underline">
        Back to photos (the restoration keeps going)
      </button>
      <style>{`@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(300%)}}`}</style>
    </div>
  );
}
