import { useEffect, useState } from "react";

import {
  getEvidence,
  getOpportunities,
  getOpportunity,
  reviewOpportunity,
} from "../api/client";
import type {
  AuditEntry,
  EvidenceDetail,
  OpportunityDetail,
  OpportunityReviewCommand,
  OpportunityReviewResult,
  OpportunitySummary,
} from "../api/types";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { OpportunityReviewPanel } from "../components/OpportunityReviewPanel";


interface OpportunityPageProps {
  opportunityId?: string;
  loadOpportunity?: (id: string) => Promise<OpportunityDetail>;
  loadOpportunities?: () => Promise<OpportunitySummary[]>;
  loadEvidence?: (id: string, opportunityId?: string) => Promise<EvidenceDetail>;
  submitReview?: (
    id: string,
    command: OpportunityReviewCommand,
  ) => Promise<OpportunityReviewResult>;
}


export function OpportunityPage({
  opportunityId,
  loadOpportunity = getOpportunity,
  loadOpportunities = getOpportunities,
  loadEvidence = getEvidence,
  submitReview = reviewOpportunity,
}: OpportunityPageProps) {
  const [selectedId, setSelectedId] = useState(opportunityId ?? "");
  const [items, setItems] = useState<OpportunitySummary[]>([]);
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);
  const [evidence, setEvidence] = useState<EvidenceDetail[] | null>(null);
  const [loadingEvidence, setLoadingEvidence] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (opportunityId) {
      setSelectedId(opportunityId);
      return;
    }
    loadOpportunities()
      .then((result) => {
        setItems(result);
        setSelectedId((current) => current || result[0]?.id || "");
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "机会列表加载失败"));
  }, [loadOpportunities, opportunityId]);

  useEffect(() => {
    if (!selectedId) return;
    setDetail(null);
    setError(null);
    loadOpportunity(selectedId)
      .then(setDetail)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "机会加载失败"));
  }, [loadOpportunity, selectedId]);

  async function openEvidence() {
    if (!detail) return;
    setLoadingEvidence(true);
    setError(null);
    try {
      setEvidence(await Promise.all(detail.evidence_ids.map((id) => loadEvidence(id, detail.id))));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "证据加载失败");
    } finally {
      setLoadingEvidence(false);
    }
  }

  function reviewed(result: OpportunityReviewResult) {
    setDetail((current) => current ? {
      ...current,
      status: result.status,
      audit_timeline: [...current.audit_timeline, result.audit],
    } : current);
  }

  return (
    <div className="opportunity-page">
      <header className="page-heading"><div><p className="eyebrow">机会中心</p><h1>证据与人工审核</h1><p>先核对原声，再记录理由和决定。</p></div></header>
      {items.length ? (
        <label className="field opportunity-picker"><span>选择机会</span><select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{items.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      ) : null}
      {error ? <div className="state-panel" role="alert">{error}</div> : detail ? (
        <>
          <section className="opportunity-summary panel">
            <div><span className="tag tag--safety">{detail.severity ?? "待定级"}</span><span className="tag tag--neutral">{detail.status}</span></div>
            <h2>{detail.title}</h2>
            <p>{detail.problem}</p>
            <dl><div><dt>影响面</dt><dd>{detail.impact_scope ?? "待评估"}</dd></div><div><dt>安全等级</dt><dd>{detail.safety_level ?? "常规"}</dd></div></dl>
            <button className="button" disabled={loadingEvidence} onClick={() => void openEvidence()} type="button">{loadingEvidence ? "正在读取证据…" : `查看 ${detail.evidence_count} 条证据`}</button>
          </section>
          <div className="governance-grid">
            <OpportunityReviewPanel
              onReviewed={reviewed}
              opportunityId={detail.id}
              safetyEscalation={detail.safety_level === "critical"}
              submitReview={submitReview}
            />
            <AuditTimeline entries={detail.audit_timeline} />
          </div>
        </>
      ) : selectedId ? <div className="state-panel" role="status">正在加载机会…</div> : <div className="state-panel">暂无可审核机会</div>}
      {evidence ? <EvidenceDrawer evidence={evidence} onClose={() => setEvidence(null)} /> : null}
    </div>
  );
}


function AuditTimeline({ entries }: { entries: AuditEntry[] }) {
  return (
    <section className="panel audit-panel" aria-labelledby="audit-title">
      <header className="panel__header"><div><h2 id="audit-title">审计时间线</h2><p>决定、操作人和理由不可省略。</p></div></header>
      {entries.length ? <ol className="audit-list">{entries.map((entry) => <li key={entry.id}><strong>{entry.action}</strong><span>{entry.actor_id}</span><p>{entry.reason}</p><time>{entry.created_at}</time></li>)}</ol> : <p className="empty-copy">尚无审核决定。</p>}
    </section>
  );
}
