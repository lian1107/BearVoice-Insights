import { useEffect, useState } from "react";

import type {
  ActionCreateCommand,
  ActionItem,
  ActionItemStatus,
  ActionTransitionCommand,
  OutcomeCreateCommand,
  OutcomeMeasurement,
} from "../api/types";


const STATUS_LABELS: Record<ActionItemStatus, string> = {
  planned: "待启动",
  in_progress: "进行中",
  blocked: "受阻",
  completed: "已完成",
  cancelled: "已取消",
};

const NEXT_STATUSES: Record<ActionItemStatus, ActionItemStatus[]> = {
  planned: ["in_progress", "cancelled"],
  in_progress: ["blocked", "completed", "cancelled"],
  blocked: ["in_progress", "cancelled"],
  completed: [],
  cancelled: [],
};


export function ActionOutcomePanel({
  opportunityId,
  opportunityStatus,
  actions,
  createAction,
  transitionAction,
  createOutcome,
  onActionsChanged,
}: {
  opportunityId: string;
  opportunityStatus: string;
  actions: ActionItem[];
  createAction: (id: string, command: ActionCreateCommand) => Promise<ActionItem>;
  transitionAction: (
    opportunityId: string,
    actionId: string,
    command: ActionTransitionCommand,
  ) => Promise<ActionItem>;
  createOutcome: (
    opportunityId: string,
    actionId: string,
    command: OutcomeCreateCommand,
  ) => Promise<OutcomeMeasurement>;
  onActionsChanged: (actions: ActionItem[]) => void;
}) {
  const canCreate = ["accepted", "validating", "planned", "in_progress"].includes(opportunityStatus);
  const [showCreate, setShowCreate] = useState(false);
  const [owner, setOwner] = useState("");
  const [departments, setDepartments] = useState("");
  const [objective, setObjective] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [externalReference, setExternalReference] = useState("");
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submitAction() {
    if (!owner.trim() || !objective.trim() || !rationale.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const action = await createAction(opportunityId, {
        owner: owner.trim(),
        collaborating_departments: departments.split(/[，,]/).map((item) => item.trim()).filter(Boolean),
        objective: objective.trim(),
        due_date: dueDate || undefined,
        external_reference: externalReference.trim() || undefined,
        decision_rationale: rationale.trim(),
      });
      onActionsChanged([...actions, action]);
      setShowCreate(false);
      setOwner("");
      setDepartments("");
      setObjective("");
      setDueDate("");
      setExternalReference("");
      setRationale("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "行动创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel action-outcome-panel" aria-labelledby="action-outcome-title">
      <header className="panel__header">
        <div>
          <p className="eyebrow">责任闭环</p>
          <h2 id="action-outcome-title">行动与效果复盘</h2>
          <p>把机会落实到负责人、协作部门、目标和可核验指标。</p>
        </div>
        {canCreate ? <button className="button" onClick={() => setShowCreate((value) => !value)} type="button">{showCreate ? "取消" : "新增行动"}</button> : null}
      </header>

      {showCreate ? (
        <div className="execution-form">
          <div className="form-grid">
            <label className="field"><span>负责人 *</span><input aria-label="行动负责人" value={owner} onChange={(event) => setOwner(event.target.value)} /></label>
            <label className="field"><span>协作部门</span><input aria-label="协作部门" placeholder="研发，品质，客服" value={departments} onChange={(event) => setDepartments(event.target.value)} /></label>
            <label className="field"><span>截止日期</span><input aria-label="行动截止日期" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label>
            <label className="field field--wide"><span>行动目标 *</span><textarea aria-label="行动目标" rows={2} value={objective} onChange={(event) => setObjective(event.target.value)} /></label>
            <label className="field"><span>外部任务编号</span><input aria-label="行动外部任务编号" value={externalReference} onChange={(event) => setExternalReference(event.target.value)} /></label>
            <label className="field"><span>决策依据 *</span><input aria-label="行动决策依据" value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
          </div>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="button button--primary" disabled={submitting || !owner.trim() || !objective.trim() || !rationale.trim()} onClick={() => void submitAction()} type="button">创建行动</button>
        </div>
      ) : null}

      {actions.length ? (
        <div className="execution-list">
          {actions.map((action) => (
            <ActionCard
              action={action}
              createOutcome={createOutcome}
              key={action.id}
              onChanged={(updated) => onActionsChanged(actions.map((item) => item.id === updated.id ? updated : item))}
              opportunityId={opportunityId}
              transitionAction={transitionAction}
            />
          ))}
        </div>
      ) : <p className="empty-copy">尚未建立行动项。机会被接受后，应先明确负责人和验证目标。</p>}
    </section>
  );
}


function ActionCard({
  opportunityId,
  action,
  transitionAction,
  createOutcome,
  onChanged,
}: {
  opportunityId: string;
  action: ActionItem;
  transitionAction: (
    opportunityId: string,
    actionId: string,
    command: ActionTransitionCommand,
  ) => Promise<ActionItem>;
  createOutcome: (
    opportunityId: string,
    actionId: string,
    command: OutcomeCreateCommand,
  ) => Promise<OutcomeMeasurement>;
  onChanged: (action: ActionItem) => void;
}) {
  const nextStatuses = NEXT_STATUSES[action.status];
  const [nextStatus, setNextStatus] = useState<ActionItemStatus | "">(nextStatuses[0] ?? "");
  const [reason, setReason] = useState("");
  const [showOutcome, setShowOutcome] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNextStatus(NEXT_STATUSES[action.status][0] ?? "");
  }, [action.status]);

  async function move() {
    if (!nextStatus || !reason.trim()) return;
    setError(null);
    try {
      onChanged(await transitionAction(opportunityId, action.id, {
        target_status: nextStatus,
        reason: reason.trim(),
      }));
      setReason("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "状态更新失败");
    }
  }

  return (
    <article className="execution-card">
      <div className="execution-card__heading"><div><span className={`tag action-status action-status--${action.status}`}>{STATUS_LABELS[action.status]}</span><h3>{action.objective}</h3></div><span>{action.external_reference || "未关联外部任务"}</span></div>
      <dl className="execution-facts">
        <div><dt>负责人</dt><dd>{action.owner}</dd></div>
        <div><dt>协作部门</dt><dd>{action.collaborating_departments.length ? action.collaborating_departments.join("、") : "无"}</dd></div>
        <div><dt>截止时间</dt><dd>{action.due_at ? new Date(action.due_at).toLocaleDateString("zh-CN") : "待定"}</dd></div>
        <div><dt>决策依据</dt><dd>{action.decision_rationale}</dd></div>
      </dl>
      {nextStatuses.length ? (
        <div className="action-transition">
          <label className="field"><span>下一状态</span><select aria-label={`行动 ${action.objective} 下一状态`} value={nextStatus} onChange={(event) => setNextStatus(event.target.value as ActionItemStatus)}>{nextStatuses.map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}</select></label>
          <label className="field"><span>状态变化理由</span><input aria-label={`行动 ${action.objective} 状态变化理由`} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          <button className="button" disabled={!reason.trim()} onClick={() => void move()} type="button">更新状态</button>
        </div>
      ) : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}

      <div className="outcome-heading"><div><strong>结果指标</strong><span>人工录入的同期观察不能证明因果。</span></div>{action.status !== "cancelled" ? <button className="text-button" onClick={() => setShowOutcome((value) => !value)} type="button">{showOutcome ? "收起" : "新增指标"}</button> : null}</div>
      {showOutcome ? <OutcomeForm action={action} createOutcome={createOutcome} onChanged={onChanged} opportunityId={opportunityId} /> : null}
      {action.outcomes.length ? <div className="outcome-list">{action.outcomes.map((outcome) => <OutcomeCard key={outcome.id} outcome={outcome} />)}</div> : <p className="empty-copy">尚无结果指标，结项前至少记录一项。</p>}
    </article>
  );
}


function optionalNumber(value: string): number | undefined {
  return value.trim() === "" ? undefined : Number(value);
}


function OutcomeForm({ opportunityId, action, createOutcome, onChanged }: {
  opportunityId: string;
  action: ActionItem;
  createOutcome: (opportunityId: string, actionId: string, command: OutcomeCreateCommand) => Promise<OutcomeMeasurement>;
  onChanged: (action: ActionItem) => void;
}) {
  const [metricName, setMetricName] = useState("");
  const [definition, setDefinition] = useState("");
  const [unit, setUnit] = useState("");
  const [baseline, setBaseline] = useState("");
  const [target, setTarget] = useState("");
  const [actual, setActual] = useState("");
  const [window, setWindow] = useState("");
  const [conclusion, setConclusion] = useState("");
  const [limitations, setLimitations] = useState("");
  const [error, setError] = useState<string | null>(null);

  const complete = [metricName, definition, unit, window, conclusion, limitations].every((value) => value.trim());

  async function submit() {
    if (!complete) return;
    setError(null);
    try {
      const outcome = await createOutcome(opportunityId, action.id, {
        metric_name: metricName.trim(),
        metric_definition: definition.trim(),
        unit: unit.trim(),
        baseline_value: optionalNumber(baseline),
        target_value: optionalNumber(target),
        actual_value: optionalNumber(actual),
        observation_window: window.trim(),
        conclusion: conclusion.trim(),
        limitations: limitations.trim(),
      });
      onChanged({ ...action, outcomes: [...action.outcomes, outcome] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "指标保存失败");
    }
  }

  return (
    <div className="outcome-form">
      <div className="causality-notice" role="note"><strong>人工复盘</strong> 这里记录观察结果和限制，不能证明因果；标准未知时请明确填写“TBD”。</div>
      <div className="form-grid">
        <label className="field"><span>指标名称 *</span><input aria-label="指标名称" value={metricName} onChange={(event) => setMetricName(event.target.value)} /></label>
        <label className="field"><span>定义 *</span><input aria-label="指标定义" value={definition} onChange={(event) => setDefinition(event.target.value)} /></label>
        <label className="field"><span>单位 *</span><input aria-label="指标单位" value={unit} onChange={(event) => setUnit(event.target.value)} /></label>
        <label className="field"><span>基线</span><input aria-label="指标基线" inputMode="decimal" value={baseline} onChange={(event) => setBaseline(event.target.value)} /></label>
        <label className="field"><span>目标</span><input aria-label="指标目标" inputMode="decimal" value={target} onChange={(event) => setTarget(event.target.value)} /></label>
        <label className="field"><span>实际</span><input aria-label="指标实际" inputMode="decimal" value={actual} onChange={(event) => setActual(event.target.value)} /></label>
        <label className="field field--wide"><span>观察窗口 *</span><input aria-label="观察窗口" placeholder="例如：2026-09-01 至 2026-09-30" value={window} onChange={(event) => setWindow(event.target.value)} /></label>
        <label className="field field--wide"><span>人工结论 *</span><textarea aria-label="人工结果结论" rows={2} value={conclusion} onChange={(event) => setConclusion(event.target.value)} /></label>
        <label className="field field--wide"><span>限制与反证 *</span><textarea aria-label="结果限制" rows={2} value={limitations} onChange={(event) => setLimitations(event.target.value)} /></label>
      </div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <button className="button button--primary" disabled={!complete} onClick={() => void submit()} type="button">保存人工结果</button>
    </div>
  );
}


function OutcomeCard({ outcome }: { outcome: OutcomeMeasurement }) {
  const value = (number: number | null) => number === null ? "TBD" : `${number} ${outcome.unit}`;
  return (
    <article className="outcome-card">
      <div><strong>{outcome.metric_name}</strong><span>{outcome.observation_window}</span></div>
      <p>{outcome.metric_definition}</p>
      <dl><div><dt>基线</dt><dd>{value(outcome.baseline_value)}</dd></div><div><dt>目标</dt><dd>{value(outcome.target_value)}</dd></div><div><dt>实际</dt><dd>{value(outcome.actual_value)}</dd></div></dl>
      <p><strong>人工结论：</strong>{outcome.conclusion}</p>
      <p><strong>限制：</strong>{outcome.limitations}</p>
      <small>{outcome.recorded_by} 录入 · {outcome.causality_notice}</small>
    </article>
  );
}
