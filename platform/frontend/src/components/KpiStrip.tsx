interface KpiItem {
  label: string;
  value: string | number;
  context: string;
  tone?: "default" | "attention";
}


export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <section className="kpi-strip" aria-label="关键指标">
      {items.map((item) => (
        <article
          className={`kpi-card ${item.tone === "attention" ? "kpi-card--attention" : ""}`}
          key={item.label}
        >
          <p className="kpi-card__label">{item.label}</p>
          <strong className="kpi-card__value">{item.value}</strong>
          <p className="kpi-card__context">{item.context}</p>
        </article>
      ))}
    </section>
  );
}
