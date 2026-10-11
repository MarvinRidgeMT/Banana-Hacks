import { useEffect, useRef, useState } from "react";
import { href, NAV_LINKS, type Route } from "../lib/router";
import { Link } from "./Link";

interface Props {
  route: Route;
  seq: number;
}

const PRIMARY = "rounded-sm bg-ink px-5 py-2.5 font-semibold text-ground hover:bg-ink/85";

export function SiteHeader({ route, seq }: Props) {
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => setOpen(false), [seq]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      menuButton.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const linkClass = (active: boolean) =>
    `underline-offset-8 hover:text-ink hover:underline ${active ? "text-ink underline decoration-2" : "text-body"}`;

  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-[110rem] items-center justify-between gap-6 px-6 py-5 sm:px-10">
        <Link to={href.home} className="stamp text-2xl" aria-label="Cold Case, home">
          Cold Case
        </Link>

        <nav aria-label="Main" className="hidden items-center gap-10 md:flex">
          <ul className="flex items-center gap-8">
            {NAV_LINKS.map((l) => (
              <li key={l.name}>
                <Link
                  to={l.to}
                  aria-current={route.name === l.name ? "page" : undefined}
                  className={linkClass(route.name === l.name)}
                >
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
          <Link
            to={href.restore}
            aria-current={route.name === "restore" ? "page" : undefined}
            className={PRIMARY}
          >
            Restore a photo
          </Link>
        </nav>

        <button
          ref={menuButton}
          type="button"
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={() => setOpen((o) => !o)}
          className="min-h-11 rounded-sm border border-line px-4 font-mono text-sm uppercase tracking-[0.12em] hover:bg-tag md:hidden"
        >
          {open ? "Close" : "Menu"}
        </button>
      </div>

      <nav id="site-menu" aria-label="Main" hidden={!open} className="border-t border-line px-6 pb-6 sm:px-10 md:hidden">
        <ul>
          {NAV_LINKS.map((l) => (
            <li key={l.name} className="border-b border-line">
              <Link
                to={l.to}
                aria-current={route.name === l.name ? "page" : undefined}
                className={`block py-4 text-lg ${linkClass(route.name === l.name)}`}
              >
                {l.label}
              </Link>
            </li>
          ))}
        </ul>
        <Link
          to={href.restore}
          aria-current={route.name === "restore" ? "page" : undefined}
          className={`mt-6 block text-center ${PRIMARY}`}
        >
          Restore a photo
        </Link>
      </nav>
    </header>
  );
}
