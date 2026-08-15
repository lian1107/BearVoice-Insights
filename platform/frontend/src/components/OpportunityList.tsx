import type { OpportunitySummary } from "../api/types";


function opportunityPriority(item: OpportunitySummary): string {
  if (item.priority_override === "safety" || item.safety_level === "critical") {
    return "安全优先";
  }
  return item.severity ?? "待定级";
}


const STATUS_ORDER: Record<string, number> = {
  pending_review: 0,
  draft: 1,
  accepted: 2,
  published: 3,
  rejected: 4,
};


function severityOrder(value: string | null): number {
  const match = value?.match(/P([0-3])/i);
  return match ? Number(match[1]) : 9;
}


export function OpportunityList({
  onOpenCenter,
  onSelect,
  opportunities,
}: {
  onOpenCenter?: () => void;
  onSelect?: (opportunityId: string) => void;
  opportunities: OpportunitySummary[];
}) {
  const ordered = [...opportunities].sort((left, right) => {
    const leftSafety = left.priority_override === "safety" ? 1 : 0;
    const rightSafety = right.priority_override === "safety" ? 1 : 0;
    return (
      rightSafety - leftSafety
      || (STATUS_ORDER[left.status] ?? 9) - (STATUS_ORDER[right.status] ?? 9)
      || severityOrder(left.severity) - severityOrder(right.severity)
      || right.evidence_count - left.evidence_count
    );
  });
  return (
    <section className="panel opportunity-panel" aria-labelledby="opportunity-title">
      <header className="panel__header">
        <div>
          <h2 id="opportunity-title">产品机会</h2>
          <p>安全覆盖优先，再结合审核状态与影响面排序；实施难度待人工评估</p>
        </div>
        <button className="text-button" onClick={onOpenCenter} type="button">进入产品机会</button>
      </header>
      <div className="opportunity-list">
        {ordered.slice(0, 3).map((item) => (
          <article className="opportunity-card" key={item.id}>
            <div className="opportunity-card__meta">
              <span
                className={
                  item.priority_override === "safety"
                    ? "tag tag--safety"
                    : "tag"
                }
              >
                {opportunityPriority(item)}
              </span>
              <span className="tag tag--neutral">{item.status}</span>
            </div>
            <h3>{item.title}</h3>
            <div className="opportunity-card__footer">
              <span>{item.impact_scope ?? `${item.evidence_count} 条独立证据`}</span>
              <button onClick={() => onSelect?.(item.id)} type="button">打开机会</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
