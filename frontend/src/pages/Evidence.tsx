import type { ReactNode } from "react";
import type { Metrics } from "../lib/types";

/** Used for anything /metrics doesn't provide. */
const FALLBACK = {
  syntheticIou: 0.898,
  syntheticNote: "v3 segmenter, held-out photos with realistic synthetic damage",
  realIou: 0.182,
  realNote: "v4, fine-tuned on 15 hand-labeled real photos; 3-fold cross-validated on held-out photos",
  realFolds: [0.156, 0.252, 0.153],
  realBefore: 0.007,
  inventedDe: 13.4,
  rebuiltDe: 7.3,
  spearman: 0.29,
  changedPx: 0,
  testsPassed: 8,
  testsTotal: 8,
};

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Values that belong together (a number and the note describing it) come
 * from the same source, so the page never pairs a server number with a
 * fallback description. */
function evidenceNumbers(metrics: Metrics | null) {
  const seg = metrics?.segmenter;
  const cal = metrics?.map_calibration;
  const px = metrics?.untouched_pixels;

  const synth = num(seg?.synthetic_iou);
  const real = seg?.real_status === "pending" ? null : num(seg?.real_iou);
  const folds = seg?.real_folds?.every((f) => num(f) !== null) ? seg.real_folds : null;
  const invented = num(cal?.invented_de);
  const rebuilt = num(cal?.rebuilt_de);
  const calOk = invented !== null && rebuilt !== null && rebuilt > 0;

  return {
    syntheticIou: synth ?? FALLBACK.syntheticIou,
    syntheticNote: (synth !== null && seg?.synthetic_note) || FALLBACK.syntheticNote,
    realIou: real ?? FALLBACK.realIou,
    realNote: (real !== null ? seg?.real_note : null) || FALLBACK.realNote,
    realFolds: real !== null ? folds : FALLBACK.realFolds,
    realBefore: num(seg?.real_iou_before_finetune) ?? FALLBACK.realBefore,
    inventedDe: calOk ? invented : FALLBACK.inventedDe,
    rebuiltDe: calOk ? rebuilt : FALLBACK.rebuiltDe,
    spearman: num(cal?.spearman) ?? FALLBACK.spearman,
    changedPx: num(px?.changed_px) ?? FALLBACK.changedPx,
    testsPassed: num(px?.tests_passed) ?? FALLBACK.testsPassed,
    testsTotal: num(px?.tests_total) ?? FALLBACK.testsTotal,
    timePerPhoto: metrics?.time_per_photo?.text ?? null,
  };
}

const iou3 = (v: number) => v.toFixed(3);


type Row = { key: string; cells: [ReactNode, ReactNode, ReactNode] };

/** A three-column table that becomes stacked cards on phones. Only one of the
 * two is displayed, so screen readers meet the content once. */
function RecordTable({ caption, columns, rows }: { caption: string; columns: [string, string, string]; rows: Row[] }) {
  return (
    <>
      <table className="hidden w-full border-collapse bg-surface text-left md:table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line">
            {columns.map((c) => (
              <th key={c} scope="col" className="case-label px-5 py-4 font-normal">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-b border-line align-top last:border-b-0">
              <th scope="row" className="w-[26%] px-5 py-4 font-semibold">
                {r.cells[0]}
              </th>
              <td className="w-[30%] px-5 py-4 text-ink">{r.cells[1]}</td>
              <td className="px-5 py-4 text-body">{r.cells[2]}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="space-y-4 md:hidden" aria-label={caption}>
        {rows.map((r) => (
          <li key={r.key} className="bg-surface p-5">
            <p className="font-semibold">{r.cells[0]}</p>
            <dl className="mt-3 space-y-3">
              <div>
                <dt className="case-label">{columns[1]}</dt>
                <dd className="mt-1 text-ink">{r.cells[1]}</dd>
              </div>
              <div>
                <dt className="case-label">{columns[2]}</dt>
                <dd className="mt-1 text-body">{r.cells[2]}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}

function IouChart({ bars }: { bars: { label: string; value: number }[] }) {
  const W = 480;
  const plot = 400; // leaves room for the value label after a full-length bar
  const rowH = 66;
  const top = 6;
  const axisY = top + bars.length * rowH + 4;
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <figure className="max-w-xl">
      <svg
        viewBox={`0 0 ${W} ${axisY + 30}`}
        className="w-full"
        role="img"
        aria-labelledby="iou-chart-title"
      >
        <title id="iou-chart-title">
          {`Damage detector IoU: ${bars.map((b) => `${b.label} ${iou3(b.value)}`).join("; ")}.`}
        </title>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={t * plot} x2={t * plot} y1={top} y2={axisY} stroke="var(--color-line)" />
            <text
              x={t * plot}
              y={axisY + 22}
              fontSize="14"
              fill="var(--color-muted)"
              fontFamily="var(--font-mono)"
              textAnchor={t === 0 ? "start" : t === 1 ? "end" : "middle"}
            >
              {t === 0 ? "0" : t.toFixed(2)}
            </text>
          </g>
        ))}
        {bars.map((b, i) => {
          const y = top + i * rowH;
          const w = Math.max(3, Math.min(1, b.value) * plot);
          return (
            <g key={b.label}>
              <text x={0} y={y + 18} fontSize="16" fill="var(--color-ink)">
                {b.label}
              </text>
              <rect x={0} y={y + 28} width={w} height={26} fill="var(--color-ink)" />
              <text
                x={w + 8}
                y={y + 47}
                fontSize="16"
                fontWeight="600"
                fill="var(--color-ink)"
                fontFamily="var(--font-mono)"
              >
                {iou3(b.value)}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-4 text-sm text-muted">
        Intersection over union between the detector's damage mask and the true damage. 1.0 is a perfect match.
      </figcaption>
    </figure>
  );
}

const BUILT_VS_USED: Row[] = [
  {
    key: "segmenter",
    cells: [
      "Damage segmenter",
      "Built (trained this weekend)",
      "U-Net with a ResNet-34 encoder; procedural damage generator; fine-tuned on 15 hand-labeled real photos",
    ],
  },
  {
    key: "inpainting",
    cells: [
      "Multi-seed inpainting",
      "Built around a model",
      "Our region cropping, 8-seed runs, compositing and untouched-pixel guarantee around SDXL inpainting",
    ],
  },
  {
    key: "map",
    cells: ["Invention Map", "Built", "Per-pixel change and seed spread in CIELAB, calibrated threshold, region confidence"],
  },
  {
    key: "faces",
    cells: ["Three faces", "Built", "Picks the most different seed outputs for the most-invented face"],
  },
  {
    key: "receipt",
    cells: ["Receipt", "Built around a library", "Manifest format is ours; signing uses c2pa-python with a test certificate"],
  },
  {
    key: "web",
    cells: [
      "Website and API",
      "Built",
      "React, Vite, TypeScript, Tailwind; job queue, cache, mask brush, region hover",
    ],
  },
  { key: "sdxl", cells: ["SDXL inpainting 0.1", "Used", "Diffusion inpainting, run on Apple silicon (MPS)"] },
  {
    key: "codeformer",
    cells: ["CodeFormer", "Used", "Face restoration, with its fidelity weight exposed (non-commercial license)"],
  },
  { key: "telea", cells: ["OpenCV Telea", "Used", "Fill for thin cracks"] },
];

export function Evidence({ metrics }: { metrics: Metrics | null }) {
  const n = evidenceNumbers(metrics);
  const ratio = (n.inventedDe / n.rebuiltDe).toFixed(1);
  const folds = n.realFolds ? ` (folds ${n.realFolds.map(iou3).join(" / ")})` : "";

  const results: Row[] = [
    {
      key: "synthetic",
      cells: ["Damage detection, synthetic photos", `IoU ${iou3(n.syntheticIou)}`, n.syntheticNote],
    },
    {
      key: "real",
      cells: ["Damage detection, real photos", `IoU ${iou3(n.realIou)}`, `${n.realNote}${folds}`],
    },
    {
      key: "labels",
      cells: [
        "Do the labels mean something?",
        `Invented pixels are ${ratio}× further from the truth`,
        `On synthetic photos with known originals: ${n.inventedDe.toFixed(1)} ΔE for Invented vs ${n.rebuiltDe.toFixed(1)} ΔE for Rebuilt (Spearman ρ ${n.spearman.toFixed(2)})`,
      ],
    },
    {
      key: "untouched",
      cells: [
        "Undamaged pixels changed",
        String(n.changedPx),
        `Automated test, ${n.testsPassed}/${n.testsTotal} pass with the models swapped for random noise; every demo run reports 0`,
      ],
    },
    {
      key: "receipt",
      cells: ["Receipt", "Valid C2PA Content Credential", "Validates; the only flag is the untrusted test certificate"],
    },
    {
      key: "steps",
      cells: [
        "SDXL steps: 20 vs 30 vs 40",
        "Under 1.2% apart, so we use 20",
        "Face ΔE against a known true face (simulated damage): 8.71 / 8.61 / 8.62",
      ],
    },
    {
      key: "documents",
      cells: [
        "Documents (experiment)",
        "IoU 0.914 vs 0.861; ink wrongly flagged 0.18% vs 0.65%",
        "A document detector fine-tuned in 40 min on 800 synthetic pages, vs our photo model, on 80 held-out synthetic pages. Not yet tested on real damaged documents, and never used to generate text.",
      ],
    },
    {
      key: "color",
      cells: [
        "Color mode: brightness kept",
        "Within 0.1 of 100 on average",
        "Lab lightness of the colored photo vs the restoration, on our demo photos. Only color is added; about 1.6 s per photo.",
      ],
    },
    {
      key: "color-guess",
      cells: [
        "Color mode: where it's a guess",
        "Lincoln 33% guessed; street scene 8%",
        "Share of pixels where two independently trained color models (ECCV 2016, SIGGRAPH 2017) disagree. No color is ever labeled Real.",
      ],
    },
    ...(n.timePerPhoto
      ? [
          {
            key: "time",
            cells: ["Time per photo", n.timePerPhoto, "One teammate in GIMP (20-minute cap) vs pipeline wall-clock"],
          } as Row,
        ]
      : []),
  ];

  return (
    <div className="space-y-16">
      <section className="max-w-4xl">
        <p className="case-label">Case file · measurements</p>
        <h1 className="mt-3 font-serif text-5xl leading-[1.08] sm:text-6xl">The honest numbers</h1>
        <p className="mt-6 max-w-[56ch] text-xl leading-relaxed text-body">
          The map is a real warning signal, and the pipeline never touches undamaged pixels. Finding real
          damage on its own is still the weak link.
        </p>
      </section>

      <section>
        <h2 className="font-serif text-3xl">Results</h2>
        <div className="mt-6">
          <RecordTable caption="Results" columns={["Measure", "Result", "How we measured it"]} rows={results} />
        </div>
      </section>

      <section>
        <h2 className="font-serif text-3xl">Finding damage: synthetic vs. real</h2>
        <div className="mt-6">
          <IouChart
            bars={[
              { label: "Synthetic damage", value: n.syntheticIou },
              { label: "Real photos, before fine-tuning", value: n.realBefore },
              { label: "Real photos, after fine-tuning", value: n.realIou },
            ]}
          />
        </div>
      </section>

      <section className="max-w-4xl">
        <h2 className="font-serif text-3xl">Limitations</h2>
        <ul className="mt-6 list-disc space-y-4 pl-6 text-lg leading-relaxed text-body marker:text-muted">
          <li>
            <strong className="text-ink">The synthetic-to-real gap.</strong> The detector scored{" "}
            {n.syntheticIou.toFixed(2)} IoU on synthetic scratches and {iou3(n.realBefore)} on real scans; it
            had learned fake damage, not real damage. Fine-tuning on 15 hand-labeled real photos raised it to{" "}
            {n.realIou.toFixed(2)}. That's still low, so the app treats the mask as a proposal a person can fix.
          </li>
          <li>
            <strong className="text-ink">Disagreement is a signal, not a guarantee.</strong> The per-pixel
            correlation is modest (ρ = {n.spearman.toFixed(2)}). "Rebuilt" means the attempts agreed, not that
            it's correct.
          </li>
          <li>
            <strong className="text-ink">Thin cracks</strong> are the hardest damage to detect.
          </li>
          <li>
            <strong className="text-ink">CodeFormer</strong>, the face model, is licensed for non-commercial use
            only.
          </li>
          <li>
            <strong className="text-ink">Receipts use a test certificate</strong>, so viewers show them as
            untrusted.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="font-serif text-3xl">What we built vs. what we used</h2>
        <div className="mt-6">
          <RecordTable
            caption="What we built vs. what we used"
            columns={["Component", "Built or used", "Details"]}
            rows={BUILT_VS_USED}
          />
        </div>
      </section>
    </div>
  );
}
