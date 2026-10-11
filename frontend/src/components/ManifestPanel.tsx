import { fileUrl } from "../lib/api";
import type { Result } from "../lib/types";

export function ManifestPanel({ result }: { result: Result }) {
  const f = result.files;
  const downloads: { label: string; file: string | null; note: string }[] = [
    { label: "Restored image", file: f.restored, note: "PNG" },
    { label: "Signed image", file: f.signed, note: "Receipt sealed inside the file (C2PA, demo certificate)" },
    { label: "Evidence map", file: f.map, note: "PNG, coloured and hatched" },
    { label: "Label map", file: f.label, note: "PNG, values 0 real, 1 rebuilt, 2 invented" },
    { label: "Receipt", file: f.manifest, note: "JSON, every edit and setting" },
    { label: "Damage mask", file: f.mask, note: "PNG, white = damaged" },
  ];
  return (
    <div className="grid gap-8 lg:grid-cols-[18rem_1fr]">
      <ul className="space-y-3">
        {downloads
          .filter((d) => d.file)
          .map((d) => (
            <li key={d.label}>
              <a
                href={fileUrl(result.key, d.file!, true)}
                className="block rounded-sm border border-line bg-surface px-4 py-3 hover:bg-tag"
              >
                <span className="block font-semibold">Download {d.label.toLowerCase()}</span>
                <span className="block text-sm text-muted">{d.note}</span>
              </a>
            </li>
          ))}
      </ul>
      <pre className="max-h-[32rem] overflow-auto rounded-sm border border-line bg-surface p-4 font-mono text-sm leading-relaxed">
        {JSON.stringify(result.manifest, null, 2)}
      </pre>
    </div>
  );
}
