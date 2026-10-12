/** Sign-in state. The session token (random, 256-bit, expires in 30 days) is kept in this
 * browser and sent as a Bearer header; the server stores only its hash. */
import { API_BASE } from "./api";

export interface User {
  email: string;
  name: string;
}
const STORE = "coldcase.session.v1";
const listeners = new Set<() => void>();
let state: { token: string; user: User } | null = read();

function read(): { token: string; user: User } | null {
  try {
    const raw = localStorage.getItem(STORE);
    const v = raw ? JSON.parse(raw) : null;
    return v && typeof v.token === "string" && v.user ? v : null;
  } catch {
    return null;
  }
}
function write(v: typeof state) {
  state = v;
  try {
    if (v) localStorage.setItem(STORE, JSON.stringify(v));
    else localStorage.removeItem(STORE);
  } catch {
    /* storage blocked: the session lasts until the tab closes */
  }
  listeners.forEach((f) => f());
}

export const currentUser = () => state?.user ?? null;
export const authToken = () => state?.token ?? null;
export function onAuthChange(f: () => void): () => void {
  listeners.add(f);
  return () => listeners.delete(f);
}

async function post(path: string, body: unknown): Promise<{ token: string; user: User }> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Can't reach the Cold Case server right now, so accounts are unavailable.");
  }
  const j = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(j.error ?? `The server answered ${res.status}.`);
  return j;
}

export async function signUp(name: string, email: string, password: string) {
  write(await post("/auth/signup", { name, email, password }));
}
export async function signIn(email: string, password: string) {
  write(await post("/auth/login", { email, password }));
}
export async function signOut() {
  const t = authToken();
  write(null);
  if (t) fetch(`${API_BASE}/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${t}` } }).catch(() => {});
}

/** Check the stored session is still valid (expired or revoked → signed out). */
export async function verifySession() {
  const t = authToken();
  if (!t) return;
  try {
    const r = await fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${t}` } });
    if (r.status === 401) write(null);
  } catch {
    /* offline: keep the session */
  }
}
