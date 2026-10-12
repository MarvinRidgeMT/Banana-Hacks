/** "My cases". Signed in: kept on the server, per account, on any device.
 * Signed out: kept in this browser only. Signing in adds this browser's cases to the account. */
import { API_BASE } from "./api";
import { authToken, onAuthChange } from "./auth";

export interface HistoryItem {
  key: string;
  title: string;
  kind: "photo" | "document";
  at: number; // ms since epoch
}

const STORE = "coldcase.history.v1";
const MAX = 60;
const listeners = new Set<() => void>();
let server: HistoryItem[] | null = null; // the signed-in account's cases

const notify = () => listeners.forEach((f) => f());

function local(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(STORE);
    const list = raw ? (JSON.parse(raw) as HistoryItem[]) : [];
    return Array.isArray(list) ? list.filter((h) => h && typeof h.key === "string") : [];
  } catch {
    return [];
  }
}
function saveLocal(list: HistoryItem[]) {
  try {
    localStorage.setItem(STORE, JSON.stringify(list.slice(0, MAX)));
  } catch {
    /* private mode or storage full */
  }
  notify();
}

async function api(method: "GET" | "POST", body?: unknown) {
  const t = authToken();
  if (!t) throw new Error("signed out");
  const r = await fetch(`${API_BASE}/cases`, {
    method,
    headers: { Authorization: `Bearer ${t}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

export async function refreshHistory() {
  if (!authToken()) {
    server = null;
    notify();
    return;
  }
  try {
    server = (await api("GET")) as HistoryItem[];
  } catch {
    server = server ?? [];
  }
  notify();
}

/** After signing in: copy this browser's cases into the account, then load the account's list. */
async function onSignIn() {
  if (!authToken()) {
    server = null;
    notify();
    return;
  }
  for (const h of local()) {
    await api("POST", { key: h.key, title: h.title, kind: h.kind }).catch(() => {});
  }
  await refreshHistory();
}
onAuthChange(() => void onSignIn());
if (authToken()) void refreshHistory();

export function loadHistory(): HistoryItem[] {
  return authToken() ? (server ?? []) : local();
}

export function addHistory(item: Omit<HistoryItem, "at">) {
  const entry = { ...item, at: Date.now() };
  if (authToken()) {
    server = [entry, ...(server ?? []).filter((h) => h.key !== item.key)];
    notify();
    api("POST", item).catch(() => {});
    return;
  }
  saveLocal([entry, ...local().filter((h) => h.key !== item.key)]);
}

export function removeHistory(key: string) {
  if (authToken()) {
    server = (server ?? []).filter((h) => h.key !== key);
    notify();
    api("POST", { action: "delete", key }).catch(() => {});
    return;
  }
  saveLocal(local().filter((h) => h.key !== key));
}

export function clearHistory() {
  if (authToken()) {
    server = [];
    notify();
    api("POST", { action: "delete" }).catch(() => {});
    return;
  }
  saveLocal([]);
}

export function onHistoryChange(f: () => void): () => void {
  listeners.add(f);
  return () => listeners.delete(f);
}

export function ago(ms: number): string {
  const s = Math.max(1, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return d === 1 ? "yesterday" : `${d} days ago`;
}
