import { useEffect, useRef, useState } from "react";
import { href, NAV_LINKS, NAV_MORE, NAV_PRIMARY, type Route } from "../lib/router";
import { Link } from "./Link";
import { currentUser, onAuthChange, signOut } from "../lib/auth";

interface Props {
  route: Route;
  seq: number;
}

/* A dark glass console bar: logo, two links, "More", account, one call to action. */
export function SiteHeader({ route, seq }: Props) {
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

  const moreActive = NAV_MORE.some((l) => l.name === route.name);
  const initials = user ? (user.name || user.email).trim().slice(0, 1).toUpperCase() : "";

  return (
    <header className="glass-header on-dark sticky top-0 z-50">
      <div className="mx-auto flex max-w-[110rem] items-center justify-between gap-6 px-6 py-3 sm:px-10">
        <Link to={href.home} className="brand flex items-center gap-3" aria-label="Cold Case, home">
          <span className="brand-mark" aria-hidden>
            <span />
          </span>
          <span className="readout text-sm font-semibold tracking-[0.22em] text-ground">Cold Case</span>
        </Link>

        <nav aria-label="Main" className="hidden items-center gap-2 md:flex">
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

        <div className="hidden items-center gap-3 md:flex">
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

        <div className="md:hidden">
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
