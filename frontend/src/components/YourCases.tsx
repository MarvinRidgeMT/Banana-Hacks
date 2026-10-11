import { useEffect, useState } from "react";
import { apiMode, fileUrl } from "../lib/api";
import { ago, clearHistory, loadHistory, onHistoryChange, removeHistory, type HistoryItem } from "../lib/history";
import { href } from "../lib/router";
import { DEFAULT_FIDELITY } from "../lib/types";
import { Link } from "./Link";

export function useHistory(): HistoryItem[] {
  const [items, setItems] = useState<HistoryItem[]>(() => loadHistory());
  useEffect(() => onHistoryChange(() => setItems(loadHistory())), []);
  return items;
}

/** The photos this browser restored before, newest first. Renders nothing when there are none. */
export function YourCases({ dark = false, limit }: { dark?: boolean; limit?: number }) {
  const items = useHistory();
  if (items.length === 0) return null;
  const shown = limit ? items.slice(0, limit) : items;
  const muted = dark ? "text-ground/60" : "text-muted";
  return (
    <section aria-labelledby="your-cases">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className={`readout text-xs ${muted}`}>Saved in this browser · {items.length} case{items.length === 1 ? "" : "s"}</p>
          <h2 id="your-cases" className="mt-2 font-serif text-3xl sm:text-4xl">
            Your restorations
          </h2>
        </div>
        <button
          type="button"
          onClick={clearHistory}
          className={`text-sm underline underline-offset-4 ${muted} hover:text-invented`}
        >
          Clear history
        </button>
      </div>
      <ul className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-5">
        {shown.map((h) => (
          <li key={h.key} className="group relative">
            <Link to={href.result(h.key, DEFAULT_FIDELITY)} className="block" aria-label={`Open ${h.title}`}>
              <div className="relative aspect-square overflow-hidden bg-mat ring-1 ring-ink/10 transition group-hover:ring-ink/50">
                <Thumb item={h} />
                <span className="readout absolute left-2 top-2 bg-mat/80 px-1.5 py-0.5 text-[0.6rem] text-ground/80">
                  {h.kind === "document" ? "Document" : "Photo"} · {h.key.slice(0, 6)}
                </span>
              </div>
              <p className="mt-3 truncate font-semibold group-hover:underline">{h.title}</p>
              <p className={`text-sm ${muted}`}>{ago(h.at)}</p>
            </Link>
            <button
              type="button"
              onClick={() => removeHistory(h.key)}
              aria-label={`Remove ${h.title} from your history`}
              className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full bg-mat/80 text-ground opacity-0 transition group-hover:opacity-100 focus:opacity-100"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Thumb({ item }: { item: HistoryItem }) {
  // the restoration if it's there; the uploaded scan otherwise
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    apiMode().then(() => live && setSrc(fileUrl(item.key, "f070/restored.png")));
    return () => {
      live = false;
    };
  }, [item.key]);
  if (!src) return null;
  return (
    <img
      src={src}
      alt=""
      crossOrigin="anonymous"
      loading="lazy"
      onError={() => setSrc((s) => (!s || s.endsWith("input.png") ? s : fileUrl(item.key, "input.png")))}
      className="h-full w-full object-contain p-2 transition duration-500 group-hover:scale-[1.03]"
    />
  );
}
