import { useEffect, useState } from "react";
import { api, fileUrl } from "../lib/api";
import { failure } from "../lib/format";
import type { ColorResult, Result } from "../lib/types";
import { ErrorNote } from "./Feedback";
import { MapLegend } from "./MapLegend";

interface Props {
  result: Result;
  color: ColorResult | null;
  on: boolean;
  onColor: (c: ColorResult | null) => void;
  onToggle: (on: boolean) => void;
}

const MEANINGS = {
  observed: "No color was in the scan, so none is real.",
  inferred: "Both color models agree: a well-supported guess.",
  invented: "The models disagree: decoration, not history.",
};

/** Colour mode: add colour to a black-and-white restoration and show where it is a guess. */
export function ColorPanel({ result, color, on, onColor, onToggle }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setError(null), [result.key, result.fidelity]);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const c = await api.colorize(result.key, result.fidelity);
      onColor(c);
      onToggle(true);
    } catch (e) {
      setError(failure("Couldn't add color", e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4 rounded-sm border border-line p-5">
      <div className="flex items-center justify-between gap-4">
        <span className="font-serif text-2xl">Add color</span>
        <span className="tag">guess, labeled</span>
      </div>
      <p className="text-sm text-muted">
        A black-and-white photo holds no color, so every color added is a guess. Cold Case keeps the scan's own
        brightness and detail, adds only color, and marks where two independent color models disagree.
      </p>

      {!color ? (
        <button
          onClick={run}
          disabled={busy}
          className="w-full rounded-sm bg-ink px-4 py-3 text-ground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {busy ? "Coloring… (a few seconds)" : "Color this photo"}
        </button>
      ) : (
        <>
          <label className="flex cursor-pointer items-center justify-between gap-4">
            <span className="font-semibold">Show color</span>
            <input
              type="checkbox"
              role="switch"
              checked={on}
              onChange={(e) => onToggle(e.target.checked)}
              className="h-6 w-11 cursor-pointer appearance-none rounded-full bg-line transition-colors before:mt-0.5 before:block before:h-5 before:w-5 before:translate-x-0.5 before:rounded-full before:bg-surface before:shadow before:transition-transform checked:bg-inferred checked:before:translate-x-5"
            />
          </label>
          <MapLegend summary={color.pixel_summary} meanings={MEANINGS} />
          <p className="readout text-sm text-muted">
            Brightness kept within {color.lightness_check.mean_abs_diff_L.toFixed(2)} of 100 (average). Turn on
            "Show the evidence" to see where the color is a guess.
          </p>
          {color.files.signed && (
            <a
              href={fileUrl(result.key, color.files.signed, true)}
              className="inline-block rounded-sm border border-line px-4 py-2 hover:bg-tag"
            >
              Download color version with receipt
            </a>
          )}
        </>
      )}
      {error && <ErrorNote message={error} onRetry={run} />}
    </section>
  );
}
