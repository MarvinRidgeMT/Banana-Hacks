import type { MaskSource, Metrics } from "../lib/types";

const MASK_TEXT: Record<MaskSource, string> = {
  segmenter: "Damage found by our trained segmenter.",
  human_file: "Damage marked by a person for this photo.",
  human_brush: "Damage marked by a person with the mask brush.",
};

function iou(v: number | null | undefined) {
  return typeof v === "number" ? v.toFixed(v < 0.1 ? 3 : 2) : "pending";
}

/** Where the damage mask came from, and how good the segmenter really is.
 * Both numbers are always shown together. */
export function EvidenceNotes({ metrics, maskSource }: { metrics: Metrics | null; maskSource: MaskSource }) {
  const seg = metrics?.segmenter;
  return (
    <section className="space-y-3 text-sm text-muted">
      <p className="text-base text-ink">{MASK_TEXT[maskSource]}</p>
      {seg && (
        <p>
          {seg.name ?? "Damage segmenter"}: IoU {iou(seg.synthetic_iou)} on synthetic damage
          {seg.synthetic_note ? ` (${seg.synthetic_note})` : ""}, {iou(seg.real_iou)} on real photos
          {seg.real_note ? ` (${seg.real_note})` : ""}.
        </p>
      )}
      {metrics?.map_calibration?.text && <p>{metrics.map_calibration.text}</p>}
      {metrics?.untouched_pixels?.text && <p>{metrics.untouched_pixels.text}</p>}
    </section>
  );
}
