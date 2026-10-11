export type ClassName = "observed" | "inferred" | "invented";
export type Summary = Record<ClassName, number>;

export interface Region {
  id: number;
  bbox: [number, number, number, number];
  area_px: number;
  inferred_px: number;
  invented_px: number;
  kind: string;
  stage: string;
  confidence: number;
  confidence_computed: number;
  pipeline_region_id: number | string | null;
}

export type MaskSource = "segmenter" | "human_file" | "human_brush";

export interface Result {
  key: string;
  source_sha256: string;
  fidelity: number;
  fidelity_applied: boolean;
  width: number;
  height: number;
  files: {
    original: string;
    restored: string;
    map: string;
    label: string;
    regions: string;
    manifest: string;
    signed: string | null;
    mask: string | null;
  };
  faces: { file: string; meta: Record<string, unknown> }[];
  face_original: string | null;
  pixel_summary: Summary;
  kind?: "photo" | "document";
  regions: Region[];
  mask_source: MaskSource;
  human_edited_mask: boolean;
  seconds: number;
  warnings: string[];
  manifest: Record<string, unknown>;
}

export interface Job {
  id: string;
  key: string;
  fidelity: number;
  status: "queued" | "running" | "done" | "error";
  position: number | null;
  error: string | null;
  detail: string | null;
  elapsed: number;
  result?: Result | null;
}

export interface Demo {
  id: string;
  file: string;
  title: string;
  blurb: string;
  credit: string;
  source_url: string;
  license: string;
  key: string;
  thumb: string;
  ready: number[];
  kind?: "photo" | "document";
}

export interface Metrics {
  segmenter?: {
    name?: string;
    synthetic_iou?: number | null;
    synthetic_note?: string;
    real_iou?: number | null;
    real_note?: string;
    real_folds?: number[] | null;
    real_iou_before_finetune?: number | null;
    /** "pending" means real_iou is still the pre-fine-tuning number. */
    real_status?: string;
  };
  map_calibration?: {
    text?: string;
    invented_de?: number | null;
    rebuilt_de?: number | null;
    spearman?: number | null;
  } | null;
  untouched_pixels?: {
    text?: string;
    changed_px?: number | null;
    tests_passed?: number | null;
    tests_total?: number | null;
  } | null;
  user_study?: { text?: string } | null;
  time_per_photo?: { text?: string } | null;
}

/** What is under the cursor on the photo. */
export interface HoverInfo {
  x: number;
  y: number;
  side: "original" | "restored";
  cls: ClassName;
  region: Region | null;
}

export const FIDELITY_STEPS = [0.3, 0.7, 1.0] as const;
export const DEFAULT_FIDELITY = 0.7;

/** Colour mode (POST /colorize): a colour version of the restoration and where the colour is a guess. */
export interface ColorResult {
  files: { colorized: string; map: string | null; manifest: string; signed: string | null };
  pixel_summary: Summary;
  lightness_check: { mean_abs_diff_L: number; p99_abs_diff_L: number; scale: string };
  models: string[];
  seconds: number;
}
