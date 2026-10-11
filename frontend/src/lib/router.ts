import { useSyncExternalStore } from "react";
import { DEFAULT_FIDELITY, FIDELITY_STEPS } from "./types";

/* Hash routes only: the backend serves dist/ as static files with no rewrite,
 * so a real path like /about would 404. */

export type Route =
  | { name: "home" }
  | { name: "restore" }
  | { name: "cases" }
  | { name: "result"; key: string; fidelity: number }
  | { name: "how-it-works" }
  | { name: "evidence" }
  | { name: "about" }
  | { name: "not-found"; hash: string };

export const href = {
  home: "#/",
  restore: "#/restore",
  cases: "#/cases",
  howItWorks: "#/how-it-works",
  evidence: "#/evidence",
  about: "#/about",
  result: (key: string, fidelity: number) => `#/p/${key}/${fidelity}`,
};

export const NAV_LINKS = [
  { name: "cases", label: "My cases", to: href.cases },
  { name: "how-it-works", label: "How it works", to: href.howItWorks },
  { name: "evidence", label: "Evidence", to: href.evidence },
  { name: "about", label: "About", to: href.about },
] as const satisfies readonly { name: Route["name"]; label: string; to: string }[];

const STATIC: Record<string, Route> = {
  "/": { name: "home" },
  "/restore": { name: "restore" },
  "/cases": { name: "cases" },
  "/how-it-works": { name: "how-it-works" },
  "/evidence": { name: "evidence" },
  "/about": { name: "about" },
};

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
  const fixed = STATIC[path];
  if (fixed) return fixed;
  // #/p/<key>/<fidelity> opens a result directly, so a link can go in the Devpost write-up.
  const m = path.match(/^\/p\/([0-9a-f]{64})(?:\/([\d.]+))?$/);
  if (m) {
    const f = Number(m[2]);
    const fidelity = (FIDELITY_STEPS as readonly number[]).includes(f) ? f : DEFAULT_FIDELITY;
    return { name: "result", key: m[1], fidelity };
  }
  return { name: "not-found", hash };
}

/** `seq` goes up on every real navigation (including clicking a link to the
 * page you're already on) but not on `replace`, so effects keyed on it run
 * once per visit. */
export interface RouterState {
  route: Route;
  seq: number;
}

let state: RouterState = { route: parseHash(window.location.hash), seq: 0 };
const listeners = new Set<() => void>();

function set(next: RouterState) {
  state = next;
  listeners.forEach((l) => l());
}

function onHashChange() {
  set({ route: parseHash(window.location.hash), seq: state.seq + 1 });
}

window.addEventListener("hashchange", onHashChange);

export function navigate(to: string, opts: { replace?: boolean } = {}) {
  if (opts.replace) {
    history.replaceState(null, "", to);
    set({ route: parseHash(to), seq: state.seq });
  } else if (window.location.hash === to) {
    onHashChange();
  } else {
    window.location.hash = to;
  }
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useRouter(): RouterState {
  return useSyncExternalStore(subscribe, () => state);
}
