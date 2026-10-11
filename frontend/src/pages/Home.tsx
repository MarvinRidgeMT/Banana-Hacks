import { useEffect, useState, type ReactNode } from "react";
import { DemoCredit } from "../components/DemoCredit";
import { ExplodedView } from "../components/ExplodedView";
import { TrueFaceExhibit } from "../components/TrueFaceExhibit";
import { DemoCardSkeleton, ErrorNote } from "../components/Feedback";
import { Link } from "../components/Link";
import { PhotoStage, Swatch } from "../components/PhotoStage";
import { api, fileUrl } from "../lib/api";
import { CLASSES, CLASS_LABEL, CLASS_MEANING } from "../lib/format";
import { href } from "../lib/router";
import type { Demo, Result } from "../lib/types";
import { DEFAULT_FIDELITY } from "../lib/types";

interface Props {
  demos: Demo[] | null;
  demosError: string | null;
  onRetryDemos: () => void;
}

const PRIMARY =
  "inline-block rounded-sm bg-ink px-6 py-3 text-lg font-semibold text-ground hover:bg-ink/85";
const SECONDARY =
  "inline-block rounded-sm border border-ink px-6 py-3 text-lg font-semibold hover:bg-tag";

const QUOTES: { text: string; quoted: boolean; source: string; url: string }[] = [
  {
    text: "generated a new, convincing-but-fake person",
    quoted: true,
    source: "Santa Barbara County Genealogical Society, republishing genealogist Steve Little",
    url: "https://sbgen.org/ai-does-not-restore-or-repair-photos/",
  },
  {
    text: "AI tools used for \u2018photo restoration\u2019 often fabricate facial features",
    quoted: true,
    source: "BYU Family History Library",
    url: "https://familyhistory.lib.byu.edu/virtual-classes/ai-image-generation-vs-protecting-trust-in-historical-images",
  },
  {
    text: "The head of Indonesia\u2019s National Archives warned in August 2026 that AI-polished archival photos can amount to falsification, and that records must stay as originally created.",
    quoted: false,
    source: "Paraphrased from RRI Voice of Indonesia",
    url: "https://rri.co.id/voice-of-indonesia/education/2685199/national-archives-warn-against-ai-altered-historical-records",
  },
];

const STEPS: { title: string; text: string }[] = [
  {
    title: "Find the damage",
    text: "A trained segmenter marks scratches, tears and missing emulsion, and you can correct its mask with a brush.",
  },
  {
    title: "Restore several times",
    text: "Each damaged area is filled four times by diffusion inpainting, each run with a different random seed.",
  },
  {
    title: "Measure disagreement",
    text: "Where the runs agree a pixel is Rebuilt, where they differ it is Invented, and untouched pixels stay Real.",
  },
  {
    title: "Faces",
    text: "Damaged faces go through CodeFormer on every run, and the alternative faces are kept so you can compare them.",
  },
  {
    title: "Sign the receipt",
    text: "Every step, model and label count is written into a C2PA manifest and signed inside the image file.",
  },
];

const NUMBERS: { value: string; label: string }[] = [
  { value: "0.90 \u2192 0.18", label: "detector IoU, synthetic \u2192 real" },
  { value: "1.8\u00d7", label: "further from the truth where it says Invented" },
  { value: "0", label: "untouched pixels changed" },
  { value: "Valid", label: "C2PA receipt" },
];

export function Home({ demos, demosError, onRetryDemos }: Props) {
  const hero = demos?.find((d) => d.id === "hero") ?? demos?.[0] ?? null;
  const heroResult = useResult(hero?.key);
  const caseHref = hero ? href.result(hero.key, DEFAULT_FIDELITY) : href.restore;
  // The exploded view needs a case with real invention: the simulated-face demo if present.
  const apart = demos?.find((d) => d.id === "face_missing") ?? demos?.find((d) => d.id === "backup") ?? hero;
  const apartResult = useResult(apart?.key);

  return (
    <div className="space-y-24 sm:space-y-32">
      {/* 1. Hero */}
      <section className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center">
        <div>
          <p className="tag">Case file · photo restoration</p>
          <h1 className="mt-5 font-serif text-5xl leading-[1.05] sm:text-6xl xl:text-7xl">
            Old photos, restored. Every guess on the record.
          </h1>
          <p className="mt-6 max-w-[54ch] text-xl leading-relaxed text-body">
            AI photo restorers don't recover lost detail; they invent it, and never say where. Cold Case
            repairs damaged historical photos and labels every pixel Real, Rebuilt or Invented, with a
            signed receipt inside the file.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link to={href.restore} className={PRIMARY}>
              Restore a photo
            </Link>
            <Link to={caseHref} className={SECONDARY}>
              See a case
            </Link>
          </div>
        </div>
        <HeroExhibit hero={hero} heroResult={heroResult} demos={demos} demosError={demosError} />
      </section>

      {/* 1b. Take it apart: the exploded evidence stack */}
      {apartResult && <ExplodedView result={apartResult} />}

      {/* 1c. The answer key: true face vs the AI's three guesses */}
      <TrueFaceExhibit />

      {/* 2. The problem */}
      <section>
        <SectionHead label="The problem">A plausible face is not the original</SectionHead>
        <p className="mt-6 max-w-[62ch] text-xl leading-relaxed text-body">
          When a damaged photo is missing part of a face, AI restorers fill the gap with a plausible face
          and present it as the original. For a family album that is a curiosity; for a public archive it
          is a falsified record.
        </p>
        <ul className="mt-12 grid gap-6 lg:grid-cols-3">
          {QUOTES.map((q) => (
            <li key={q.url}>
              <figure className="flex h-full flex-col justify-between gap-6 border-l-4 border-invented bg-surface p-6 sm:p-8">
                {q.quoted ? (
                  <blockquote cite={q.url} className="font-serif text-2xl leading-snug">
                    &ldquo;{q.text}&rdquo;
                  </blockquote>
                ) : (
                  <p className="text-lg leading-relaxed text-ink">{q.text}</p>
                )}
                <figcaption className="text-sm text-muted">
                  <a href={q.url} target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-ink">
                    {q.source}
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                  <span aria-hidden> ↗</span>
                </figcaption>
              </figure>
            </li>
          ))}
        </ul>
        <div className="mt-16 border-y border-line py-12 sm:py-16">
          <p className="font-serif text-6xl leading-none sm:text-8xl">21,588</p>
          <p className="mt-4 font-serif text-2xl sm:text-3xl">history organizations in the US alone</p>
          <p className="case-label mt-3">Source: AASLH 2022 census</p>
          <p className="mt-10 max-w-[40ch] text-xl text-body">
            Once an invented face is published, it becomes history.
          </p>
        </div>
      </section>

      {/* 3. Three labels */}
      <section>
        <SectionHead label="Three labels">Every pixel is one of three things</SectionHead>
        <ul className="mt-10 grid gap-6 md:grid-cols-3">
          {CLASSES.map((c) => (
            <li key={c} className="bg-surface p-6 sm:p-8">
              <Swatch cls={c} className="h-12 w-12" />
              <p className="mt-5 font-serif text-3xl">{CLASS_LABEL[c]}</p>
              <p className="mt-2 text-lg text-body">{CLASS_MEANING[c]}</p>
            </li>
          ))}
        </ul>
        <p className="mt-8 text-lg text-body">Rebuilt means the attempts agreed, not that they're right.</p>
      </section>

      {/* 4. One photo, three faces */}
      <section>
        <p className="tag">The faces</p>
        <p className="mt-5 font-serif text-4xl leading-tight sm:text-5xl">
          One photo. <span className="text-invented">Three faces.</span>
        </p>
        <p className="mt-3 text-xl text-body">The AI was equally sure of all three.</p>
        {heroResult && heroResult.faces.length > 0 && (
          <ul className="mt-10 flex flex-wrap gap-8">
            {heroResult.faces.slice(0, 3).map((f, i) => (
              <li key={f.file}>
                <img
                  src={fileUrl(heroResult.key, f.file)}
                  alt={`Possible face ${i + 1}`}
                  crossOrigin="anonymous"
                  className="exhibit-frame h-32 w-auto object-contain sm:h-44"
                />
              </li>
            ))}
          </ul>
        )}
        {hero && (
          <Link to={caseHref} className="mt-8 inline-block text-lg underline underline-offset-4 hover:text-body">
            See the three faces in {hero.title}
          </Link>
        )}
      </section>

      {/* 5. How it works */}
      <section>
        <SectionHead label="How it works">Five steps, all on the record</SectionHead>
        <ol className="mt-10 grid gap-6 sm:grid-cols-2 xl:grid-cols-5">
          {STEPS.map((s, i) => (
            <li key={s.title} className="border-t-2 border-ink pt-5">
              <p className="case-label">Step {String(i + 1).padStart(2, "0")}</p>
              <p className="mt-2 font-serif text-2xl">{s.title}</p>
              <p className="mt-2 text-body">{s.text}</p>
            </li>
          ))}
        </ol>
        <Link to={href.howItWorks} className="mt-10 inline-block text-lg underline underline-offset-4 hover:text-body">
          Read how it works
        </Link>
      </section>

      {/* 6. Cases */}
      <section>
        <SectionHead label="Cases">Open a case</SectionHead>
        {demosError && <ErrorNote message={demosError} onRetry={onRetryDemos} className="mt-6" />}
        {!demos && !demosError && (
          <ul className="mt-10 grid grid-cols-1 gap-x-8 gap-y-14 sm:grid-cols-2 xl:grid-cols-4" aria-label="Loading the cases">
            {[0, 1, 2, 3].map((i) => (
              <li key={i}>
                <DemoCardSkeleton />
              </li>
            ))}
          </ul>
        )}
        {demos?.length === 0 && <p className="mt-6 text-muted">No demo photos on the server yet.</p>}
        <ul className="mt-10 grid grid-cols-1 gap-x-8 gap-y-14 sm:grid-cols-2 xl:grid-cols-4">
          {(demos ?? []).map((d) => (
            <li key={d.id}>
              <Link to={href.result(d.key, DEFAULT_FIDELITY)} className="group block" aria-label={`Open the case ${d.title}`}>
                <div className="exhibit-frame aspect-[4/5]">
                  <img
                    src={fileUrl(d.key, d.thumb)}
                    alt=""
                    crossOrigin="anonymous"
                    className="h-full w-full object-contain group-hover:opacity-85"
                  />
                </div>
                <p className="case-label mt-7">Case {d.key.slice(0, 8)}</p>
                <p className="mt-1 font-serif text-2xl group-hover:underline">{d.title}</p>
              </Link>
              <DemoCredit demo={d} className="mt-2" />
            </li>
          ))}
        </ul>
      </section>

      {/* 7. Numbers */}
      <section className="on-dark bg-mat px-6 py-12 text-ground sm:px-12 sm:py-16">
        <p className="tag">The numbers</p>
        <ul className="mt-10 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          {NUMBERS.map((n) => (
            <li key={n.label}>
              <p className="font-serif text-4xl sm:text-5xl">{n.value}</p>
              <p className="mt-2 text-lg text-ground/80">{n.label}</p>
            </li>
          ))}
        </ul>
        <Link to={href.evidence} className="mt-12 inline-block text-lg underline underline-offset-4 hover:text-tag">
          See the evidence behind these numbers
        </Link>
      </section>

      {/* 8. Call to action */}
      <section className="py-8 text-center">
        <span className="stamp text-lg">Open case</span>
        <h2 className="mx-auto mt-8 max-w-[18ch] font-serif text-4xl leading-tight sm:text-6xl">
          Got a damaged photo? See what's real.
        </h2>
        <Link to={href.restore} className={`mt-10 ${PRIMARY}`}>
          Restore a photo
        </Link>
      </section>
    </div>
  );
}

function SectionHead({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <p className="tag">{label}</p>
      <h2 className="mt-5 font-serif text-4xl leading-tight sm:text-5xl">{children}</h2>
    </>
  );
}

/** The cached result at the default fidelity: undefined while loading, null if
 * it isn't ready (202) or didn't load. Never starts a restore job. */
function useResult(key: string | undefined): Result | null | undefined {
  const [state, setState] = useState<{ key: string; result: Result | null } | null>(null);
  useEffect(() => {
    if (!key) return;
    let live = true;
    api
      .result(key, DEFAULT_FIDELITY)
      .then((result) => live && setState({ key, result }))
      .catch(() => live && setState({ key, result: null }));
    return () => {
      live = false;
    };
  }, [key]);
  return state && state.key === key ? state.result : undefined;
}

function HeroExhibit({
  hero,
  heroResult,
  demos,
  demosError,
}: {
  hero: Demo | null;
  heroResult: Result | null | undefined;
  demos: Demo[] | null;
  demosError: string | null;
}) {
  const [thumbFailed, setThumbFailed] = useState(false);
  const [showLabels, setShowLabels] = useState(false);

  if (heroResult) {
    return (
      <figure>
        <PhotoStage result={heroResult} showMap={showLabels} opacity={0.75} onHover={() => {}} />
        <figcaption className="mt-8 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-body">
              Drag the handle to compare the damaged scan with the {showLabels ? "labelled " : ""}restoration.
            </p>
            <button
              type="button"
              aria-pressed={showLabels}
              onClick={() => setShowLabels((v) => !v)}
              className={`rounded-sm border px-4 py-2 font-semibold ${
                showLabels ? "border-ink bg-ink text-ground" : "border-line bg-surface hover:bg-tag"
              }`}
            >
              {showLabels ? "Hide the labels" : "Show what was invented"}
            </button>
          </div>
          <ul className={`flex flex-wrap gap-x-6 gap-y-2 ${showLabels ? "" : "opacity-50"}`}>
            {CLASSES.map((c) => (
              <li key={c} className="flex items-center gap-2">
                <Swatch cls={c} />
                {CLASS_LABEL[c]}
              </li>
            ))}
          </ul>
        </figcaption>
      </figure>
    );
  }

  if (hero && !thumbFailed) {
    return (
      <figure>
        <div className="exhibit-frame relative mx-auto aspect-[4/5] w-full max-w-md">
          <img
            src={fileUrl(hero.key, hero.thumb)}
            alt={`${hero.title}, the original scan`}
            crossOrigin="anonymous"
            onError={() => setThumbFailed(true)}
            className="h-full w-full object-contain"
          />
          <span className="tag absolute left-3 top-3">Original scan</span>
        </div>
        <figcaption className="mx-auto mt-8 max-w-md text-body">
          {heroResult === undefined
            ? `${hero.title}. Loading the labels…`
            : `${hero.title}. The labelled restoration isn't ready yet; it will appear on the case page.`}
        </figcaption>
      </figure>
    );
  }

  const message = demosError || thumbFailed || demos?.length === 0
    ? "The demo photo isn't available right now. You can still restore one of your own."
    : "Loading the case file…";
  return (
    <div className="exhibit-frame mx-auto grid aspect-[4/5] w-full max-w-md place-items-center p-8 text-center text-ground">
      <div>
        <span className="stamp text-xl">Cold Case</span>
        <p className="mt-6 text-lg">{message}</p>
        <ul className="mt-6 space-y-2 text-left">
          {CLASSES.map((c) => (
            <li key={c} className="flex items-center gap-3">
              <Swatch cls={c} />
              <span className="font-semibold">{CLASS_LABEL[c]}</span>
              <span className="text-sm text-ground/75">{CLASS_MEANING[c]}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
