/** Side-by-side: what a typical AI restorer gives you vs what Cold Case gives you. */
const ROWS: [string, string, string][] = [
  ["Lost detail", "Filled in silently, presented as the original", "Every pixel labelled Real, Rebuilt or Invented"],
  ["A damaged face", "One confident face", "When the attempts disagree, all three are shown and the face is marked Invented"],
  ["Undamaged areas", "Can be smoothed or regenerated along with the damage", "Copied byte for byte: 0 pixels changed outside the damage, tested"],
  ["Finding the damage", "Hidden, generic", "Our own trained detector proposes it; a person checks it; the receipt says who"],
  ["Proof afterwards", "None", "A signed C2PA receipt inside the file: every stage, setting and region"],
  ["Is the warning real?", "Not measured", "Measured: Invented pixels are 1.8× further from the truth than Rebuilt ones"],
];

export function Comparison() {
  return (
    <section>
      <p className="tag">Why it's different</p>
      <h2 className="mt-5 font-serif text-4xl leading-tight sm:text-5xl">
        Other restorers make it look right. <span className="text-invented">Cold Case tells you what's real.</span>
      </h2>
      <div className="mt-10 overflow-hidden rounded-sm border border-line">
        <div className="hidden grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_minmax(0,1.2fr)] bg-tag font-semibold sm:grid">
          <span className="px-5 py-3" />
          <span className="px-5 py-3 text-muted">A typical AI restorer</span>
          <span className="px-5 py-3">Cold Case</span>
        </div>
        {ROWS.map(([what, them, us]) => (
          <div key={what} className="grid gap-1 border-t border-line bg-surface px-5 py-4 first:border-t-0 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_minmax(0,1.2fr)] sm:gap-0 sm:px-0 sm:py-0 sm:first:border-t">
            <span className="font-semibold sm:px-5 sm:py-4">{what}</span>
            <span className="text-muted sm:px-5 sm:py-4"><span className="sm:hidden">Typical: </span>{them}</span>
            <span className="text-ink sm:border-l sm:border-line sm:bg-ground/60 sm:px-5 sm:py-4"><span className="font-semibold sm:hidden">Cold Case: </span>{us}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
