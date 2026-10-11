import { fidelityLabel } from "../lib/format";
import { FIDELITY_STEPS } from "../lib/types";

interface Props {
  value: number;
  ready: number[];
  onChange: (f: number) => void;
}

/** CodeFormer's w in three precomputed steps. Lower w = more of the face invented. */
export function FidelityControl({ value, ready, onChange }: Props) {
  return (
    <fieldset>
      <legend className="mb-1 font-semibold">Face fidelity</legend>
      <p className="mb-3 text-sm text-muted">
        How closely the face stays to the damaged original. Lower means the model invents more.
      </p>
      <div className="grid grid-cols-3 overflow-hidden rounded-sm border border-line" role="radiogroup">
        {FIDELITY_STEPS.map((f) => {
          const active = f === value;
          const isReady = ready.includes(f);
          return (
            <button
              key={f}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(f)}
              className={`border-line px-2 py-2 text-center not-last:border-r ${
                active ? "bg-ink text-ground" : "bg-surface text-ink hover:bg-tag"
              }`}
            >
              <span className="block font-semibold">{fidelityLabel(f)}</span>
              <span className={`block text-sm tabular-nums ${active ? "text-ground/70" : "text-muted"}`}>
                w = {f.toFixed(1)}
                {!isReady && " (preparing)"}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
