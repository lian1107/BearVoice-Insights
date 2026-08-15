import type { ReactNode } from "react";

interface KpiItem {
  label: string;
  value: string | number;
  context: string;
  icon?: ReactNode;
  tone?: "default" | "attention" | "positive";
}


export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <section className="kpi-strip" aria-label="关键指标">
      {items.map((item) => (
        <article
          className={`kpi-card kpi-card--${item.tone ?? "default"}`}
          key={item.label}
        >
          <div className="kpi-card__top"><p className="kpi-card__label">{item.label}</p>{item.icon ? <span className="kpi-card__icon">{item.icon}</span> : null}</div>
          <strong className="kpi-card__value">{item.value}</strong>
          <p className="kpi-card__context">{item.context}</p>
        </article>
      ))}
    </section>
  );
}
