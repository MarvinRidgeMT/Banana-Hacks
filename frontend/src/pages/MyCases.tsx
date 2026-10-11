import { Link } from "../components/Link";
import { useHistory, YourCases } from "../components/YourCases";
import { href } from "../lib/router";

export function MyCases() {
  const items = useHistory();
  return (
    <div className="space-y-12">
      <section className="max-w-3xl">
        <p className="case-label">Case files · this browser</p>
        <h1 className="mt-3 font-serif text-5xl leading-[1.08] sm:text-6xl">My cases</h1>
        <p className="mt-5 text-xl leading-relaxed text-body">
          Every photo you restore is kept here, with its labels, alternatives, color version and signed receipt.
          The list lives in this browser; the results stay on the restoring server, so each link keeps working.
        </p>
      </section>
      {items.length === 0 ? (
        <section className="rounded-sm border border-dashed border-faint bg-surface/60 p-12 text-center">
          <p className="font-serif text-3xl">No cases yet</p>
          <p className="mt-2 text-muted">Restore a photo and it will appear here.</p>
          <Link
            to={href.restore}
            className="mt-6 inline-block rounded-sm bg-ink px-6 py-3 text-lg font-semibold text-ground hover:bg-ink/85"
          >
            Restore a photo
          </Link>
        </section>
      ) : (
        <YourCases />
      )}
    </div>
  );
}
