import { useEffect, useState } from "react";

import {
  createActionOutcome,
  createOpportunityAction,
  getEvidence,
  getOpportunities,
  getOpportunity,
  reviewOpportunity,
  transitionOpportunityAction,
} from "../api/client";
import type {
  ActionCreateCommand,
  ActionItem,
  ActionTransitionCommand,
  AuditEntry,
  EvidenceDetail,
  OpportunityDetail,
  OpportunityReviewCommand,
  OpportunityReviewResult,
  OpportunitySummary,
  OutcomeCreateCommand,
  OutcomeMeasurement,
} from "../api/types";
import { ActionOutcomePanel } from "../components/ActionOutcomePanel";
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
  createAction?: (id: string, command: ActionCreateCommand) => Promise<ActionItem>;
  transitionAction?: (
    opportunityId: string,
    actionId: string,
    command: ActionTransitionCommand,
  ) => Promise<ActionItem>;
  createOutcome?: (
    opportunityId: string,
    actionId: string,
    command: OutcomeCreateCommand,
  ) => Promise<OutcomeMeasurement>;
}


export function OpportunityPage({
  opportunityId,
  loadOpportunity = getOpportunity,
  loadOpportunities = getOpportunities,
  loadEvidence = getEvidence,
  submitReview = reviewOpportunity,
  createAction = createOpportunityAction,
  transitionAction = transitionOpportunityAction,
  createOutcome = createActionOutcome,
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
      actions: result.actions ?? current.actions,
      audit_timeline: [...current.audit_timeline, result.audit],
    } : current);
  }

  function updateActions(actions: ActionItem[]) {
    setDetail((current) => current ? { ...current, actions } : current);
    setItems((current) => current.map((item) => item.id === selectedId ? { ...item, actions } : item));
  }

  function pickerLabel(item: OpportunitySummary) {
    const compactTitle = item.title.length > 34 ? `${item.title.slice(0, 34)}…` : item.title;
    const execution = item.actions?.[0];
    return `${item.severity ?? "待定"} · ${execution ? `${execution.owner} / ${execution.status}` : "待建行动"} · ${compactTitle}`;
  }

  return (
    <div className="opportunity-page">
      <header className="page-heading"><div><p className="eyebrow">证据链 · 人工决策</p><h1>产品机会审核</h1><p>先核对原声，再记录理由和决定。</p></div></header>
      {items.length ? (
        <>
          <label className="field opportunity-picker"><span>选择机会</span><select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{items.map((item) => <option key={item.id} value={item.id}>{pickerLabel(item)}</option>)}</select></label>
          {!opportunityId ? <ExecutionOverview items={items} onSelect={setSelectedId} /> : null}
        </>
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
            {detail.status === "pending_review" ? (
              <OpportunityReviewPanel
                onReviewed={reviewed}
                opportunityId={detail.id}
                safetyEscalation={detail.safety_level === "critical"}
                submitReview={submitReview}
              />
            ) : <ActionOutcomePanel
              actions={detail.actions ?? []}
              createAction={createAction}
              createOutcome={createOutcome}
              onActionsChanged={updateActions}
              opportunityId={detail.id}
              opportunityStatus={detail.status}
              transitionAction={transitionAction}
            />}
            <AuditTimeline entries={detail.audit_timeline} />
          </div>
          {detail.status === "pending_review" && (detail.actions?.length ?? 0) > 0 ? (
            <ActionOutcomePanel
              actions={detail.actions ?? []}
              createAction={createAction}
              createOutcome={createOutcome}
              onActionsChanged={updateActions}
              opportunityId={detail.id}
              opportunityStatus={detail.status}
              transitionAction={transitionAction}
            />
          ) : null}
        </>
      ) : selectedId ? <div className="state-panel" role="status">正在加载机会…</div> : <div className="state-panel">暂无可审核机会</div>}
      {evidence ? <EvidenceDrawer evidence={evidence} onClose={() => setEvidence(null)} /> : null}
    </div>
  );
}


function ExecutionOverview({ items, onSelect }: {
  items: OpportunitySummary[];
  onSelect: (id: string) => void;
}) {
  const rows = items.flatMap((item) => (item.actions ?? []).map((action) => ({ item, action })));
  if (!rows.length) return null;
  return (
    <section className="panel execution-overview" aria-labelledby="execution-overview-title">
      <header className="panel__header"><div><h2 id="execution-overview-title">执行总览</h2><p>责任人、协作部门、目标、截止、状态和外部编号集中展示。</p></div></header>
      <div className="table-panel"><table><thead><tr><th>机会</th><th>负责人 / 协作</th><th>目标</th><th>截止 / 状态</th><th>外部编号</th></tr></thead><tbody>{rows.map(({ item, action }) => <tr key={action.id}><td><button className="text-button" onClick={() => onSelect(item.id)} type="button">{item.title}</button></td><td>{action.owner}<small>{action.collaborating_departments.join("、") || "无协作部门"}</small></td><td>{action.objective}</td><td>{action.due_at ? new Date(action.due_at).toLocaleDateString("zh-CN") : "待定"}<small>{action.status}</small></td><td>{action.external_reference || "未关联"}</td></tr>)}</tbody></table></div>
    </section>
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
