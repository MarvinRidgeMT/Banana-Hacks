export function StubPage({ label, title }: { label: string; title: string }) {
  return (
    <section className="max-w-4xl">
      <p className="case-label">{label}</p>
      <h1 className="mt-3 font-serif text-5xl leading-[1.08] sm:text-6xl">{title}</h1>
    </section>
  );
}
