import { fileUrl } from "../lib/api";
import type { Result } from "../lib/types";

export function FacesPanel({ result }: { result: Result }) {
  if (result.faces.length === 0) {
    return (
      <p className="max-w-[60ch] text-lg text-muted">
        No alternate faces for this photo. Either no face was found, or the damage didn't reach one, so
        there was nothing to invent.
      </p>
    );
  }
  const faces = result.faces.slice(0, 3);
  return (
    <figure>
      <div className="flex flex-wrap items-end gap-6">
        {result.face_original && (
          <div className="pr-6 sm:border-r sm:border-line">
            <FaceImage src={fileUrl(result.key, result.face_original)} alt="The damaged face as scanned" />
            <p className="mt-2 text-muted">As scanned</p>
          </div>
        )}
        <div className="relative flex flex-wrap items-end gap-8">
          {faces.map((f, i) => (
            <div key={f.file}>
              <FaceImage src={fileUrl(result.key, f.file)} alt={`Possible restoration ${i + 1}`} />
              <p className="mt-3 text-muted">
                Guess {i + 1}
                {typeof f.meta.seed === "number" && <span className="text-sm"> (seed {f.meta.seed})</span>}
              </p>
            </div>
          ))}
          {faces.length > 1 && (
            <span
              aria-hidden
              className="stamp pointer-events-none absolute left-1/2 top-[42%] -translate-x-1/2 -translate-y-1/2 bg-ground/90 text-3xl whitespace-nowrap"
            >
              {faces.length} guesses
            </span>
          )}
        </div>
      </div>
      <figcaption className="mt-8">
        <span className="font-serif text-4xl">
          One photo. <span className="text-invented">Three faces.</span>
        </span>
        <span className="mt-2 block text-lg text-body">The AI was equally sure of all three.</span>
      </figcaption>
    </figure>
  );
}

function FaceImage({ src, alt }: { src: string; alt: string }) {
  return (
    <img
      src={src}
      alt={alt}
      crossOrigin="anonymous"
      className="exhibit-frame h-56 w-auto min-w-40 object-contain"
    />
  );
}
