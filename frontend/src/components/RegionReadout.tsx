import { CLASS_LABEL, CLASS_MEANING, kindLabel, stageLabel } from "../lib/format";
import type { HoverInfo } from "../lib/types";
import { Swatch } from "./PhotoStage";

/** Large, steady version of the hover tooltip, for the side panel. */
export function RegionReadout({ hover }: { hover: HoverInfo | null }) {
  return (
    <section aria-live="polite" className="min-h-36 rounded-sm border border-line bg-surface p-4">
      {!hover ? (
        <p className="text-muted">Point at the restored photo to see where each pixel came from.</p>
      ) : hover.side === "original" ? (
        <p>
          <span className="font-semibold">Original scan.</span>{" "}
          <span className="text-muted">Drag the handle left to inspect the restored side.</span>
        </p>
      ) : (
        <dl className="space-y-1">
          <div className="flex items-center gap-2 text-xl font-semibold">
            <Swatch cls={hover.cls} className="h-5 w-5" />
            {CLASS_LABEL[hover.cls]}
          </div>
          <p className="text-muted">{CLASS_MEANING[hover.cls]}</p>
          {hover.region && (
            <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 pt-2">
              <dt className="text-muted">Region</dt>
              <dd>{kindLabel(hover.region.kind)}</dd>
              <dt className="text-muted">Confidence</dt>
              <dd className="tabular-nums">{Math.round(hover.region.confidence * 100)}%</dd>
              <dt className="text-muted">Changed by</dt>
              <dd>{stageLabel(hover.region.stage)}</dd>
            </div>
          )}
        </dl>
      )}
    </section>
  );
}
