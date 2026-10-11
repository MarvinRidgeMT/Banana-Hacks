import { demoCredit } from "../lib/format";
import type { Demo } from "../lib/types";

export function DemoCredit({ demo, className = "" }: { demo: Demo; className?: string }) {
  const c = demoCredit(demo);
  if (!c) return null;
  return (
    <p className={`text-sm text-muted ${className}`}>
      {c.url ? (
        <a href={c.url} target="_blank" rel="noreferrer" className="underline">
          {c.credit}
        </a>
      ) : (
        c.credit
      )}
      {c.license && `, ${c.license}`}
    </p>
  );
}
