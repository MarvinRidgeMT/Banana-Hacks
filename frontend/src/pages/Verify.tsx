import { useRef, useState } from "react";
import { Link } from "../components/Link";
import { MapLegend } from "../components/MapLegend";
import { api } from "../lib/api";
import { failure } from "../lib/format";
import { href } from "../lib/router";
import type { VerifyResult } from "../lib/types";
import { DEFAULT_FIDELITY } from "../lib/types";

type Verdict = { word: string; tone: "good" | "bad" | "warn"; line: string };

function verdictOf(v: VerifyResult): Verdict {
  if (v.tampered) return { word: "Altered", tone: "bad", line: "The pixels were changed after the receipt was signed. Don't trust its labels for this file." };
  if (v.valid) return { word: "Verified", tone: "good", line: "This file still matches its signed Cold Case receipt: every pixel is exactly as restored." };
  if (v.pixels_match_record) return { word: "Receipt removed", tone: "warn", line: "The receipt was stripped, but these pixels exactly match a Cold Case restoration on record." };
  if (v.issues.some((i) => i.includes("not a Cold Case"))) return { word: "Other credentials", tone: "warn", line: "This file has Content Credentials from another tool, but no Cold Case receipt." };
  return { word: "No record", tone: "warn", line: "There is no record of how this image was edited. If it was AI-restored, nothing says where." };
}

export function Verify() {
  const input = useRef<HTMLInputElement>(null);
  const [res, setRes] = useState<VerifyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const run = async (file: File) => {
    setBusy(true);
    setError(null);
    setRes(null);
    setPreview(URL.createObjectURL(file));
    try {
      setRes(await api.verify(file));
    } catch (e) {
      setError(failure("Couldn't check that file", e));
    } finally {
      setBusy(false);
    }
  };

  const v = res ? verdictOf(res) : null;
  const toneClass = v?.tone === "good" ? "border-inferred text-inferred" : v?.tone === "bad" ? "border-invented text-invented" : "border-warn text-ink";

  return (
    <div className="space-y-12">
      <section className="max-w-3xl">
        <p className="case-label">Verify a photo</p>
        <h1 className="mt-3 font-serif text-5xl leading-[1.08] sm:text-6xl">Was this photo restored honestly?</h1>
        <p className="mt-5 text-xl leading-relaxed text-body">
          Got a restored photo from someone else? Drop it here. Cold Case reads the signed receipt inside the file,
          checks the pixels haven't been changed since, and shows which parts were real, rebuilt or invented.
          Nothing is stored.
        </p>
      </section>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) void run(f);
          }}
          className={`grid min-h-80 place-items-center rounded-sm border-2 border-dashed p-8 text-center ${dragging ? "border-inferred bg-surface" : "border-faint bg-surface/60"}`}
        >
          {preview ? (
            <img src={preview} alt="The file being checked" className="exhibit-frame max-h-96 w-auto" />
          ) : (
            <div>
              <p className="font-serif text-3xl">Drop a restored photo</p>
              <p className="mt-2 text-muted">PNG or JPG, up to 30 MB</p>
            </div>
          )}
          <button
            type="button"
            onClick={() => input.current?.click()}
            className="mt-6 rounded-sm bg-ink px-6 py-3 text-lg font-semibold text-ground hover:bg-ink/85"
          >
            {preview ? "Check another file" : "Choose a file"}
          </button>
          <input
            ref={input}
            type="file"
            accept="image/*"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void run(f);
              e.target.value = "";
            }}
          />
        </div>

        <div aria-live="polite">
          {busy && <p className="text-lg text-muted">Reading the receipt…</p>}
          {error && <p className="text-invented">{error}</p>}
          {res && v && (
            <div className="space-y-6">
              <p className={`stamp text-3xl ${toneClass}`}>{v.word}</p>
              <p className="text-xl">{v.line}</p>
              {res.pixel_summary && (
                <div>
                  <p className="case-label mb-3">What the receipt says about every pixel</p>
                  <MapLegend summary={res.pixel_summary} />
                </div>
              )}
              {res.stages.length > 0 && (
                <p className="text-body">
                  <span className="font-semibold">Recorded steps:</span> {res.stages.join(" → ").replaceAll("_", " ")}
                </p>
              )}
              {res.case_key && (
                <Link
                  to={href.result(res.case_key, res.fidelity ?? DEFAULT_FIDELITY)}
                  className="inline-block rounded-sm border border-ink px-5 py-3 font-semibold hover:bg-tag"
                >
                  Open the case on record →
                </Link>
              )}
              {res.issues.length > 0 && (
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
                  {res.issues.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {!res && !busy && !error && (
            <ul className="space-y-4 text-body">
              <li><span className="font-semibold text-inferred">Verified</span>: the file matches its signed receipt.</li>
              <li><span className="font-semibold text-invented">Altered</span>: someone edited the pixels after restoration.</li>
              <li><span className="font-semibold">No record</span>: nothing says how, or whether, it was restored.</li>
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
