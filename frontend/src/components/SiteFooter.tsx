import { NAV_LINKS } from "../lib/router";
import { Link } from "./Link";

const REPO = "https://github.com/MarvinRidgeMT/Banana-Hacks";

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-surface/60">
      <div className="mx-auto grid max-w-[110rem] gap-10 px-6 py-12 sm:px-10 md:grid-cols-[minmax(0,1fr)_auto]">
        <div>
          <p className="font-serif text-2xl">Cold Case: old photos, restored. Every guess on the record.</p>
          <p className="mt-4 text-body">
            Built at Banana Hacks 2026 ·{" "}
            <a href={REPO} target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-ink">
              Source on GitHub
            </a>
          </p>
          <p className="mt-2 text-sm text-muted">Receipts are signed with a test certificate.</p>
        </div>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap gap-x-8 gap-y-3 md:flex-col">
            {NAV_LINKS.map((l) => (
              <li key={l.name}>
                <Link to={l.to} className="text-body underline-offset-4 hover:text-ink hover:underline">
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}
