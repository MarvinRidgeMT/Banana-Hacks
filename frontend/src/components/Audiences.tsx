import { href } from "../lib/router";
import { CountUp } from "./CountUp";
import { Link } from "./Link";

/* Who it's for. Every number here is sourced; the link sits right under it. */
const AUDIENCES = [
  {
    id: "archives",
    who: "Historical societies & archives",
    stat: "21,588",
    statText: "history organizations in the US hold collections like these",
    source: {
      label: "AASLH census, 2022",
      url: "https://www.aam-us.org/2022/06/13/2022-national-census-of-history-organizations-a-report-on-the-history-community-in-the-united-states/",
    },
    risk: "A restored photo goes into the catalog and is quietly treated as the original.",
    gives: "Batch-restore a box of scans, export a CSV catalog, and attach XMP/JSON sidecars that keep each file's labels with it.",
    features: ["Batch · 40 at a time", "CSV catalog", "XMP sidecars"],
    cta: { label: "Start a batch", to: href.batch() },
  },
  {
    id: "families",
    who: "Families & genealogists",
    stat: "1,000,000",
    statText: "family photos run through one consumer AI enhancer in its first 10 days",
    source: {
      label: "MyHeritage, 2020",
      url: "https://blog.myheritage.com/2020/06/myheritage-photo-enhancer-goes-viral-one-million-photos-already-enhanced/",
    },
    risk: "An invented face is passed down as great-grandmother's real one.",
    gives: "Invented areas are marked, and the likeness check compares a restored face with another photo of the same person.",
    features: ["Real / Rebuilt / Invented", "Likeness check", "Color, labeled"],
    cta: { label: "Restore a photo", to: href.restore },
  },
  {
    id: "newsrooms",
    who: "Newsrooms & fact-checkers",
    stat: "437",
    statText: "active fact-checking projects worldwide, June 2026",
    source: { label: "Duke Reporters' Lab, 2026", url: "https://reporterslab.org/latest-news/" },
    risk: "A viral “restored” archive photo can't be traced back to what the scan really showed.",
    gives: "Drop any file into Verify: it reads the signed receipt, catches edits made after signing, and finds the case even when the receipt was stripped.",
    features: ["Signed C2PA receipt", "Tamper check", "Pixel-hash lookup"],
    cta: { label: "Verify a file", to: href.verify },
  },
  {
    id: "museums",
    who: "Museums & libraries",
    stat: "35,000",
    statText: "active museums in the United States",
    source: {
      label: "IMLS, 2014",
      url: "https://www.imls.gov/news/government-doubles-official-estimate-there-are-35000-active-museums-us",
    },
    risk: "Visitors can't tell which parts of an exhibited restoration are history and which are a model's guess.",
    gives: "Show the restoration and the evidence map side by side. Document mode never generates a letter, so a repaired letter can't say something new.",
    features: ["Evidence map", "0 letters generated", "Every setting recorded"],
    cta: { label: "How it works", to: href.howItWorks },
  },
  {
    id: "legal",
    who: "Courts, lawyers & insurers",
    stat: "Rule 707",
    statText: "a proposed US federal evidence rule for machine-generated evidence (Aug 2025)",
    source: {
      label: "Barnes & Thornburg",
      url: "https://btlaw.com/en/insights/alerts/2025/new-evidence-rule-707-would-set-standards-for-ai-generated-courtroom-evidence",
    },
    risk: "An AI-cleaned exhibit is challenged and no one can say what the software changed.",
    gives: "Every model, seed and setting is in a signed receipt inside the file, and pixels outside the damage are copied byte for byte (tested: 0 changed).",
    features: ["Full audit trail", "Untouched pixels: 0 changed", "Lost text flagged"],
    cta: { label: "See the evidence", to: href.evidence },
  },
] as const;

export function Audiences() {
  return (
    <section aria-labelledby="who-for" className="bleed aud-section on-dark relative overflow-hidden">
      <div aria-hidden className="aud-orb" />
      <div className="relative mx-auto max-w-[110rem] px-6 py-24 sm:px-10 sm:py-32">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:items-end">
          <div>
            <p className="readout flex items-center gap-3 text-xs text-ground/60">
              <span className="hud-tick" aria-hidden /> Who it's for
            </p>
            <h2 id="who-for" className="display mt-6 text-[clamp(2.8rem,6vw,6.2rem)] text-ground">
              For anyone whose photos are <span className="text-gradient">evidence.</span>
            </h2>
          </div>
          <p className="max-w-[46ch] text-xl leading-relaxed text-ground/75">
            An old photo is often the only record of a person, a place or an event. If a restorer invents part of it
            and no one can tell, the record is changed for good. These are the people who can't afford that.
          </p>
        </div>

        <ul className="mt-16 grid gap-5 md:grid-cols-2 lg:grid-cols-6">
          {AUDIENCES.map((a, i) => (
            <li key={a.id} className={`aud-card group ${i < 2 ? "lg:col-span-3" : "lg:col-span-2"}`}>
              <div className="flex h-full flex-col p-7 sm:p-8">
                <div className="flex items-center justify-between">
                  <span className="readout text-[0.7rem] text-ground/50">
                    {String(i + 1).padStart(2, "0")} / {String(AUDIENCES.length).padStart(2, "0")}
                  </span>
                  <span className="aud-dot" aria-hidden />
                </div>
                <h3 className="mt-5 text-2xl font-semibold text-ground">{a.who}</h3>
                <p className={`aud-stat mt-6 font-serif leading-none ${i < 2 ? "text-7xl" : "text-6xl"}`}>
                  {/^\d/.test(a.stat) ? <CountUp text={a.stat} /> : a.stat}
                </p>
                <p className="mt-3 text-ground/70">
                  {a.statText}{" "}
                  <a
                    href={a.source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="readout whitespace-nowrap text-[0.68rem] text-ground/45 underline underline-offset-4 hover:text-ground"
                  >
                    {a.source.label}
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                </p>
                <dl className="mt-7 space-y-4 border-t border-ground/10 pt-6">
                  <div>
                    <dt className="readout text-[0.68rem] text-[#ff8a80]">The risk</dt>
                    <dd className="mt-1 text-ground/80">{a.risk}</dd>
                  </div>
                  <div>
                    <dt className="readout text-[0.68rem] text-[#8fb4ff]">What Cold Case gives them</dt>
                    <dd className="mt-1 text-ground/80">{a.gives}</dd>
                  </div>
                </dl>
                <ul className="mt-6 flex flex-wrap gap-2" aria-label="Features">
                  {a.features.map((f) => (
                    <li key={f} className="aud-chip readout">
                      {f}
                    </li>
                  ))}
                </ul>
                <div className="mt-auto pt-8">
                  <Link to={a.cta.to} className="aud-cta">
                    {a.cta.label} <span aria-hidden>→</span>
                  </Link>
                </div>
              </div>
            </li>
          ))}
          <li className="aud-card aud-card-cta md:col-span-2 lg:col-span-6">
            <div className="flex flex-wrap items-center justify-between gap-6 p-7 sm:p-8">
              <div>
                <p className="readout text-[0.7rem] text-ground/50">And anyone with a shoebox of old photos</p>
                <p className="mt-3 font-serif text-3xl leading-tight text-ground sm:text-4xl">
                  Free, open source, and every result signed.
                </p>
              </div>
              <Link to={href.restore} className="cta-glow">
                Restore a photo <span aria-hidden>→</span>
              </Link>
            </div>
          </li>
        </ul>
      </div>
    </section>
  );
}
