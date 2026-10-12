import { useState } from "react";
import { signIn, signUp } from "../lib/auth";
import { href, navigate } from "../lib/router";

const FIELD =
  "mt-1 block w-full rounded-sm border border-line bg-surface px-4 py-3 text-lg outline-none focus:border-ink";

export function Account() {
  const [mode, setMode] = useState<"in" | "up">("in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "up") await signUp(name, email, password);
      else await signIn(email, password);
      navigate(href.cases);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto grid max-w-5xl gap-14 py-6 lg:grid-cols-2 lg:items-start">
      <section>
        <p className="case-label">Case files · your account</p>
        <h1 className="mt-3 font-serif text-5xl leading-[1.08] sm:text-6xl">
          {mode === "in" ? "Welcome back." : "Open your case file."}
        </h1>
        <p className="mt-5 text-xl leading-relaxed text-body">
          With an account, every photo you restore is saved to <span className="font-semibold">My cases</span>,
          private to you and available on any device. Cases you made before signing in are added automatically.
        </p>
        <ul className="mt-8 space-y-3 text-body">
          <li>· Passwords are hashed with scrypt and a unique salt; we never store them.</li>
          <li>· Sessions use random 256-bit tokens; the server keeps only their hash.</li>
          <li>· Sign-in attempts are rate-limited to stop password guessing.</li>
        </ul>
      </section>

      <section className="rounded-sm border border-line bg-surface/70 p-8">
        <div className="mb-6 inline-grid grid-cols-2 overflow-hidden rounded-sm border border-line text-sm" role="tablist">
          {(
            [
              ["in", "Sign in"],
              ["up", "Create account"],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={`px-5 py-2 font-semibold ${mode === m ? "bg-ink text-ground" : "hover:bg-tag"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="space-y-5">
          {mode === "up" && (
            <label className="block">
              <span className="font-semibold">Name</span>
              <input className={FIELD} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={60} />
            </label>
          )}
          <label className="block">
            <span className="font-semibold">Email</span>
            <input
              className={FIELD}
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              maxLength={254}
            />
          </label>
          <label className="block">
            <span className="font-semibold">Password</span>
            <input
              className={FIELD}
              type="password"
              required
              minLength={mode === "up" ? 8 : 1}
              maxLength={200}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "up" ? "new-password" : "current-password"}
            />
            {mode === "up" && <span className="mt-1 block text-sm text-muted">At least 8 characters.</span>}
          </label>
          {error && (
            <p role="alert" className="text-invented">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-sm bg-ink px-6 py-3 text-lg font-semibold text-ground hover:bg-ink/85 disabled:opacity-60"
          >
            {busy ? "One moment…" : mode === "in" ? "Sign in" : "Create account"}
          </button>
        </form>
      </section>
    </div>
  );
}
