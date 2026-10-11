import type { ReactNode } from "react";
import { isPlaceholder } from "../lib/format";
import type { Demo } from "../lib/types";

// TODO: confirm full names with Sid and Anish before the demo.
const TEAM = [
  { name: "Sid", role: "Pipeline and models" },
  { name: "Anish", role: "Website, API and evidence" },
];

const NEXT = [
  "More labeled real damage, prioritizing thin cracks, and (with consent) turning human-corrected masks into training data.",
  "Reference photos: add another photo of the same person, so a face guess can be checked against a real likeness.",
  "A trusted signing certificate, so receipts show as verified.",
  "A commercially licensed face model to replace CodeFormer.",
  "Batch mode for archives: restore a whole collection, then sort by invented area so staff review the riskiest images first.",
  "A calibration study on photos with known undamaged originals.",
];

const ToConfirm = () => (
  <span className="inline-block bg-warn px-2 py-0.5 font-mono text-xs font-semibold uppercase tracking-[0.08em] text-ink">
    To confirm
  </span>
);

function sourceLink(url: string): ReactNode {
  if (isPlaceholder(url)) return <ToConfirm />;
  if (!/^https?:\/\//.test(url)) return url;
  return (
    <a href={url} target="_blank" rel="noreferrer" className="break-all underline underline-offset-4 hover:text-ink">
      {url}
    </a>
  );
}

function Credits({ demos, error }: { demos: Demo[] | null; error: string | null }) {
  if (error) return <p className="mt-4 text-invented">Couldn't load the demo photos: {error}</p>;
  if (!demos) return <p className="mt-4 text-muted">Loading the demo photos…</p>;
  if (demos.length === 0) return <p className="mt-4 text-muted">No demo photos on the server yet.</p>;
  return (
    <ul className="mt-6 grid gap-6 lg:grid-cols-2">
      {demos.map((d) => (
        <li key={d.id} className="bg-surface p-6">
          <p className="font-serif text-2xl">{d.title}</p>
          <dl className="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2">
            <dt className="case-label pt-1">Credit</dt>
            <dd className="text-body">{isPlaceholder(d.credit) ? <ToConfirm /> : d.credit}</dd>
            <dt className="case-label pt-1">Source</dt>
            <dd className="text-body">{sourceLink(d.source_url)}</dd>
            <dt className="case-label pt-1">License</dt>
            <dd className="text-body">{isPlaceholder(d.license) ? <ToConfirm /> : d.license}</dd>
          </dl>
        </li>
      ))}
    </ul>
  );
}

export function About({ demos, demosError }: { demos: Demo[] | null; demosError: string | null }) {
  return (
    <div className="space-y-16">
      <section className="max-w-4xl">
        <p className="case-label">Case file · the team</p>
        <h1 className="mt-3 font-serif text-5xl leading-[1.08] sm:text-6xl">About</h1>
      </section>

      <section className="max-w-4xl">
        <h2 className="font-serif text-3xl">Who it's for</h2>
        <p className="mt-6 max-w-[64ch] text-xl leading-relaxed text-body">
          Volunteer digitizers at small historical societies and public libraries: a box of donated photos, a
          flatbed scanner, a shared laptop and no budget for a conservator. They want to publish restored photos
          without misrepresenting the people in them. Genealogists and families come second: they want to know
          which features in a restored ancestor photo are really their relative's.
        </p>
        <p className="mt-6 max-w-[64ch] text-xl leading-relaxed text-body">
          It's a website, so it runs on locked-down library computers with nothing to install. It's free and open
          source.
        </p>
      </section>

      <section>
        <h2 className="font-serif text-3xl">Team</h2>
        <ul className="mt-6 grid gap-6 sm:grid-cols-2 lg:max-w-4xl">
          {TEAM.map((p) => (
            <li key={p.name} className="bg-surface p-6">
              <p className="font-serif text-2xl">{p.name}</p>
              <p className="mt-2 text-body">{p.role}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="max-w-4xl">
        <h2 className="font-serif text-3xl">What's next</h2>
        <ul className="mt-6 list-disc space-y-3 pl-6 text-lg text-body marker:text-muted">
          {NEXT.map((item) => (
            <li key={item} className="max-w-[72ch]">
              {item}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="font-serif text-3xl">Photo credits</h2>
        <Credits demos={demos} error={demosError} />
      </section>
    </div>
  );
}
