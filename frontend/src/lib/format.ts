import type { ClassName, Summary } from "./types";

export const CLASSES: ClassName[] = ["observed", "inferred", "invented"];

export const CLASS_LABEL: Record<ClassName, string> = {
  observed: "Real",
  inferred: "Rebuilt",
  invented: "Invented",
};

export const CLASS_MEANING: Record<ClassName, string> = {
  observed: "Untouched original",
  inferred: "Every repair attempt agreed",
  invented: "The attempts disagreed: a guess",
};

/** Whole-number percentages that add up to exactly 100 (largest remainder),
 * with "<1%" for a class that is present but rounds to zero. */
export function percentages(s: Summary): Record<ClassName, string> {
  const raw = CLASSES.map((c) => Math.max(0, s[c]) * 100);
  const total = raw.reduce((a, b) => a + b, 0) || 1;
  const scaled = raw.map((v) => (v / total) * 100);
  const floors = scaled.map(Math.floor);
  let left = 100 - floors.reduce((a, b) => a + b, 0);
  const order = scaled
    .map((v, i) => ({ i, rem: v - Math.floor(v) }))
    .sort((a, b) => b.rem - a.rem);
  for (const { i } of order) {
    if (left <= 0) break;
    floors[i] += 1;
    left -= 1;
  }
  const out = {} as Record<ClassName, string>;
  CLASSES.forEach((c, i) => {
    out[c] = floors[i] === 0 && scaled[i] > 0 ? "<1%" : `${floors[i]}%`;
  });
  return out;
}

export const STAGE_LABEL: Record<string, string> = {
  inpainting: "Damage fill (diffusion inpainting)",
  face_restoration: "Face restoration (CodeFormer)",
  damage_segmentation: "Damage finder",
  colorization: "Colorization",
};

export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "Unknown stage";
  return STAGE_LABEL[stage] ?? stage.replace(/_/g, " ");
}

export function kindLabel(kind: string): string {
  if (kind === "face") return "Face";
  if (kind === "damage") return "Damaged area";
  return kind.charAt(0).toUpperCase() + kind.slice(1).replace(/_/g, " ");
}

export const FIDELITY_LABEL: Record<string, string> = {
  "0.3": "Restore more",
  "0.7": "Balanced",
  "1": "Preserve",
};

export function fidelityLabel(f: number): string {
  return FIDELITY_LABEL[String(f)] ?? `w = ${f}`;
}

export function seconds(s: number): string {
  if (s < 60) return `${Math.max(1, Math.round(s))} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${Math.round(s - m * 60)} s`;
}
