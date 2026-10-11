import { useRef, useState } from "react";
import { fileUrl } from "../lib/api";
import type { Demo } from "../lib/types";
import { DemoCredit } from "./DemoCredit";
import { DemoCardSkeleton, ErrorNote } from "./Feedback";

interface Props {
  demos: Demo[] | null;
  demosError: string | null;
  onRetryDemos: () => void;
  onOpenDemo: (d: Demo) => void;
  onUpload: (file: File, markMyself: boolean) => void;
}

const ACCEPT = "image/jpeg,image/png,image/tiff,image/webp,image/bmp";

export function UploadView({ demos, demosError, onRetryDemos, onOpenDemo, onUpload }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [markMyself, setMarkMyself] = useState(true);
  const [note, setNote] = useState<string | null>(null);

  const take = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const images = Array.from(files).filter((f) => f.type.startsWith("image/") || /\.(tiff?|jpe?g|png|webp|bmp)$/i.test(f.name));
    if (images.length === 0) {
      setNote("That isn't an image. Use a JPG, PNG or TIFF scan.");
      return;
    }
    setNote(images.length > 1 ? `Restoring the first photo, ${images[0].name}. Batch restore isn't available yet.` : null);
    onUpload(images[0], markMyself);
  };

  return (
    <div className="space-y-16">
      <section className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:items-center">
        <div>
          <p className="tag">Restore a photo</p>
          <h1 className="mt-5 font-serif text-4xl leading-[1.08] sm:text-5xl">
            Bring a damaged photo. Leave with the evidence.
          </h1>
          <ol className="mt-8 space-y-4">
            {[
              ["Upload a scan", "A JPG, PNG or TIFF of a damaged print or negative."],
              ["Check the damage mask", "Our detector paints what it thinks is lost. Add what it missed; erase what it got wrong."],
              ["Get the evidence", "The restoration, every pixel labelled Real, Rebuilt or Invented, and a signed receipt. About 1 to 2 minutes."],
            ].map(([t, d], i) => (
              <li key={t} className="flex gap-4">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink font-mono text-sm text-ground">{i + 1}</span>
                <span>
                  <span className="block text-lg font-semibold">{t}</span>
                  <span className="block text-body">{d}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>

        <div>
          <p className="mb-4 text-body">
            Works best on scans with tears, missing pieces or scratches. Fading and stains aren't counted
            as damage.
          </p>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              take(e.dataTransfer.files);
            }}
            className={`rounded-sm border-2 border-dashed p-10 text-center transition-colors ${
              dragging ? "border-inferred bg-surface" : "border-faint bg-surface/60"
            }`}
          >
            <p className="font-serif text-3xl">Drop a scanned photo here</p>
            <p className="mt-2 text-muted">JPG, PNG or TIFF, up to 30 MB</p>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="mt-6 rounded-sm bg-ink px-6 py-3 text-lg font-semibold text-ground hover:bg-ink/85"
            >
              Choose a photo
            </button>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => {
                take(e.target.files);
                e.target.value = "";
              }}
            />
            <label className="mt-6 flex cursor-pointer items-center justify-center gap-3 text-left">
              <input
                type="checkbox"
                checked={markMyself}
                onChange={(e) => setMarkMyself(e.target.checked)}
                className="h-5 w-5 accent-[var(--color-inferred)]"
              />
              <span>Review the damage mask before restoring (recommended)</span>
            </label>
            {note && <p className="mt-4 text-inferred">{note}</p>}
          </div>
        </div>
      </section>

      <section>
        <h2 className="font-serif text-3xl">Or start with one of these</h2>
        {demosError && <ErrorNote message={demosError} onRetry={onRetryDemos} className="mt-4" />}
        {!demos && !demosError && (
          <ul className="mt-6 grid grid-cols-1 gap-8 sm:grid-cols-2 xl:grid-cols-4" aria-label="Loading demo photos">
            {[0, 1, 2, 3].map((i) => (
              <li key={i}>
                <DemoCardSkeleton />
              </li>
            ))}
          </ul>
        )}
        {demos && demos.length === 0 && (
          <p className="mt-4 text-muted">
            No demo photos on the server yet. Add them to backend/demos and list them in demos.json.
          </p>
        )}
        <ul className="mt-6 grid grid-cols-1 gap-8 sm:grid-cols-2 xl:grid-cols-4">
          {(demos ?? []).map((d) => (
            <li key={d.id}>
              <button
                onClick={() => onOpenDemo(d)}
                className="group block w-full text-left"
                aria-label={`Open ${d.title}`}
              >
                <div className="aspect-[4/5] overflow-hidden bg-mat p-3 outline-2 outline-offset-4 outline-transparent group-hover:outline-invented">
                  <img
                    src={fileUrl(d.key, d.thumb)}
                    alt=""
                    crossOrigin="anonymous"
                    className="h-full w-full object-contain"
                  />
                </div>
                <p className="mt-3 font-serif text-2xl group-hover:underline">{d.title}</p>
                <p className="mt-1 text-muted">{d.blurb}</p>
              </button>
              <DemoCredit demo={d} className="mt-2" />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
