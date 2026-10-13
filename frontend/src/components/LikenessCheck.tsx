import { useRef, useState } from "react";
import { api } from "../lib/api";
import { failure } from "../lib/format";
import type { LikenessResult, Result } from "../lib/types";

/** Score each face guess against a real photo of the same person. */
export function LikenessCheck({ result }: { result: Result }) {
  const input = useRef<HTMLInputElement>(null);
  const [res, setRes] = useState<LikenessResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const run = async (file: File) => {
    setBusy(true);
    setError(null);
    setRes(null);
    setPreview(URL.createObjectURL(file));
    try {
      setRes(await api.likeness(result.key, result.fidelity, file));
    } catch (e) {
      setError(failure("Couldn't check the likeness", e));
    } finally {
      setBusy(false);
    }
  };

  const max = 1;
  const anyMatch = res?.scores.some((s) => s.name.startsWith("Guess") && s.same_person);
  const allMatch = res?.scores.filter((s) => s.name.startsWith("Guess")).every((s) => s.same_person);

  return (
    <section className="mt-14 rounded-sm border border-line bg-surface/70 p-6 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="max-w-[60ch]">
          <p className="case-label">Likeness check</p>
          <h3 className="mt-2 font-serif text-3xl">Is it still the same person?</h3>
          <p className="mt-3 text-body">
            Add another photo of the same person, ideally undamaged. A face-recognition model scores each guess against
            it. It can tell you if a guess turned them into someone else; it cannot tell you which guess is right.
          </p>
        </div>
        <div className="flex items-center gap-4">
          {preview && <img src={preview} alt="Reference photo" className="exhibit-frame h-28 w-auto" />}
          <button
            type="button"
            onClick={() => input.current?.click()}
            disabled={busy}
            className="rounded-sm bg-ink px-5 py-3 font-semibold text-ground hover:bg-ink/85 disabled:opacity-60"
          >
            {busy ? "Checking…" : res ? "Try another photo" : "Add a reference photo"}
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
      </div>
      {error && <p className="mt-4 text-invented">{error}</p>}
      {res && (
        <div className="mt-8">
          <ul className="space-y-3">
            {res.scores.map((s) => (
              <li key={s.name} className="grid grid-cols-[9rem_1fr_4rem] items-center gap-4">
                <span className="font-semibold">{s.name}</span>
                <span className="relative h-4 rounded-sm bg-line">
                  <span
                    className={`absolute inset-y-0 left-0 rounded-sm ${s.same_person ? "bg-inferred" : "hatch-invented"}`}
                    style={{ width: `${Math.max(2, (Math.max(0, s.similarity) / max) * 100)}%` }}
                  />
                  <span
                    aria-hidden
                    className="absolute inset-y-[-4px] w-0.5 bg-ink"
                    style={{ left: `${res.threshold * 100}%` }}
                    title="Same-person threshold"
                  />
                </span>
                <span className="readout text-right tabular-nums">{s.similarity.toFixed(2)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-sm text-muted">
            Black line: same-person threshold ({res.threshold}). Model: {res.model}.
          </p>
          <p className="mt-5 max-w-[70ch] text-lg">
            {allMatch
              ? "All guesses still read as the same person as your reference. The invention didn't change who this is, but the details (an eye, a cheek) are still guesses."
              : anyMatch
                ? `Only some guesses still read as the same person (closest: ${res.best}). Treat the others as a different face.`
                : "None of the guesses reads as the person in your reference photo. The restored face should not be presented as them."}
          </p>
        </div>
      )}
    </section>
  );
}
