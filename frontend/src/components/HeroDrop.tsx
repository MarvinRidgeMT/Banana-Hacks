import { useRef, useState } from "react";
import { Link } from "./Link";

interface Props {
  onUpload: (file: File, markMyself: boolean, kind: "photo" | "document") => void;
  offline: boolean;
  caseHref: string;
}

/** Drop a scan straight onto the landing page. */
export function HeroDrop({ onUpload, offline, caseHref }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [kind, setKind] = useState<"photo" | "document">("photo");
  const [note, setNote] = useState<string | null>(null);

  const take = (files: FileList | null) => {
    const f = Array.from(files ?? []).find((x) => x.type.startsWith("image/") || /\.(tiff?|jpe?g|png|webp|bmp)$/i.test(x.name));
    if (!f) {
      setNote("That isn't an image. Use a JPG, PNG or TIFF scan.");
      return;
    }
    if (offline) {
      setNote("The restoring server is offline right now, so new photos can't be restored. The saved cases still work.");
      return;
    }
    setNote(null);
    onUpload(f, true, kind);
  };

  return (
    <div className="mt-8 max-w-[34rem]">
      <div
        role="button"
        tabIndex={0}
        aria-label={`Drop a damaged ${kind} here, or press Enter to choose a file`}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            input.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          take(e.dataTransfer.files);
        }}
        className={`hero-drop ${over ? "is-over" : ""}`}
      >
        <span className="hero-drop-icon" aria-hidden>
          ⤓
        </span>
        <span className="min-w-0">
          <span className="block font-semibold text-ground">Drop a damaged {kind} here</span>
          <span className="block text-sm text-ground/55">
            or <span className="underline underline-offset-4">choose a file</span> · JPG, PNG, TIFF · about 1–2 minutes
          </span>
        </span>
      </div>
      <input
        ref={input}
        type="file"
        accept="image/*,.tif,.tiff"
        className="hidden"
        onChange={(e) => {
          take(e.target.files);
          e.target.value = "";
        }}
      />
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ground/55">
        <span className="flex items-center gap-1" role="radiogroup" aria-label="What is it?">
          {(["photo", "document"] as const).map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={kind === k}
              onClick={() => setKind(k)}
              className={`rounded-full px-3 py-1 capitalize transition ${kind === k ? "bg-ground/15 text-ground" : "hover:text-ground"}`}
            >
              {k}
            </button>
          ))}
        </span>
        <Link to={caseHref} className="underline underline-offset-4 hover:text-ground">
          or open this case
        </Link>
      </div>
      {note && (
        <p role="alert" className="mt-3 text-sm text-[#ffb4a8]">
          {note}
        </p>
      )}
    </div>
  );
}
