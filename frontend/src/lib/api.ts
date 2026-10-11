import type { Demo, Job, Metrics, Result } from "./types";

/** Empty when the site is served by the backend or the Vite dev proxy;
 * the Cloudflare Tunnel URL when the site is on Vercel. */
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export function fileUrl(key: string, file: string, download = false): string {
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
    const res = await fetch(`${API_BASE}/results/${key}?fidelity=${fidelity}`).catch(() => {
      throw new ApiError("Can't reach the Cold Case server.");
    });
    if (res.status === 202) return null; // known photo, this fidelity step not computed yet
    return json<Result>(res);
  },

  /** Upload a photo and get the segmenter's proposed damage mask to review. */
  propose(file: File) {
    const form = new FormData();
    form.append("file", file);
    return call<{ key: string; original: string; mask: string | null }>("/propose", { method: "POST", body: form });
  },

  restore(opts: { file?: File; key?: string; mask?: Blob; fidelity: number; allFidelities?: boolean }) {
    const form = new FormData();
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
