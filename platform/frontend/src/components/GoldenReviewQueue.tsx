import { useState } from "react";

import type { GoldenReviewCommand, GoldenReviewItem } from "../api/types";


export function GoldenReviewQueue({
  initialItems,
  submitReview,
}: {
  initialItems: GoldenReviewItem[];
  submitReview: (id: string, command: GoldenReviewCommand) => Promise<GoldenReviewItem>;
}) {
  const [items, setItems] = useState(initialItems);
  const [activeId, setActiveId] = useState(initialItems[0]?.id ?? "");
  const [signal, setSignal] = useState("");
  const [objectName, setObjectName] = useState("");
  const [evidenceText, setEvidenceText] = useState("");
  const active = items.find((item) => item.id === activeId);

  async function submit() {
    if (!active || !signal.trim() || !evidenceText.trim()) return;
    const updated = await submitReview(active.id, {
      signal: signal.trim(),
      object_name: objectName.trim(),
      evidence_text: evidenceText.trim(),
    });
    setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
  }

  return (
    <div className="review-queue">
      <aside className="panel queue-list" aria-label="待定标样本">
        <h2>定标队列</h2>
        {items.map((item, index) => (
          <button aria-current={item.id === activeId ? "true" : undefined} key={item.id} onClick={() => setActiveId(item.id)} type="button">
            <span>样本 {String(index + 1).padStart(3, "0")}</span><small>{item.review_status}</small>
          </button>
        ))}
      </aside>
      {active ? (
        <section className="panel golden-editor">
          <div className="not-golden-notice">待人工定标 · 当前内容不是黄金真相</div>
          <blockquote>{active.redacted_input}</blockquote>
          <dl className="review-comparison">
            <div><dt>模型建议</dt><dd>{active.model_suggestion || "无预标注"}</dd></div>
            <div><dt>审核者一</dt><dd>{active.reviewer_one ?? "待提交"}</dd></div>
            <div><dt>审核者二</dt><dd>{active.reviewer_two ?? "待提交"}</dd></div>
            <div><dt>仲裁结果</dt><dd>{active.adjudication ?? "无"}</dd></div>
          </dl>
          <div className="form-grid">
            <label className="field"><span>信号类型</span><input value={signal} onChange={(event) => setSignal(event.target.value)} /></label>
            <label className="field"><span>对象</span><input value={objectName} onChange={(event) => setObjectName(event.target.value)} /></label>
            <label className="field field--wide"><span>直接证据片段</span><textarea rows={3} value={evidenceText} onChange={(event) => setEvidenceText(event.target.value)} /></label>
          </div>
          <button className="button button--primary" disabled={!signal.trim() || !evidenceText.trim()} onClick={() => void submit()} type="button">提交独立审核</button>
        </section>
      ) : <div className="state-panel">没有待审核样本</div>}
    </div>
  );
}
