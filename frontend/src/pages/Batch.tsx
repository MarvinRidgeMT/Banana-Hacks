import { useEffect, useRef, useState } from "react";
import { Link } from "../components/Link";
import { api, batchCsvUrl, fileUrl } from "../lib/api";
import { failure } from "../lib/format";
import { href, navigate } from "../lib/router";
import type { BatchStatus } from "../lib/types";
import { DEFAULT_FIDELITY } from "../lib/types";

const STORE = "coldcase.batches.v1";
const pct = (x?: number) => (x === undefined ? "–" : `${(x * 100).toFixed(1)}%`);

function savedBatches(): { id: string; at: number; total: number }[] {
  try {
    return JSON.parse(localStorage.getItem(STORE) ?? "[]");
  } catch {
    return [];
  }
}
function remember(b: BatchStatus) {
  try {
    const list = savedBatches().filter((x) => x.id !== b.id);
    localStorage.setItem(STORE, JSON.stringify([{ id: b.id, at: Date.now(), total: b.total }, ...list].slice(0, 20)));
  } catch {
    /* storage blocked */
  }
}

export function Batch({ batchId }: { batchId?: string }) {
  return batchId ? <BatchView id={batchId} /> : <BatchUpload />;
}

function BatchUpload() {
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<"photo" | "document">("photo");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const past = savedBatches();

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const b = await api.batchCreate(files, kind);
      remember(b);
      navigate(href.batch(b.id));
    } catch (e) {
      setError(failure("Couldn't start the batch", e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-12">
      <section className="max-w-3xl">
        <p className="case-label">Batch mode · for archives</p>
        <h1 className="mt-3 font-serif text-5xl leading-[1.08] sm:text-6xl">Restore a whole box of scans.</h1>
        <p className="mt-5 text-xl leading-relaxed text-body">
          Add up to 40 scans at once. Cold Case restores them in a queue, then lists them with the most invented first,
          so staff review the riskiest images before anything is published. Export the list as a CSV for your catalog.
        </p>
      </section>
      <section className="rounded-sm border-2 border-dashed border-faint bg-surface/60 p-10 text-center">
        <p className="font-serif text-3xl">{files.length ? `${files.length} scan${files.length === 1 ? "" : "s"} ready` : "Choose your scans"}</p>
        <p className="mt-2 text-muted">JPG, PNG or TIFF, up to 30 MB each, 40 per batch</p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-4">
          <button type="button" onClick={() => input.current?.click()} className="rounded-sm border border-ink px-6 py-3 font-semibold hover:bg-tag">
            {files.length ? "Change files" : "Choose files"}
          </button>
          <div className="inline-grid grid-cols-2 overflow-hidden rounded-sm border border-line text-sm" role="radiogroup" aria-label="What are you restoring?">
            {(["photo", "document"] as const).map((k) => (
              <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}
                className={`px-4 py-2 font-semibold ${kind === k ? "bg-ink text-ground" : "bg-surface hover:bg-tag"}`}>
                {k === "photo" ? "Photos" : "Documents"}
              </button>
            ))}
          </div>
          <button
            type="button"
            disabled={!files.length || busy}
            onClick={start}
            className="rounded-sm bg-ink px-6 py-3 text-lg font-semibold text-ground hover:bg-ink/85 disabled:opacity-50"
          >
            {busy ? "Uploading…" : "Start the batch"}
          </button>
        </div>
        <input
          ref={input}
          type="file"
          multiple
          accept="image/*,.tif,.tiff"
          className="sr-only"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 40))}
        />
        {error && <p className="mt-4 text-invented">{error}</p>}
      </section>
      {past.length > 0 && (
        <section>
          <h2 className="font-serif text-3xl">Earlier batches in this browser</h2>
          <ul className="mt-4 space-y-2">
            {past.map((b) => (
              <li key={b.id}>
                <Link to={href.batch(b.id)} className="underline underline-offset-4 hover:text-body">
                  Batch {b.id.slice(0, 8)} · {b.total} scans · {new Date(b.at).toLocaleString()}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function BatchView({ id }: { id: string }) {
  const [st, setSt] = useState<BatchStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const s = await api.batch(id);
        if (stop) return;
        setSt(s);
        remember(s);
        setError(null);
        if (s.done < s.items.filter((i) => i.key).length) setTimeout(tick, 3000);
      } catch (e) {
        if (!stop) setError(failure("Couldn't load the batch", e));
      }
    };
    void tick();
    return () => {
      stop = true;
    };
  }, [id]);

  const working = st ? st.items.filter((i) => i.key).length : 0;
  return (
    <div className="space-y-10">
      <section className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="case-label">Batch {id.slice(0, 8)}</p>
          <h1 className="mt-3 font-serif text-5xl">
            {st ? `${st.done} of ${working} restored` : "Loading the batch…"}
          </h1>
          <p className="mt-3 text-body">Sorted by invented share, most first: review from the top.</p>
        </div>
        {st && (
          <a href={batchCsvUrl(id)} className="rounded-sm bg-ink px-6 py-3 font-semibold text-ground hover:bg-ink/85">
            Download catalog CSV
          </a>
        )}
      </section>
      {st && (
        <div className="h-2 w-full overflow-hidden rounded-full bg-line" aria-hidden>
          <div className="h-full bg-inferred transition-all" style={{ width: `${(100 * st.done) / Math.max(1, working)}%` }} />
        </div>
      )}
      {error && <p className="text-invented">{error}</p>}
      {st && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="border-b border-ink text-sm text-muted">
                <th className="py-3 pr-4 font-normal">Scan</th>
                <th className="py-3 pr-4 font-normal">File</th>
                <th className="py-3 pr-4 font-normal">Status</th>
                <th className="py-3 pr-4 text-right font-normal">Real</th>
                <th className="py-3 pr-4 text-right font-normal">Rebuilt</th>
                <th className="py-3 pr-4 text-right font-normal">Invented</th>
                <th className="py-3 font-normal" />
              </tr>
            </thead>
            <tbody>
              {st.items.map((it, i) => (
                <tr key={it.key ?? `${it.filename}-${i}`} className="border-b border-line">
                  <td className="py-3 pr-4">
                    {it.key && it.thumb ? (
                      <img src={fileUrl(it.key, it.thumb)} alt="" crossOrigin="anonymous" className="h-14 w-14 bg-mat object-contain" />
                    ) : (
                      <span className="block h-14 w-14 animate-pulse bg-line" />
                    )}
                  </td>
                  <td className="py-3 pr-4 font-semibold">{it.filename}</td>
                  <td className="py-3 pr-4 text-sm">
                    {it.status === "done" ? "Restored" : it.status === "running" ? "Restoring now" : it.status === "queued" ? `In line${it.position ? ` (#${it.position})` : ""}` : <span className="text-invented">{it.error ?? "Failed"}</span>}
                  </td>
                  <td className="readout py-3 pr-4 text-right">{pct(it.pixel_summary?.observed)}</td>
                  <td className="readout py-3 pr-4 text-right">{pct(it.pixel_summary?.inferred)}</td>
                  <td className={`readout py-3 pr-4 text-right ${(it.pixel_summary?.invented ?? 0) > 0.01 ? "font-semibold text-invented" : ""}`}>
                    {pct(it.pixel_summary?.invented)}
                  </td>
                  <td className="py-3 text-right">
                    {it.key && it.status === "done" && (
                      <Link to={href.result(it.key, DEFAULT_FIDELITY)} className="underline underline-offset-4">
                        Open case
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
