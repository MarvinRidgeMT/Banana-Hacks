import { useState } from "react";
import { CLASSES, CLASS_LABEL } from "../lib/format";
import { readStored, writeStored } from "../lib/storage";
import { Swatch } from "./PhotoStage";

const KEY = "coldcase.hint.how-to-read";

const SENTENCE = {
  observed: "Untouched original: these pixels are exactly as they were scanned.",
  inferred: "Every repair attempt agreed on these pixels, which is not proof they're right.",
  invented: "The attempts disagreed: these pixels are a guess, not a recovery.",
} as const;

export function ReadingHint() {
  const [hidden, setHidden] = useState(() => readStored(KEY) === "dismissed");
  if (hidden) return null;
  return (
    <aside aria-labelledby="how-to-read" className="relative border border-line bg-surface p-5 pr-14 sm:p-6 sm:pr-16">
      <h2 id="how-to-read" className="case-label">How to read this</h2>
      <ul className="mt-3 space-y-2">
        {CLASSES.map((c) => (
          <li key={c} className="flex items-start gap-3">
            <Swatch cls={c} className="mt-1 h-4 w-4" />
            <span>
              <span className="font-semibold">{CLASS_LABEL[c]}.</span> {SENTENCE[c]}
            </span>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => {
          writeStored(KEY, "dismissed");
          setHidden(true);
        }}
        aria-label="Dismiss how to read this"
        className="absolute right-3 top-3 grid h-10 w-10 place-items-center rounded-sm text-2xl leading-none text-muted hover:bg-tag hover:text-ink"
      >
        <span aria-hidden>×</span>
      </button>
    </aside>
  );
}
