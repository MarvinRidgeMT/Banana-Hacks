import { useEffect, useRef, useState } from "react";
import { href, NAV_LINKS, NAV_MORE, NAV_PRIMARY, type Route } from "../lib/router";
import { Link } from "./Link";
import { currentUser, onAuthChange, signOut } from "../lib/auth";

interface Props {
  route: Route;
  seq: number;
}

/* A floating frosted-paper capsule: logo, three links, account, one call to action.
 * It takes no height in the page (pages leave room for it), so it floats over the hero. */
export function SiteHeader({ route, seq }: Props) {
  const [open, setOpen] = useState(false);
  const [more, setMore] = useState(false);
  const [user, setUser] = useState(currentUser());
  const [scrolled, setScrolled] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  useEffect(() => onAuthChange(() => setUser(currentUser())), []);
  useEffect(() => {
    setOpen(false);
    setMore(false);
  }, [seq]);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 12);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

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
  const initial = user ? (user.name || user.email).trim().slice(0, 1).toUpperCase() : "";
  const link = (active: boolean) => `top-link ${active ? "is-active" : ""}`;

  return (
    <header className="site-header">
      <div className={`capsule ${scrolled || open ? "is-raised" : ""}`}>
        <div className="flex items-center justify-between gap-4 py-2 pl-5 pr-2">
          <Link to={href.home} className="flex items-center gap-2.5" aria-label="Cold Case, home">
            <span className="logo-seal" aria-hidden>
              CC
            </span>
            <span className="font-serif text-[1.35rem] leading-none tracking-tight text-ink">Cold Case</span>
          </Link>

          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {NAV_PRIMARY.map((l) => (
              <Link key={l.name} to={l.to} aria-current={route.name === l.name ? "page" : undefined} className={link(route.name === l.name)}>
                {l.label}
              </Link>
            ))}
            <div className="relative" ref={moreRef}>
              <button
                type="button"
                aria-expanded={more}
                aria-controls="more-menu"
                onClick={() => setMore((m) => !m)}
                className={link(moreActive)}
              >
                More
                <svg aria-hidden width="10" height="10" viewBox="0 0 10 10" className={`transition ${more ? "rotate-180" : ""}`}>
                  <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
              <div id="more-menu" hidden={!more} className="more-panel">
                <ul>
                  {NAV_MORE.map((l) => (
                    <li key={l.name}>
                      <Link to={l.to} aria-current={route.name === l.name ? "page" : undefined} className="more-row">
                        <span className="font-semibold text-ink">{l.label}</span>
                        <span className="text-sm text-muted">{l.note}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </nav>

          <div className="hidden items-center gap-2 md:flex">
            {user ? (
              <>
                <span className="avatar-light" title={user.email} aria-label={`Signed in as ${user.name || user.email}`}>
                  {initial}
                </span>
                <button type="button" onClick={() => void signOut()} className="top-link">
                  Sign out
                </button>
              </>
            ) : (
              <Link to={href.account} className={link(route.name === "account")}>
                Sign in
              </Link>
            )}
            <Link to={href.restore} aria-current={route.name === "restore" ? "page" : undefined} className="top-cta">
              Restore a photo
              <span aria-hidden className="top-cta-arrow">
                →
              </span>
            </Link>
          </div>

          <div className="md:hidden">
            <button
              ref={menuButton}
              type="button"
              aria-expanded={open}
              aria-controls="site-menu"
              onClick={() => setOpen((o) => !o)}
              className="top-link min-h-11"
            >
              {open ? "Close" : "Menu"}
            </button>
          </div>
        </div>

        <nav id="site-menu" aria-label="Main" hidden={!open} className="px-5 pb-5 md:hidden">
          <ul>
            {NAV_LINKS.map((l) => (
              <li key={l.name} className="border-t border-line">
                <Link
                  to={l.to}
                  aria-current={route.name === l.name ? "page" : undefined}
                  className={`block py-3.5 text-lg ${route.name === l.name ? "font-semibold text-ink" : "text-body"}`}
                >
                  {l.label}
                </Link>
              </li>
            ))}
            <li className="border-t border-line py-3.5 text-lg">
              {user ? (
                <button type="button" onClick={() => void signOut()} className="text-body">
                  Sign out ({user.name || user.email})
                </button>
              ) : (
                <Link to={href.account} className="text-body">
                  Sign in
                </Link>
              )}
            </li>
          </ul>
          <Link to={href.restore} className="top-cta mt-2 flex justify-center">
            Restore a photo <span aria-hidden>→</span>
          </Link>
        </nav>
      </div>
    </header>
  );
}
