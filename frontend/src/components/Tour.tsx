import { useCallback, useEffect, useRef, useState } from "react";
import { href } from "../lib/router";
import { Link } from "./Link";

/** A guided 60-second walk through the landing page: scrolls to each part and captions it. */
const STEPS: { target: string; title: string; text: string }[] = [
  { target: "hero", title: "Every pixel gets a verdict", text: "Cold Case restores a damaged photo and labels every pixel: Real (untouched), Rebuilt (8 restorations agreed) or Invented (they disagreed, so it's a guess)." },
  { target: "proof", title: "Nothing else gets touched", text: "A typical restorer changes 30 to 61% of the parts of the photo that weren't damaged. Cold Case changes 0%. Drag the slider to see it." },
  { target: "answer-key", title: "The proof the labels mean something", text: "We cut Lincoln's eye out ourselves, so the true face is known. The AI drew three confident faces; none is Lincoln's. Cold Case marked that area Invented." },
  { target: "modes", title: "Photos, documents, color", text: "Document mode never runs a generative model, so it can't write fake words. Color mode marks colors the two models disagree on as a guess." },
  { target: "who", title: "Who it's for", text: "Archives, families, newsrooms, museums and courts: anyone whose photos are a record, and who needs to know what's real." },
  { target: "cases", title: "Open a case", text: "Every case has the before/after slider, the evidence map, alternative faces and a signed C2PA receipt inside the file." },
];
const STEP_MS = 9500;

export function useTour() {
  const [step, setStep] = useState<number | null>(null);
  return { step, start: () => setStep(0), setStep };
}

export function Tour({ step, setStep }: { step: number | null; setStep: (s: number | null) => void }) {
  const [paused, setPaused] = useState(false);
  const timer = useRef<number | null>(null);
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  const go = useCallback(
    (s: number | null) => {
      setPaused(false);
      setStep(s === null || s >= STEPS.length ? null : Math.max(0, s));
    },
    [setStep],
  );

  // Scroll to and highlight the current part.
  useEffect(() => {
    document.querySelectorAll(".tour-on").forEach((el) => el.classList.remove("tour-on"));
    if (step === null) return;
    const el = document.querySelector<HTMLElement>(`[data-tour="${STEPS[step].target}"]`);
    if (!el) return;
    el.classList.add("tour-on");
    const top = el.getBoundingClientRect().top + window.scrollY - 72;
    window.scrollTo({ top, behavior: reduced ? "auto" : "smooth" });
    return () => el.classList.remove("tour-on");
  }, [step, reduced]);

  // Auto-advance.
  useEffect(() => {
    if (step === null || paused) return;
    timer.current = window.setTimeout(() => go(step + 1), STEP_MS);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [step, paused, go]);

  useEffect(() => {
    if (step === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") go(null);
      if (e.key === "ArrowRight") go(step + 1);
      if (e.key === "ArrowLeft") go(Math.max(0, step - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, go]);

  if (step === null) return null;
  const s = STEPS[step];
  const last = step === STEPS.length - 1;
  return (
    <div className="tour-card on-dark" role="dialog" aria-label="Guided tour" aria-live="polite">
      <div className="tour-progress" aria-hidden>
        {STEPS.map((_, i) => (
          <span key={i} className={i < step ? "done" : i === step ? (paused ? "now paused" : "now") : ""} style={{ ["--ms" as string]: `${STEP_MS}ms` }} />
        ))}
      </div>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="readout text-[0.68rem] text-ground/50">
            Tour · {step + 1} of {STEPS.length}
          </p>
          <p className="mt-2 text-xl font-semibold text-ground">{s.title}</p>
        </div>
        <button type="button" onClick={() => go(null)} className="nav-pill !px-3" aria-label="End the tour">
          ✕
        </button>
      </div>
      <p className="mt-2 leading-relaxed text-ground/80">{s.text}</p>
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => go(Math.max(0, step - 1))} disabled={step === 0} className="nav-pill disabled:opacity-30">
          ← Back
        </button>
        <button type="button" onClick={() => setPaused((p) => !p)} className="nav-pill">
          {paused ? "Play" : "Pause"}
        </button>
        {last ? (
          <Link to={href.restore} className="cta-glow ml-auto">
            Restore a photo →
          </Link>
        ) : (
          <button type="button" onClick={() => go(step + 1)} className="cta-glow ml-auto">
            Next →
          </button>
        )}
      </div>
    </div>
  );
}
