import { useState } from "react";

/** The one comparison no other restorer can show: we removed part of Lincoln's face
 * ourselves, so we know the truth, and can set it beside the AI's three confident guesses.
 * Press and hold a guess to swap in the real face. */
const BASE = "/exhibits/lincoln_";

export function TrueFaceExhibit() {
  const [peek, setPeek] = useState<number | null>(null);
  const guesses = [1, 2, 3];
  return (
    <section>
      <p className="tag">The answer key</p>
      <h2 className="mt-5 font-serif text-4xl leading-tight sm:text-5xl">
        Three confident faces. <span className="text-invented">None of them is Lincoln's.</span>
      </h2>
      <p className="mt-4 max-w-[62ch] text-xl leading-relaxed text-body">
        We erased part of a public-domain Lincoln portrait ourselves, so for once the true face is known.
        Each of the AI's attempts produced a sharp, believable eye. Cold Case marked that area{" "}
        <span className="font-semibold text-invented">Invented</span>, because the attempts disagreed. Press
        and hold a guess to see the real face.
      </p>

      <div className="mt-10 grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-5">
        <Figure src={`${BASE}damaged.png`} label="The damaged scan" note="What the restorer is given" />
        <Figure src={`${BASE}true.png`} label="The truth" note="Removed by us, so we can check" accent="ink" />
        {guesses.map((g) => (
          <button
            key={g}
            type="button"
            className="text-left"
            onPointerDown={() => setPeek(g)}
            onPointerUp={() => setPeek(null)}
            onPointerLeave={() => setPeek(null)}
            onKeyDown={(e) => (e.key === " " || e.key === "Enter") && setPeek(g)}
            onKeyUp={() => setPeek(null)}
            aria-label={`Guess ${g}. Press and hold to compare with the real face.`}
          >
            <Figure
              src={peek === g ? `${BASE}true.png` : `${BASE}guess${g}.png`}
              label={peek === g ? "The truth" : `AI guess ${g}`}
              note={peek === g ? "Release to see the guess" : "Press and hold to compare"}
              accent={peek === g ? "ink" : "invented"}
            />
          </button>
        ))}
      </div>
      <p className="mt-6 max-w-[62ch] text-muted">
        Across our synthetic tests, pixels Cold Case labels Invented sit 1.8× further from the truth than
        pixels it labels Rebuilt. The label is a warning you can act on, not decoration.
      </p>
    </section>
  );
}

function Figure({ src, label, note, accent }: { src: string; label: string; note: string; accent?: "ink" | "invented" }) {
  return (
    <figure>
      <div className={`exhibit-frame overflow-hidden ${accent === "invented" ? "outline-2 outline-offset-4 outline-invented/60" : ""}`}>
        <img src={src} alt={label} className="block aspect-[265/343] w-full object-cover" draggable={false} />
      </div>
      <figcaption className="mt-3">
        <span className={`block font-semibold ${accent === "invented" ? "text-invented" : ""}`}>{label}</span>
        <span className="block text-sm text-muted">{note}</span>
      </figcaption>
    </figure>
  );
}
