import { useEffect, useRef, useState } from "react";
import { href, NAV_LINKS, NAV_MORE, NAV_PRIMARY, type Route } from "../lib/router";
import { Link } from "./Link";
import { currentUser, onAuthChange, signOut } from "../lib/auth";

interface Props {
  route: Route;
  seq: number;
  /** From /health: null while checking, "static" when only saved results are available. */
  pipeline: string | null;
}

function Status({ pipeline }: { pipeline: string | null }) {
  const [cls, label, tip] =
    pipeline === null
      ? ["is-wait", "Connecting", "Checking whether the restoring server is up"]
      : pipeline === "static"
        ? ["is-demo", "Demo mode", "The restoring server is offline. Saved cases work; new uploads need the server."]
        : pipeline === "stub"
          ? ["is-demo", "Test mode", "The server is running a fake pipeline. Results are not real restorations."]
          : ["is-live", "Live", "The restoring server is online: you can restore your own photos."];
  return (
    <span className={`status-chip readout ${cls}`} title={tip} role="status">
      <span className="status-dot" aria-hidden />
      {label}
      <span className="sr-only">. {tip}</span>
    </span>
  );
}

/* A dark glass console bar: logo, two links, "More", account, one call to action. */
export function SiteHeader({ route, seq, pipeline }: Props) {
  const [open, setOpen] = useState(false);
  const [more, setMore] = useState(false);
  const [user, setUser] = useState(currentUser());
  const menuButton = useRef<HTMLButtonElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  useEffect(() => onAuthChange(() => setUser(currentUser())), []);
  useEffect(() => {
    setOpen(false);
    setMore(false);
  }, [seq]);

  useEffect(() => {
    if (!open && !more) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      setMore(false);
      menuButton.current?.focus();
    };
    const onDown = (e: MouseEvent) => {
      if (more && moreRef.current && !moreRef.current.contains(e.target as Node)) setMore(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [open, more]);

  // On the home page the bar melts into the hero until you scroll.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  const flat = route.name === "home" && !scrolled && !open;

  const moreActive = NAV_MORE.some((l) => l.name === route.name);
  const initials = user ? (user.name || user.email).trim().slice(0, 1).toUpperCase() : "";

  return (
    <header className={`glass-header on-dark sticky top-0 z-50 ${flat ? "is-flat" : ""}`}>
      <div className="mx-auto flex max-w-[110rem] items-center justify-between gap-6 px-6 py-3 sm:px-10">
        <Link to={href.home} className="brand flex items-center gap-3" aria-label="Cold Case, home">
          <span className="brand-mark" aria-hidden>
            <span />
          </span>
          <span className="readout whitespace-nowrap text-sm font-semibold tracking-[0.22em] text-ground">Cold Case</span>
        </Link>

        <div className="hidden items-center gap-1 md:flex">
        <nav aria-label="Main" className="flex items-center gap-1">
          {NAV_PRIMARY.map((l) => (
            <Link
              key={l.name}
              to={l.to}
              aria-current={route.name === l.name ? "page" : undefined}
              className={`nav-pill ${route.name === l.name ? "is-active" : ""}`}
            >
              {l.label}
            </Link>
          ))}
          <div className="relative" ref={moreRef}>
            <button
              type="button"
              aria-expanded={more}
              aria-controls="more-menu"
              onClick={() => setMore((m) => !m)}
              className={`nav-pill ${moreActive ? "is-active" : ""}`}
            >
              More <span aria-hidden className={`inline-block transition ${more ? "rotate-180" : ""}`}>▾</span>
            </button>
            <div id="more-menu" hidden={!more} className="more-menu">
              <ul>
                {NAV_MORE.map((l) => (
                  <li key={l.name}>
                    <Link
                      to={l.to}
                      aria-current={route.name === l.name ? "page" : undefined}
                      className="more-item"
                    >
                      <span className="font-medium text-ground">{l.label}</span>
                      <span className="text-sm text-ground/55">{l.note}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </nav>

        <span className="mx-3 h-6 w-px bg-ground/15" aria-hidden />
        <div className="flex items-center gap-2">
          <Status pipeline={pipeline} />
          {user ? (
            <div className="flex items-center gap-2">
              <span className="avatar" title={user.email} aria-label={`Signed in as ${user.name || user.email}`}>
                {initials}
              </span>
              <button type="button" onClick={() => void signOut()} className="nav-pill">
                Sign out
              </button>
            </div>
          ) : (
            <Link to={href.account} className={`nav-pill ${route.name === "account" ? "is-active" : ""}`}>
              Sign in
            </Link>
          )}
          <Link
            to={href.restore}
            aria-current={route.name === "restore" ? "page" : undefined}
            className="cta-glow"
          >
            Restore a photo <span aria-hidden>→</span>
          </Link>
        </div>
        </div>

        <div className="flex items-center gap-2 md:hidden">
          <Status pipeline={pipeline} />
        <button
          ref={menuButton}
          type="button"
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={() => setOpen((o) => !o)}
          className="nav-pill min-h-11"
        >
          {open ? "Close" : "Menu"}
        </button>
        </div>
      </div>
      <div className="header-scan" aria-hidden />

      <nav id="site-menu" aria-label="Main" hidden={!open} className="px-6 pb-6 sm:px-10 md:hidden">
        <ul>
          {NAV_LINKS.map((l) => (
            <li key={l.name} className="border-b border-ground/10">
              <Link
                to={l.to}
                aria-current={route.name === l.name ? "page" : undefined}
                className={`block py-4 text-lg ${route.name === l.name ? "text-ground" : "text-ground/70"}`}
              >
                {l.label}
              </Link>
            </li>
          ))}
          <li className="border-b border-ground/10 py-4 text-lg">
            {user ? (
              <button type="button" onClick={() => void signOut()} className="text-ground/70">
                Sign out ({user.name || user.email})
              </button>
            ) : (
              <Link to={href.account} className="text-ground/70">
                Sign in
              </Link>
            )}
          </li>
        </ul>
        <Link to={href.restore} className="cta-glow mt-6 flex justify-center">
          Restore a photo <span aria-hidden>→</span>
        </Link>
      </nav>
    </header>
  );
}
