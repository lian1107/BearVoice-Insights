import type { EvidenceDetail } from "../api/types";


function directionLabel(value: EvidenceDetail["direction"]): string {
  return value === "oppose" ? "反对证据" : "支持证据";
}


export function EvidenceDrawer({
  evidence,
  onClose,
}: {
  evidence: EvidenceDetail[];
  onClose: () => void;
}) {
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        aria-label="机会证据"
        aria-modal="true"
        className="evidence-drawer"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className="drawer-header">
          <div><p className="eyebrow">证据链</p><h2>脱敏客户原声</h2></div>
          <button aria-label="关闭证据" onClick={onClose} type="button">关闭</button>
        </header>
        <p className="drawer-note">只展示脱敏文本、来源和分析版本，不返回原文件路径。</p>
        <div className="evidence-list">
          {evidence.map((item) => (
            <article key={item.id} className="evidence-item">
              <div className="evidence-item__meta">
                <span className={`tag ${item.direction === "oppose" ? "tag--neutral" : ""}`}>
                  {directionLabel(item.direction)}
                </span>
                <span>{item.signal_type} · {item.object_name ?? "未标注对象"}</span>
              </div>
              <blockquote>{item.quote}</blockquote>
              <dl>
                <div><dt>来源</dt><dd>来源：{item.source}</dd></div>
                <div><dt>日期</dt><dd>{item.occurred_at ? item.occurred_at.slice(0, 10) : "未知"}</dd></div>
                <div><dt>运行版本</dt><dd>{item.analysis_run_id}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </aside>
    </div>
  );
}
