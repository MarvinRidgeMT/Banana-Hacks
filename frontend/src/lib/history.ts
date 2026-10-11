/** "Your restorations": the photos this browser has restored, so people can come back to them.
 * Kept in localStorage (this browser only; nothing is sent anywhere). The results themselves stay
 * in the server's cache, keyed by the photo's SHA-256, so a saved link keeps working. */
export interface HistoryItem {
  key: string;
  title: string;
  kind: "photo" | "document";
  at: number; // ms since epoch
}

const STORE = "coldcase.history.v1";
const MAX = 60;
const listeners = new Set<() => void>();

export function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(STORE);
    const list = raw ? (JSON.parse(raw) as HistoryItem[]) : [];
    return Array.isArray(list) ? list.filter((h) => h && typeof h.key === "string") : [];
  } catch {
    return [];
  }
}

function save(list: HistoryItem[]) {
  try {
    localStorage.setItem(STORE, JSON.stringify(list.slice(0, MAX)));
  } catch {
    /* private mode or storage full: history just isn't kept */
  }
  listeners.forEach((f) => f());
}

export function addHistory(item: Omit<HistoryItem, "at">) {
  const rest = loadHistory().filter((h) => h.key !== item.key);
  save([{ ...item, at: Date.now() }, ...rest]);
}

export function removeHistory(key: string) {
  save(loadHistory().filter((h) => h.key !== key));
}

export function clearHistory() {
  save([]);
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
