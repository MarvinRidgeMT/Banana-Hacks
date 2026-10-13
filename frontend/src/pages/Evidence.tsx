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

/** Real damage, measured on 40 real damaged photos with expert masks (ARTeFACT) that no model was
 * trained on. From runs/v7_report.json. */
const REAL_40 = [
  { label: "v5: trained on synthetic damage only", iou: 0.034, recall: 0.034, precision: 0.801 },
  { label: "v5 + Microsoft scratch detector", iou: 0.281, recall: 0.363, precision: 0.555 },
  { label: "v7: fine-tuned on 90 real damaged photos", iou: 0.377, recall: 0.432, precision: 0.747 },
  { label: "v7 + Microsoft scratch detector (live)", iou: 0.426, recall: 0.606, precision: 0.59 },
];
const pct = (v: number) => `${Math.round(v * 100)}%`;


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

function IouChart({ bars, title = "Damage detector IoU" }: { bars: { label: string; value: number }[]; title?: string }) {
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
        aria-label={`${title}: ${bars.map((b) => `${b.label} ${iou3(b.value)}`).join("; ")}.`}
      >
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
      <figcaption className="mt-4 text-sm text-muted">{title}. 1.00 is perfect.</figcaption>
    </figure>
  );
}

const BUILT_VS_USED: Row[] = [
  {
    key: "segmenter",
    cells: [
      "Damage segmenter",
      "Built (trained this weekend)",
      "U-Net with a ResNet-34 encoder; our procedural damage generator on 617 Library of Congress photos; fine-tuned on 90 real damaged photos (ARTeFACT)",
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
  {
    key: "ms",
    cells: ["Scratch detector", "Used", "Microsoft, Bringing Old Photos Back to Life (Wan et al., CVPR 2020), MIT licence; its mask is combined with ours"],
  },
  {
    key: "artefact",
    cells: ["ARTeFACT dataset", "Used", "Real damaged photos and documents with expert masks (Ivanova et al., 2024): 90 to train, 40 held out to test"],
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

  const results: Row[] = [
    {
      key: "synthetic",
      cells: ["Damage detection, synthetic photos", `IoU ${iou3(n.syntheticIou)}`, n.syntheticNote],
    },
    {
      key: "real",
      cells: [
        "Damage detection, real photos",
        "Finds 61% of the damage (IoU 0.426); 3% before",
        "40 real damaged photos with expert masks (ARTeFACT dataset) that were never used for training. Live setup: our v7 detector, fine-tuned on 90 other ARTeFACT photos, combined with Microsoft's old-photo scratch detector. 59% of what it flags is real damage; a person reviews every mask.",
      ],
    },
    {
      key: "recall-levels",
      cells: [
        "Catching more damage (mask editor)",
        "Standard 68% · More 83% · Most 90% found",
        "A person can ask for more: a lower cutoff and a wider mask. Picked on 20 unseen real photos, scored on 20 others. The cost is a bigger mask (1.2x, 2.1x, 3.5x the true damage area), and every masked pixel is regenerated and labelled, so we keep Standard as the default.",
      ],
    },
    {
      key: "real-demos",
      cells: [
        "Damage detection, our demo scans",
        "IoU 0.345 (v7) vs 0.062 (v5)",
        "Our 5 demo photos with hand-painted masks: a different source from the training photos, so not just memorising one collection. Small sample.",
      ],
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
        "Documents: finding real damage",
        "Finds 55% of the damage (IoU 0.467); 16% before",
        "46 real damaged documents (manuscripts, maps, letters, prints; ARTeFACT) held out from training. Doc v2 was fine-tuned on 106 others plus 800 synthetic pages. The cost: on synthetic pages where the ink is known, writing wrongly flagged went from 0.18% to 0.23%, and synthetic-damage IoU from 0.914 to 0.835. No model ever generates text.",
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
        <h2 className="font-serif text-3xl">Finding real damage</h2>
        <p className="mt-3 max-w-[60ch] text-body">
          On 40 real damaged photos the models never saw. Share of the true damage found, and overlap (IoU)
          with the expert mask.
        </p>
        <div className="mt-6 grid gap-10 lg:grid-cols-2">
          <IouChart bars={REAL_40.map((r) => ({ label: r.label, value: r.recall }))} title="Share of real damage found" />
          <IouChart bars={REAL_40.map((r) => ({ label: r.label, value: r.iou }))} title="Overlap with the expert mask (IoU)" />
        </div>
      </section>

      <section className="max-w-4xl">
        <h2 className="font-serif text-3xl">Limitations</h2>
        <ul className="mt-6 list-disc space-y-4 pl-6 text-lg leading-relaxed text-body marker:text-muted">
          <li>
            <strong className="text-ink">Finding real damage is still the weakest step.</strong> A detector
            trained on synthetic damage found only 3% of real damage. Real expert-labeled photos and Microsoft's
            scratch detector raised that to {pct(REAL_40[3].recall)}, but about 4 in 10 real damaged pixels are
            still missed, so the mask is a proposal: a person reviews it, and can click a missed crack to add
            all of it.
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
