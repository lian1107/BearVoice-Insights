import { useState } from "react";

import type {
  OpportunityReviewCommand,
  OpportunityReviewResult,
} from "../api/types";


const DECISIONS: Array<{
  value: OpportunityReviewCommand["decision"];
  label: string;
  className: string;
}> = [
  { value: "approve", label: "接受机会", className: "button button--primary" },
  { value: "request_changes", label: "重大修改", className: "button" },
  { value: "reject", label: "驳回机会", className: "button button--danger" },
];


export function OpportunityReviewPanel({
  opportunityId,
  safetyEscalation,
  submitReview,
  onReviewed,
}: {
  opportunityId: string;
  safetyEscalation: boolean;
  submitReview: (
    id: string,
    command: OpportunityReviewCommand,
  ) => Promise<OpportunityReviewResult>;
  onReviewed: (result: OpportunityReviewResult) => void;
}) {
  const [reason, setReason] = useState("");
  const [owner, setOwner] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [externalReference, setExternalReference] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: OpportunityReviewCommand["decision"]) {
    if (!reason.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await submitReview(opportunityId, {
        decision,
        reason: reason.trim(),
        owner: owner.trim() || undefined,
        due_date: dueDate || undefined,
        external_reference: externalReference.trim() || undefined,
      });
      onReviewed(result);
      setReason("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "审核提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel review-panel" aria-labelledby="review-title">
      <header className="panel__header">
        <div><h2 id="review-title">人工审核</h2><p>所有决定都必须记录理由，不能只改状态。</p></div>
      </header>
      {safetyEscalation ? (
        <div className="safety-alert" role="alert">
          安全机会：接受后仍需品控复核，不得跳过安全验证。
        </div>
      ) : null}
      <label className="field field--wide">
        <span>审核理由</span>
        <textarea
          onChange={(event) => setReason(event.target.value)}
          placeholder="说明证据如何支持决定、还存在哪些限制"
          rows={4}
          value={reason}
        />
      </label>
      <div className="form-grid">
        <label className="field"><span>负责人（接受后）</span><input value={owner} onChange={(event) => setOwner(event.target.value)} /></label>
        <label className="field"><span>计划日期</span><input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label>
        <label className="field"><span>外部任务编号</span><input value={externalReference} onChange={(event) => setExternalReference(event.target.value)} /></label>
      </div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div className="review-actions">
        {DECISIONS.map((item) => (
          <button
            className={item.className}
            disabled={!reason.trim() || submitting}
            key={item.value}
            onClick={() => void decide(item.value)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
    </section>
  );
}
