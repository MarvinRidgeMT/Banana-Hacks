import { useRef, useState } from "react";
import { fileUrl } from "../lib/api";
import type { Demo } from "../lib/types";

interface Props {
  demos: Demo[] | null;
  demosError: string | null;
  onOpenDemo: (d: Demo) => void;
  onUpload: (file: File, markMyself: boolean) => void;
}

const ACCEPT = "image/jpeg,image/png,image/tiff,image/webp,image/bmp";

export function UploadView({ demos, demosError, onOpenDemo, onUpload }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [markMyself, setMarkMyself] = useState(false);
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
          <h1 className="font-serif text-5xl leading-[1.08] sm:text-6xl">
            Old photos, restored. Every guess on the record.
          </h1>
          <p className="mt-6 max-w-[52ch] text-xl leading-relaxed text-muted">
            AI restorers don't recover lost detail. They invent it. Cold Case repairs the damage and
            labels every pixel: real, rebuilt from the rest of the photo, or invented.
          </p>
        </div>

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
            <span>Let me mark the damage myself first</span>
          </label>
          {note && <p className="mt-4 text-inferred">{note}</p>}
        </div>
      </section>

      <section>
        <h2 className="font-serif text-3xl">Or start with one of these</h2>
        {demosError && <p className="mt-4 text-invented">{demosError}</p>}
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
              <p className="mt-2 text-sm text-muted">
                {d.source_url && !d.source_url.startsWith("FILL") ? (
                  <a href={d.source_url} target="_blank" rel="noreferrer" className="underline">
                    {d.credit}
                  </a>
                ) : (
                  d.credit
                )}
                {d.license && `, ${d.license}`}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
