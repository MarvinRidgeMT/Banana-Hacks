import { useId, useState, type ReactNode } from "react";
import { Swatch } from "../components/PhotoStage";
import { CLASSES, CLASS_LABEL, fidelityLabel } from "../lib/format";
import type { ClassName } from "../lib/types";
import { FIDELITY_STEPS } from "../lib/types";

const VERIFY_URL = "https://contentcredentials.org/verify";

const Code = ({ children }: { children: ReactNode }) => <span className="normal-case">{children}</span>;

const STAGES: { title: string; body: string; receipt: ReactNode }[] = [
  {
    title: "Find the damage",
    body:
      "A segmenter, fine-tuned on 15 hand-labeled real scans, proposes a mask of lost content. A person can correct it with the brush.",
    receipt: (
      <>
        Mask source (<Code>segmenter</Code>, <Code>human_file</Code> or <Code>human_brush</Code>)
      </>
    ),
  },
  {
    title: "Restore several times",
    body:
      "The damaged areas are inpainted with several random seeds (SDXL inpainting; OpenCV Telea for thin cracks). Pixels outside the mask are copied straight from the scan, so untouched areas can't change.",
    receipt: "Seeds",
  },
  {
    title: "Measure disagreement",
    body:
      "For each repaired pixel, measure how much the seeds disagree (in CIELAB color). Low spread is Rebuilt; high spread is Invented.",
    receipt: "Threshold and pixel counts",
  },
  {
    title: "Faces",
    body:
      "Damaged faces go through CodeFormer once per seed. Cold Case keeps the most different results as \u201cthe faces that could have been\u201d instead of picking one.",
    receipt: "Face regions and confidence",
  },
  {
    title: "Sign the receipt",
    body:
      "A manifest of inputs, mask source, seeds, settings and pixel counts is embedded in the restored PNG as a C2PA Content Credential.",
    receipt: "The signature",
  },
];

const LABEL_SENTENCE: Record<ClassName, string> = {
  observed: "Outside the damage mask, copied from the scan unchanged.",
  inferred: "Repaired, and every repair attempt came out about the same.",
  invented: "Repaired, but the attempts disagreed, so what you see is one guess among several. Always hatched, never colour alone.",
};

const FIDELITY_NOTE: Record<string, string> = {
  "0.3": "The face model fills in more from what faces usually look like.",
  "0.7": "The default; results open at this step.",
  "1": "Faces stay closest to the damaged original.",
};

const FAQ: { q: string; a: ReactNode }[] = [
  {
    q: "Is a Rebuilt pixel correct?",
    a: (
      <p>
        Not necessarily. It means the repair attempts agreed. On test photos with known originals, Invented areas
        were 1.8× further from the truth than Rebuilt ones, so the labels are a real warning signal, not a guarantee.
      </p>
    ),
  },
  {
    q: "Can it change parts of the photo that weren't damaged?",
    a: (
      <p>
        No. Pixels outside the mask are copied byte for byte. An automated test checks this, and every demo run
        reports 0 changed.
      </p>
    ),
  },
  {
    q: "Why can I edit the damage mask?",
    a: (
      <p>
        The detector still misses real damage, especially thin cracks (0.18 IoU on real photos). A person checks it,
        and the receipt records that they did.
      </p>
    ),
  },
  {
    q: "Why three faces instead of one?",
    a: <p>Where a face was invented, the attempts disagree. Showing one would hide that.</p>,
  },
  {
    q: "How do I check a receipt?",
    a: (
      <p>
        Download the signed PNG and open it in any C2PA viewer, such as{" "}
        <a href={VERIFY_URL} target="_blank" rel="noreferrer" className="underline underline-offset-4">
          contentcredentials.org/verify
        </a>
        .
      </p>
    ),
  },
  {
    q: "Where does my upload go?",
    a: (
      <>
        <p>
          To the server running Cold Case, which restores it there. The photo is turned upright, converted to PNG and
          saved in the server's cache folder, in a folder named after the photo's SHA-256 hash. Alongside it go a
          thumbnail, your mask if you drew one, and a short record of the filename, image size and upload time. The
          restorations are written to the same folder.
        </p>
        <p className="mt-3">
          Nothing in the code deletes uploads, and there are no accounts: anyone with the result link can open the
          files.
        </p>
      </>
    ),
  },
];

function FaqItem({ q, a }: { q: string; a: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <li className="border-b border-line">
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center justify-between gap-6 py-5 text-left text-lg font-semibold hover:text-body"
        >
          {q}
          <span aria-hidden className="font-mono text-2xl leading-none text-muted">
            {open ? "\u2212" : "+"}
          </span>
        </button>
      </h3>
      <div id={id} hidden={!open} className="max-w-[64ch] pb-6 text-body">
        {a}
      </div>
    </li>
  );
}

export function HowItWorks() {
  return (
    <div className="space-y-20">
      <section className="max-w-4xl">
        <p className="case-label">Case file · method</p>
        <h1 className="mt-3 font-serif text-5xl leading-[1.08] sm:text-6xl">How it works</h1>
        <p className="mt-6 max-w-[56ch] text-xl leading-relaxed text-body">
          A restorer that fills in lost detail has to say what it made up. Cold Case runs in five stages, and each one
          writes what it did into the receipt.
        </p>
      </section>

      <section aria-labelledby="pipeline">
        <h2 id="pipeline" className="font-serif text-3xl">
          The pipeline
        </h2>
        <ol className="mt-8 flex flex-col lg:flex-row">
          {STAGES.map((s, i) => (
            <li key={s.title} className="flex flex-col lg:flex-1 lg:flex-row">
              {i > 0 && (
                <span aria-hidden className="flex justify-center py-3 text-2xl text-muted lg:items-center lg:px-3 lg:py-0">
                  <span className="lg:hidden">↓</span>
                  <span className="hidden lg:inline">→</span>
                </span>
              )}
              <div className="flex flex-1 flex-col">
                <div className="flex-1 border border-line bg-surface p-5">
                  <p className="font-mono text-sm text-muted">{String(i + 1).padStart(2, "0")}</p>
                  <h3 className="mt-1 font-serif text-2xl leading-tight">{s.title}</h3>
                  <p className="mt-3 text-[0.9rem] leading-relaxed text-body">{s.body}</p>
                </div>
                <p className="mt-3">
                  <span className="tag">Receipt: {s.receipt}</span>
                </p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="label-map" className="max-w-4xl">
        <h2 id="label-map" className="font-serif text-3xl">
          Reading the label map
        </h2>
        <p className="mt-4 text-lg text-body">Every pixel of a restored photo gets one of three labels.</p>
        <dl className="mt-6 grid grid-cols-[auto_1fr] items-baseline gap-x-4 gap-y-4">
          {CLASSES.map((c) => (
            <div key={c} className="contents">
              <dt className="flex items-center gap-3 font-semibold">
                <Swatch cls={c} className="h-5 w-5 translate-y-0.5" />
                {CLASS_LABEL[c]}
              </dt>
              <dd className="text-body">{LABEL_SENTENCE[c]}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-6 text-lg">Point at any region to see its confidence and which stage changed it.</p>
      </section>

      <section aria-labelledby="fidelity" className="max-w-4xl">
        <h2 id="fidelity" className="font-serif text-3xl">
          Fidelity
        </h2>
        <p className="mt-4 text-lg text-body">
          Fidelity sets how closely restored faces stay to the damaged original, in three steps from &ldquo;restore
          more&rdquo; to &ldquo;preserve&rdquo;. Each step is its own restoration with its own label map, so the labels
          update with it.
        </p>
        <ol className="mt-6 grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-3">
          {FIDELITY_STEPS.map((f) => (
            <li key={f} className="bg-surface p-5">
              <p className="font-semibold">
                {fidelityLabel(f)}
                <span className="ml-2 font-mono text-sm font-normal text-muted">w = {f.toFixed(1)}</span>
              </p>
              <p className="mt-2 text-sm text-body">{FIDELITY_NOTE[String(f)]}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="receipt" className="max-w-4xl">
        <h2 id="receipt" className="font-serif text-3xl">
          The receipt
        </h2>
        <p className="mt-4 text-lg leading-relaxed text-body">
          Every restoration comes with a JSON record of every stage, setting, region and confidence. The same record is
          signed into the image as a C2PA Content Credential, so the labels travel with the file.
        </p>
        <p className="mt-6 flex flex-wrap items-center gap-4">
          <span className="stamp">Test certificate</span>
          <span className="text-body">It's signed with a test certificate, so viewers show it as untrusted.</span>
        </p>
      </section>

      <section aria-labelledby="faq" className="max-w-4xl">
        <h2 id="faq" className="font-serif text-3xl">
          Questions
        </h2>
        <ul className="mt-4 border-t border-line">
          {FAQ.map((item) => (
            <FaqItem key={item.q} {...item} />
          ))}
        </ul>
      </section>
    </div>
  );
}
