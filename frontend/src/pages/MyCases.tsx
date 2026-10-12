import { Link } from "../components/Link";
import { useHistory, YourCases } from "../components/YourCases";
import { href } from "../lib/router";
import { useEffect, useState } from "react";
import { currentUser, onAuthChange } from "../lib/auth";

export function MyCases() {
  const items = useHistory();
  const [user, setUser] = useState(currentUser());
  useEffect(() => onAuthChange(() => setUser(currentUser())), []);
  return (
    <div className="space-y-12">
      <section className="max-w-3xl">
        <p className="case-label">Case files</p>
        <h1 className="mt-3 font-serif text-5xl leading-[1.08] sm:text-6xl">My cases</h1>
        <p className="mt-5 text-xl leading-relaxed text-body">
          Every photo you restore is kept here, with its labels, alternatives, color version and signed receipt.
          Signed in, the list is private to your account and follows you to any device.
        </p>
        <p className="mt-5 rounded-sm border border-line bg-surface px-5 py-3 text-body">
          {user ? (
            <>Signed in as <span className="font-semibold">{user.email}</span>. Your cases are saved to your account.</>
          ) : (
            <>
              These cases are saved in this browser only.{" "}
              <Link to={href.account} className="font-semibold underline underline-offset-4">
                Sign in or create an account
              </Link>{" "}
              to keep them on any device.
            </>
          )}
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
