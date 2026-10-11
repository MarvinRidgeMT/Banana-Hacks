import type { Demo, Job, Metrics, Result } from "./types";

/** Empty when the site is served by the backend or the Vite dev proxy;
 * the Cloudflare Tunnel URL when the site is on Vercel. */
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

/** Copies of the demo results shipped with the site (see backend/export_static_demos.py),
 * used when the restoring server can't be reached, so the demo cases always work. */
const STATIC_BASE = "/static-api";
const OFFLINE_MSG =
  "The restoring server is offline right now, so new photos can't be restored. The demo cases still work.";

let mode: "live" | "static" = "live";
let modePromise: Promise<"live" | "static"> | null = null;

/** Decide once per page load whether the live server answers (4 s timeout). */
export function apiMode(): Promise<"live" | "static"> {
  if (!modePromise) {
    modePromise = (async () => {
      try {
        const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(4000) });
        if (res.ok) return "live" as const;
      } catch {
        /* unreachable: fall through */
      }
      try {
        const res = await fetch(`${STATIC_BASE}/demos.json`);
        if (res.ok) return "static" as const;
      } catch {
        /* no static copies either */
      }
      return "live" as const;
    })().then((m) => (mode = m));
  }
  return modePromise;
}

const fidelityDir = (f: number) => `f${String(Math.round(f * 100)).padStart(3, "0")}`;

export function fileUrl(key: string, file: string, download = false): string {
  if (mode === "static") return `${STATIC_BASE}/results/${key}/${file}`;
  return `${API_BASE}/results/${key}/${file}${download ? "?download=1" : ""}`;
}

export class ApiError extends Error {}

async function json<T>(res: Response): Promise<T> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* not JSON */
  }
  if (!res.ok) {
    const msg = (body as { error?: string } | null)?.error ?? `The server answered ${res.status}.`;
    throw new ApiError(msg);
  }
  return body as T;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  if ((await apiMode()) === "static") {
    if (path === "/health") return { ok: true, pipeline: "static", queued: 0, running: 0 } as T;
    if (path === "/metrics" || path === "/demos") return json<T>(await fetch(`${STATIC_BASE}${path}.json`));
    throw new ApiError(OFFLINE_MSG);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(
      "Can't reach the Cold Case server. Check that the backend and the tunnel are running.",
    );
  }
  return json<T>(res);
}

export const api = {
  health: () => call<{ ok: boolean; pipeline: string; queued: number; running: number }>("/health"),
  metrics: () => call<Metrics>("/metrics"),
  demos: () => call<Demo[]>("/demos"),
  job: (id: string) => call<Job>(`/jobs/${id}`),

  /** Cached result, or null if this fidelity step hasn't been computed yet. */
  async result(key: string, fidelity: number): Promise<Result | null> {
    if ((await apiMode()) === "static") {
      const r = await fetch(`${STATIC_BASE}/results/${key}/${fidelityDir(fidelity)}/result.json`);
      if (r.status === 404) throw new ApiError(OFFLINE_MSG);
      return json<Result>(r);
    }
    const res = await fetch(`${API_BASE}/results/${key}?fidelity=${fidelity}`).catch(() => {
      throw new ApiError("Can't reach the Cold Case server.");
    });
    if (res.status === 202) return null; // known photo, this fidelity step not computed yet
    return json<Result>(res);
  },

  /** Upload a photo and get the segmenter's proposed damage mask to review. */
  propose(file: File, kind: "photo" | "document" = "photo") {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return call<{ key: string; original: string; mask: string | null }>("/propose", { method: "POST", body: form });
  },

  restore(opts: { file?: File; key?: string; mask?: Blob; kind?: "photo" | "document"; fidelity: number; allFidelities?: boolean }) {
    const form = new FormData();
    if (opts.kind) form.append("kind", opts.kind);
    if (opts.file) form.append("file", opts.file);
    if (opts.key) form.append("key", opts.key);
    if (opts.mask) form.append("mask", opts.mask, "mask.png");
    form.append("fidelity", String(opts.fidelity));
    form.append("all_fidelities", opts.allFidelities === false ? "false" : "true");
    return call<Job>("/restore", { method: "POST", body: form });
  },
};

/** Poll a job until it finishes. Calls onUpdate on every poll. */
export async function waitForJob(
  job: Job,
  onUpdate: (j: Job) => void,
  signal: AbortSignal,
): Promise<Job> {
  let current = job;
  onUpdate(current);
  while (current.status === "queued" || current.status === "running") {
    await new Promise((r) => setTimeout(r, 800));
    if (signal.aborted) throw new DOMException("aborted", "AbortError");
    current = await api.job(current.id);
    onUpdate(current);
  }
  return current;
}
