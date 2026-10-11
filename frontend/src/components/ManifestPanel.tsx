import { useState } from "react";
import { api, fileUrl } from "../lib/api";
import { failure } from "../lib/format";
import type { ColorResult, Result } from "../lib/types";

interface Props {
  result: Result;
  color?: ColorResult | null;
  onColor?: (c: ColorResult) => void;
}

export function ManifestPanel({ result, color, onColor }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const f = result.files;
  const downloads: { label: string; file: string | null; note: string }[] = [
    { label: "Restored image", file: f.restored, note: "PNG" },
    { label: "Signed image", file: f.signed, note: "Receipt sealed inside the file (C2PA, demo certificate)" },
    { label: "Evidence map", file: f.map, note: "PNG, coloured and hatched" },
    { label: "Label map", file: f.label, note: "PNG, values 0 real, 1 rebuilt, 2 invented" },
    { label: "Receipt", file: f.manifest, note: "JSON, every edit and setting" },
    { label: "Damage mask", file: f.mask, note: "PNG, white = damaged" },
  ];
  const colorDownloads: { label: string; file: string | null; note: string }[] = color
    ? [
        { label: "Color version", file: color.files.colorized, note: "PNG, the restoration with color added" },
        { label: "Signed color version", file: color.files.signed, note: "Color receipt sealed inside the file (C2PA)" },
        { label: "Color guess map", file: color.files.map, note: "PNG, red where the two color models disagree" },
        { label: "Color receipt", file: color.files.manifest, note: "JSON, models, labels and brightness check" },
      ]
    : [];

  const makeColor = async () => {
    setBusy(true);
    setError(null);
    try {
      onColor?.(await api.colorize(result.key, result.fidelity));
    } catch (e) {
      setError(failure("Couldn't add color", e));
    } finally {
      setBusy(false);
    }
  };

  const item = (d: { label: string; file: string | null; note: string }) => (
    <li key={d.label}>
      <a
        href={fileUrl(result.key, d.file!, true)}
        className="block rounded-sm border border-line bg-surface px-4 py-3 hover:bg-tag"
      >
        <span className="block font-semibold">Download {d.label.toLowerCase()}</span>
        <span className="block text-sm text-muted">{d.note}</span>
      </a>
    </li>
  );

  return (
    <div className="grid gap-8 lg:grid-cols-[18rem_1fr]">
      <div className="space-y-8">
        <ul className="space-y-3">{downloads.filter((d) => d.file).map(item)}</ul>
        {result.kind !== "document" && (
          <div>
            <p className="case-label mb-3">Color version</p>
            {color ? (
              <ul className="space-y-3">{colorDownloads.filter((d) => d.file).map(item)}</ul>
            ) : (
              <button
                type="button"
                onClick={makeColor}
                disabled={busy}
                className="block w-full rounded-sm border border-ink bg-ink px-4 py-3 text-left text-ground hover:bg-ink/85 disabled:opacity-60"
              >
                <span className="block font-semibold">{busy ? "Coloring… (a few seconds)" : "Make a color version to download"}</span>
                <span className="block text-sm text-ground/70">Every color is labeled as a guess; brightness stays the scan's own</span>
              </button>
            )}
            {error && <p className="mt-2 text-sm text-invented">{error}</p>}
          </div>
        )}
      </div>
      <pre className="max-h-[32rem] overflow-auto rounded-sm border border-line bg-surface p-4 font-mono text-sm leading-relaxed">
        {JSON.stringify(result.manifest, null, 2)}
      </pre>
    </div>
  );
}
