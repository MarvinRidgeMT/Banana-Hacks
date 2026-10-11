import { CLASSES, CLASS_LABEL, CLASS_MEANING, percentages } from "../lib/format";
import type { ClassName, Summary } from "../lib/types";
import { Swatch } from "./PhotoStage";

/** The share of the photo in each class, as a bar you can read across a room. */
export function MapLegend({ summary, meanings }: { summary: Summary; meanings?: Partial<Record<ClassName, string>> }) {
  const pct = percentages(summary);
  return (
    <figure>
      <div
        className="flex h-9 w-full overflow-hidden rounded-sm border border-line"
        role="img"
        aria-label={CLASSES.map((c) => `${pct[c]} ${CLASS_LABEL[c].toLowerCase()}`).join(", ")}
      >
        {CLASSES.map((c) => {
          const share = Math.max(0, summary[c]);
          if (share <= 0) return null;
          const bg = c === "observed" ? "bg-observed" : c === "inferred" ? "bg-inferred" : "hatch-invented";
          // keep tiny shares visible as a sliver
          return <div key={c} className={bg} style={{ flexGrow: share, flexBasis: 0, minWidth: 4 }} />;
        })}
      </div>
      <figcaption className="mt-3 grid grid-cols-[auto_auto_auto_1fr] items-baseline gap-x-3 gap-y-2">
        {CLASSES.map((c) => (
          <div key={c} className="contents">
            <Swatch cls={c} className="h-4 w-4 translate-y-0.5" />
            <span className="font-semibold">{CLASS_LABEL[c]}</span>
            <span className="text-right text-xl font-semibold tabular-nums">{pct[c]}</span>
            <span className="text-sm text-muted">{meanings?.[c] ?? CLASS_MEANING[c]}</span>
          </div>
        ))}
      </figcaption>
    </figure>
  );
}
