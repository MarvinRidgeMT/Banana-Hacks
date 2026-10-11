import { Link } from "../components/Link";
import { href } from "../lib/router";

export function NotFound({ hash }: { hash: string }) {
  return (
    <section className="mx-auto max-w-3xl py-12">
      <div className="bg-surface p-8 sm:p-12">
        <div className="flex flex-col-reverse items-start gap-6 sm:flex-row sm:justify-between">
          <p className="case-label">Records office · error 404</p>
          <span className="stamp shrink-0 text-lg">Not on file</span>
        </div>
        <h1 className="mt-3 max-w-[14ch] font-serif text-5xl leading-[1.08]">No record of this page</h1>
        <p className="mt-6 max-w-[52ch] text-lg text-body">
          Nothing is filed under <code className="tag break-all" style={{ textTransform: "none" }}>
            {hash || "#/"}
          </code>. The link may
          be mistyped, or the page may have moved.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-6">
          <Link to={href.home} className="rounded-sm bg-ink px-6 py-3 font-semibold text-ground hover:bg-ink/85">
            Back to the home page
          </Link>
          <Link to={href.restore} className="underline underline-offset-4 hover:text-body">
            Restore a photo
          </Link>
        </div>
      </div>
    </section>
  );
}
