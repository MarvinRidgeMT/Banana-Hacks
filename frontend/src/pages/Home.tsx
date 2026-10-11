import { useEffect, useRef, useState } from "react";
import { Comparison } from "../components/Comparison";
import { DemoCredit } from "../components/DemoCredit";
import { ExplodedView } from "../components/ExplodedView";
import { DemoCardSkeleton, ErrorNote } from "../components/Feedback";
import { HeroScanner } from "../components/HeroScanner";
import { Link } from "../components/Link";
import { TrueFaceExhibit } from "../components/TrueFaceExhibit";
import { YourCases } from "../components/YourCases";
import { api, fileUrl } from "../lib/api";
import { href } from "../lib/router";
import type { ColorResult, Demo, Result, Summary } from "../lib/types";
import { DEFAULT_FIDELITY } from "../lib/types";

interface Props {
  demos: Demo[] | null;
  demosError: string | null;
  onRetryDemos: () => void;
}

const PRIMARY_DARK =
  "inline-flex items-center gap-3 rounded-full bg-ground px-7 py-3.5 text-lg font-semibold text-ink transition hover:bg-surface hover:shadow-[0_0_40px_rgba(241,234,219,0.35)]";
const SECONDARY_DARK =
  "inline-flex items-center gap-3 rounded-full border border-ground/40 px-7 py-3.5 text-lg font-semibold text-ground transition hover:border-ground hover:bg-ground/10";

const LEAD_QUOTE = {
  text: "generated a new, convincing-but-fake person",
  source: "Santa Barbara County Genealogical Society, republishing genealogist Steve Little",
  url: "https://sbgen.org/ai-does-not-restore-or-repair-photos/",
};
const MORE_QUOTES = [
  {
    text: "“AI tools used for ‘photo restoration’ often fabricate facial features”",
    source: "BYU Family History Library",
    url: "https://familyhistory.lib.byu.edu/virtual-classes/ai-image-generation-vs-protecting-trust-in-historical-images",
  },
  {
    text: "Indonesia’s National Archives warned in August 2026 that AI-polished archival photos can amount to falsification.",
    source: "Paraphrased from RRI Voice of Indonesia",
    url: "https://rri.co.id/voice-of-indonesia/education/2685199/national-archives-warn-against-ai-altered-historical-records",
  },
];

/** Measured results only; every one is on the Evidence page. */
const TICKER = [
  "0 untouched pixels changed",
  "Invented pixels sit 1.8× further from the truth",
  "8 independent restorations per photo",
  "C2PA receipt signed inside every file",
  "Documents: 0 letters generated",
  "Color: brightness kept within 0.1 / 100",
  "Damage detector trained by us",
  "Faces: every alternative kept",
];

const PIPELINE = ["Detect damage", "Restore × 8 seeds", "Measure disagreement", "Label every pixel", "Sign the receipt"];

export function Home({ demos, demosError, onRetryDemos }: Props) {
  const hero = demos?.find((d) => d.id === "face_missing") ?? demos?.[0] ?? null;
  const heroResult = useResult(hero?.key);
  const caseHref = hero ? href.result(hero.key, DEFAULT_FIDELITY) : href.restore;
  const photoCase = demos?.find((d) => d.id === "backup") ?? hero;
  const docCase = demos?.find((d) => d.kind === "document") ?? null;
  const colorCase = demos?.find((d) => d.id === "inferred") ?? null;

  return (
    <div className="-mt-12">
      {/* 1. HERO: the examination table */}
      <section className="bleed desk on-dark hero-grid relative overflow-hidden">
        <div aria-hidden className="hero-glow" />
        <div className="relative mx-auto grid max-w-[110rem] items-center gap-14 px-6 pb-20 pt-12 sm:px-10 lg:grid-cols-[minmax(0,6fr)_minmax(0,6fr)] lg:pb-24 lg:pt-14">
          <div>
            <p className="readout flex items-center gap-3 text-xs text-ground/60">
              <span className="live-dot" aria-hidden />
              Forensic photo restoration · Banana Hacks 2026
            </p>
            <h1 className="display mt-6 text-[clamp(3rem,6vw,6.4rem)]">
              Every pixel
              <br />
              gets a verdict.
            </h1>
            <ul className="mt-8 flex flex-wrap gap-3" aria-label="The three labels">
              <Verdict cls="observed" label="Real" pct={heroResult?.pixel_summary.observed} />
              <Verdict cls="inferred" label="Rebuilt" pct={heroResult?.pixel_summary.inferred} />
              <Verdict cls="invented" label="Invented" pct={heroResult?.pixel_summary.invented} />
            </ul>
            <p className="mt-7 max-w-[44ch] text-xl leading-relaxed text-ground/80">
              AI photo restorers invent what was lost and never say where. Cold Case restores damaged historical
              photos and documents, labels every pixel, and signs the record into the file.
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <Link to={href.restore} className={PRIMARY_DARK}>
                Restore a photo <span aria-hidden>→</span>
              </Link>
              <Link to={caseHref} className={SECONDARY_DARK}>
                Open this case
              </Link>
            </div>
          </div>
          <div className="relative">
            {heroResult ? (
              <HeroScanner result={heroResult} />
            ) : (
              <HeroFallback hero={hero} loading={heroResult === undefined && !demosError} />
            )}
          </div>
        </div>
        <a href="#problem" className="scroll-cue readout" aria-label="Scroll to the problem">
          Scroll
        </a>
      </section>

      {/* 2. Proof ticker */}
      <div className="bleed ticker" aria-label="Measured results">
        <div className="ticker-track">
          {[0, 1].map((copy) => (
            <ul key={copy} className="ticker-row" aria-hidden={copy === 1}>
              {TICKER.map((t) => (
                <li key={t}>
                  <span className="ticker-mark" aria-hidden>
                    ◆
                  </span>
                  {t}
                </li>
              ))}
            </ul>
          ))}
        </div>
      </div>

      <div className="mt-24 space-y-28 sm:mt-32 sm:space-y-36">
        {/* 3. The problem, in one line */}
        <section id="problem" className="scroll-mt-24">
          <p className="tag">The problem</p>
          <figure className="mt-8">
            <blockquote cite={LEAD_QUOTE.url} className="display max-w-[18ch] text-[clamp(2.8rem,6vw,6rem)]">
              AI &ldquo;restoration&rdquo; <span className="strike-red">{LEAD_QUOTE.text}</span>.
            </blockquote>
            <figcaption className="mt-6 text-muted">
              Quoting{" "}
              <a href={LEAD_QUOTE.url} target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-ink">
                {LEAD_QUOTE.source}
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            </figcaption>
          </figure>
          <div className="mt-14 grid gap-10 border-t border-line pt-10 md:grid-cols-3">
            <div>
              <p className="font-serif text-6xl leading-none">
                <CountUp text="21,588" />
              </p>
              <p className="mt-3 text-body">history organizations in the US alone hold photos like these (AASLH 2022)</p>
            </div>
            {MORE_QUOTES.map((q) => (
              <div key={q.url}>
                <p className="text-lg leading-relaxed">{q.text}</p>
                <a href={q.url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm text-muted underline underline-offset-4 hover:text-ink">
                  {q.source}
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
              </div>
            ))}
          </div>
        </section>

        {/* 4. The answer key */}
        <TrueFaceExhibit />

        {/* 5. Take it apart */}
        {heroResult && <ExplodedView result={heroResult} />}

        {/* 6. Three kinds of evidence */}
        <section>
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <p className="tag">What it handles</p>
              <h2 className="mt-5 font-serif text-4xl leading-tight sm:text-6xl">
                Photos, documents, color.
                <br />
                <span className="text-invented">Same honesty.</span>
              </h2>
            </div>
            <ol className="pipeline readout" aria-label="The pipeline">
              {PIPELINE.map((s, i) => (
                <li key={s}>
                  <span className="text-faint">{String(i + 1).padStart(2, "0")}</span> {s}
                </li>
              ))}
            </ol>
          </div>
          <div className="mt-12 grid gap-8 lg:grid-cols-3">
            <ModeCard
              demo={photoCase}
              eyebrow="Photo mode"
              title="Restored, then labeled"
              text="Our detector finds the damage, diffusion restores it 8 times, and where the attempts disagree the pixels are marked Invented."
              before={photoCase ? "f070/original.png" : null}
              after={photoCase ? "f070/restored.png" : null}
              overlay={photoCase ? "f070/map.png" : null}
              stat={useSummaryStat(photoCase?.key)}
            />
            <ModeCard
              demo={docCase}
              eyebrow="Document mode"
              title="Paper repaired, words never written"
              text="No diffusion model touches a document. Gaps are filled from the paper around them, and any gap that touched writing is flagged as lost text."
              before={docCase ? "f070/original.png" : null}
              after={docCase ? "f070/restored.png" : null}
              overlay={docCase ? "f070/map.png" : null}
              stat="0 letters generated"
            />
            <ModeCard
              demo={colorCase}
              eyebrow="Color mode"
              title="Color, marked as a guess"
              text="A black-and-white photo holds no color. Two color models paint it; where they disagree, the color is labeled a guess. Brightness stays the scan's own."
              before={colorCase ? "f070/restored.png" : null}
              after={colorCase ? "f070/color/colorized.png" : null}
              overlay={colorCase ? "f070/color/map.png" : null}
              stat={useColorStat(colorCase?.key)}
            />
          </div>
          <Link to={href.howItWorks} className="mt-10 inline-block text-lg underline underline-offset-4 hover:text-body">
            Read how it works
          </Link>
        </section>

        {/* Returning visitors: their own cases */}
        <YourCases limit={5} />

        {/* 7. Typical restorer vs Cold Case */}
        <Comparison />

        {/* 8. Cases */}
        <section className="bleed desk on-dark hero-grid">
          <div className="mx-auto max-w-[110rem] px-6 py-20 sm:px-10 sm:py-24">
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div>
                <p className="readout text-xs text-ground/60">Case files · all public domain</p>
                <h2 className="mt-4 font-serif text-4xl leading-tight sm:text-6xl">Open a case</h2>
              </div>
              <p className="max-w-[48ch] text-ground/70">
                Portraits, crowds, glass plates and handwritten documents. Every case is a real restoration with its
                labels, alternatives and signed receipt.
              </p>
            </div>
            {demosError && <ErrorNote message={demosError} onRetry={onRetryDemos} className="mt-8" />}
            {!demos && !demosError && (
              <ul className="mt-12 grid grid-cols-2 gap-6 lg:grid-cols-4" aria-label="Loading the cases">
                {[0, 1, 2, 3].map((i) => (
                  <li key={i}>
                    <DemoCardSkeleton />
                  </li>
                ))}
              </ul>
            )}
            {demos?.length === 0 && <p className="mt-8 text-ground/70">No demo photos on the server yet.</p>}
            <ul className="mt-12 grid grid-cols-1 gap-x-6 gap-y-12 sm:grid-cols-2 lg:grid-cols-4">
              {(demos ?? []).map((d, i) => (
                <li key={d.id}>
                  <Link to={href.result(d.key, DEFAULT_FIDELITY)} className="group block" aria-label={`Open the case ${d.title}`}>
                    <div className="case-card relative aspect-[4/5] overflow-hidden">
                      <img
                        src={fileUrl(d.key, d.thumb)}
                        alt=""
                        crossOrigin="anonymous"
                        className="h-full w-full object-contain p-4 transition duration-500 group-hover:scale-[1.03]"
                      />
                      <span className="readout absolute left-3 top-3 text-[0.65rem] text-ground/60">
                        No. {String(i + 1).padStart(3, "0")}
                      </span>
                      {d.kind === "document" && <span className="scanner-chip bottom-3 left-3">Document</span>}
                    </div>
                    <p className="mt-4 text-lg font-semibold leading-snug text-ground group-hover:underline">
                      {d.title.replace(/^Document: /, "")}
                    </p>
                  </Link>
                  <DemoCredit demo={d} className="mt-1 !text-ground/55 [&_a]:!text-ground/55" />
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 9. The way in */}
        <section className="pb-8 text-center">
          <p className="readout text-xs text-muted">Free · open source · every result signed</p>
          <h2 className="display mx-auto mt-6 max-w-[20ch] text-[clamp(3rem,7vw,7rem)]">
            Got a damaged photo? <span className="text-invented">See what's real.</span>
          </h2>
          <div className="mt-12 flex flex-wrap justify-center gap-4">
            <Link
              to={href.restore}
              className="inline-flex items-center gap-3 rounded-full bg-ink px-8 py-4 text-xl font-semibold text-ground transition hover:bg-ink/85"
            >
              Restore a photo <span aria-hidden>→</span>
            </Link>
            <Link to={href.evidence} className="inline-flex items-center rounded-full border border-ink/30 px-8 py-4 text-xl font-semibold hover:bg-tag">
              See the evidence
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}

function Verdict({ cls, label, pct }: { cls: keyof Summary; label: string; pct?: number }) {
  return (
    <li className={`verdict verdict-${cls}`}>
      <span className="verdict-swatch" aria-hidden />
      <span className="font-semibold">{label}</span>
      <span className="readout tabular-nums text-ground/70">
        {pct === undefined ? "··.·%" : `${(pct * 100).toFixed(1)}%`}
      </span>
    </li>
  );
}

/** A before/after card that wipes back and forth on its own, with the label map on hover. */
function ModeCard(props: {
  demo: Demo | null;
  eyebrow: string;
  title: string;
  text: string;
  before: string | null;
  after: string | null;
  overlay: string | null;
  stat: string | null;
}) {
  const { demo, eyebrow, title, text, before, after, overlay, stat } = props;
  const [showMap, setShowMap] = useState(false);
  const body = (
    <>
      <div
        className="mode-stage relative aspect-square overflow-hidden bg-mat"
        onMouseEnter={() => setShowMap(true)}
        onMouseLeave={() => setShowMap(false)}
      >
        {demo && before && after ? (
          <>
            <img src={fileUrl(demo.key, after)} alt="" crossOrigin="anonymous" className="absolute inset-0 h-full w-full object-contain" />
            <img src={fileUrl(demo.key, before)} alt="" crossOrigin="anonymous" className="wipe absolute inset-0 h-full w-full object-contain" />
            <span aria-hidden className="wipe-line" />
            {overlay && (
              <img
                src={fileUrl(demo.key, overlay)}
                alt=""
                crossOrigin="anonymous"
                className="absolute inset-0 h-full w-full object-contain transition-opacity duration-300"
                style={{ opacity: showMap ? 0.8 : 0 }}
              />
            )}

            <span className="readout absolute left-3 top-3 text-[0.65rem] text-ground/70">Before</span>
            <span className="readout absolute right-3 top-3 text-[0.65rem] text-ground/70">
              {showMap ? "After + labels" : "After"}
            </span>
          </>
        ) : (
          <span className="absolute inset-0 animate-pulse bg-ground/5" />
        )}
      </div>
      <div className="p-6">
        <p className="readout text-xs text-muted">{eyebrow}</p>
        <h3 className="mt-2 font-serif text-3xl leading-tight">{title}</h3>
        <p className="mt-3 text-body">{text}</p>
        {stat && <p className="readout mt-5 inline-block bg-tag px-2 py-1 text-xs text-ink">{stat}</p>}
      </div>
    </>
  );
  return demo ? (
    <Link to={href.result(demo.key, DEFAULT_FIDELITY)} className="mode-card group block" aria-label={`${eyebrow}: open the case`}>
      {body}
    </Link>
  ) : (
    <div className="mode-card">{body}</div>
  );
}

function useSummaryStat(key: string | undefined): string | null {
  const r = useResult(key);
  if (!r) return null;
  const s = r.pixel_summary;
  return `${(s.observed * 100).toFixed(1)}% real · ${(s.inferred * 100).toFixed(1)}% rebuilt · ${(s.invented * 100).toFixed(1)}% invented`;
}

function useColorStat(key: string | undefined): string | null {
  const [c, setC] = useState<ColorResult | null>(null);
  useEffect(() => {
    if (!key) return;
    let live = true;
    fetch(fileUrl(key, "f070/color/color.json"))
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => live && setC(j))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [key]);
  if (!c) return null;
  return `0% real color · ${(c.pixel_summary.invented * 100).toFixed(0)}% marked a guess`;
}

function HeroFallback({ hero, loading }: { hero: Demo | null; loading: boolean }) {
  return (
    <div className="lightbox mx-auto grid aspect-[4/5] w-full max-w-lg place-items-center overflow-hidden">
      {hero ? (
        <img src={fileUrl(hero.key, hero.thumb)} alt="" crossOrigin="anonymous" className="h-full w-full object-contain opacity-70" />
      ) : (
        <p className="p-8 text-center text-ink">
          {loading ? "Laying out the case…" : "The demo case isn't available right now. You can still restore your own photo."}
        </p>
      )}
    </div>
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

/** Animates the first number in `text` from 0 when it scrolls into view. */
function CountUp({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(text);
  useEffect(() => {
    const m = text.match(/[\d,]+(\.\d+)?/);
    if (!m || !ref.current) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const target = parseFloat(m[0].replace(/,/g, ""));
    const dec = (m[1] ?? "").length ? m[1]!.length - 1 : 0;
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        io.disconnect();
        const t0 = performance.now();
        const tick = (t: number) => {
          const k = Math.min(1, (t - t0) / 1400);
          const v = target * (1 - Math.pow(1 - k, 3));
          setShown(text.replace(m[0], v.toLocaleString("en-US", { maximumFractionDigits: dec, minimumFractionDigits: dec })));
          if (k < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    io.observe(ref.current);
    return () => io.disconnect();
  }, [text]);
  return <span ref={ref}>{shown}</span>;
}
