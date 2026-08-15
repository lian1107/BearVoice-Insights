import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Blocks,
  CheckCircle2,
  ClipboardCheck,
  Compass,
  DatabaseZap,
  ShieldAlert,
  UserRoundCheck,
} from "lucide-react";

import { getProductDecisionInsight } from "../api/client";
import type {
  DecisionDimensionKey,
  DecisionPattern,
  ProductDecisionCard,
  ProductDecisionInsight,
} from "../api/types";


const DIMENSIONS: Array<{ key: DecisionDimensionKey; label: string }> = [
  { key: "channel", label: "渠道" },
  { key: "sku", label: "SKU" },
  { key: "batch", label: "生产批次" },
  { key: "version", label: "产品版本" },
  { key: "lifecycle_stage", label: "使用阶段" },
  { key: "risk_level", label: "风险等级" },
];


interface InsightsPageProps {
  loadInsight?: (product: string) => Promise<ProductDecisionInsight>;
}


function compactDate(value: string | null): string {
  if (!value) return "日期未提供";
  return value.slice(0, 10);
}


function riskLabel(value: string): string {
  const labels: Record<string, string> = {
    critical: "关键风险",
    high: "高风险",
    medium: "中风险",
    low: "低风险",
    unknown: "风险待定",
  };
  return labels[value.toLowerCase()] ?? value;
}


function evidenceLevelLabel(value: ProductDecisionCard["evidence_level"]): string {
  return value === "local_descriptive" ? "样本内描述" : "方向性证据";
}


function relatedPattern(
  card: ProductDecisionCard,
  patterns: DecisionPattern[],
): DecisionPattern | undefined {
  const evidence = new Set(card.supporting_evidence_ids);
  return patterns.find((pattern) => pattern.supporting_evidence_ids.some((id) => evidence.has(id)));
}


function Tags({ label, values }: { label: string; values: string[] }) {
  if (!values.length) return null;
  return (
    <div className="decision-tags">
      <strong>{label}</strong>
      <span>{values.slice(0, 4).join("、")}{values.length > 4 ? ` 等 ${values.length} 项` : ""}</span>
    </div>
  );
}


function DecisionCard({
  card,
  index,
  pattern,
}: {
  card: ProductDecisionCard;
  index: number;
  pattern?: DecisionPattern;
}) {
  const isSafety = ["critical", "high"].includes(card.risk_level.toLowerCase());
  return (
    <article className={`product-decision-card${isSafety ? " product-decision-card--risk" : ""}`}>
      <div className="product-decision-card__rank" aria-label={`优先级 ${index + 1}`}>{String(index + 1).padStart(2, "0")}</div>
      <div className="product-decision-card__body">
        <header>
          <div className="product-decision-card__meta">
            <span className={isSafety ? "tag tag--safety" : "tag"}>{riskLabel(card.risk_level)}</span>
            <span className="tag tag--neutral">{evidenceLevelLabel(card.evidence_level)}</span>
            <span>{card.voice_count} 条去重原声 · 支持证据 {card.supporting_evidence_ids.length} 条 · 样本内 {card.share.toFixed(1)}%</span>
          </div>
          <h2>{card.problem}</h2>
          <p className="decision-why"><Compass aria-hidden="true" size={15} /><span><strong>为什么现在做：</strong>{card.why_now}</span></p>
        </header>

        <div className="decision-impact" aria-label="影响范围">
          <Tags label="渠道" values={pattern?.channels ?? []} />
          <Tags label="SKU" values={pattern?.skus ?? []} />
          <Tags label="批次" values={pattern?.batches ?? []} />
          <Tags label="版本" values={pattern?.versions ?? []} />
        </div>

        <div className="decision-workbench">
          <section>
            <h3><Blocks aria-hidden="true" size={15} />改进方向</h3>
            <p>{card.recommended_direction}</p>
            {pattern?.improvement_directions.length ? (
              <ul>{pattern.improvement_directions.slice(0, 3).map((item) => <li key={item}>{item}</li>)}</ul>
            ) : null}
          </section>
          <section>
            <h3><ClipboardCheck aria-hidden="true" size={15} />验证计划</h3>
            <p>{card.validation_plan}</p>
            {pattern?.validation_suggestions.length ? (
              <ul>{pattern.validation_suggestions.slice(0, 3).map((item) => <li key={item}>{item}</li>)}</ul>
            ) : null}
          </section>
        </div>

        {pattern?.root_cause_hypotheses.length ? (
          <section className="hypothesis-box">
            <h3><AlertTriangle aria-hidden="true" size={15} />待验证根因假设</h3>
            <p>以下内容是线索，不是已经证实的原因。</p>
            <ul>{pattern.root_cause_hypotheses.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
        ) : null}

        <footer className="decision-accountability">
          <div><UserRoundCheck aria-hidden="true" size={16} /><span><small>人工责任人</small><strong>{card.human_owner || "待指定"}</strong></span></div>
          <div><CheckCircle2 aria-hidden="true" size={16} /><span><small>优先级依据</small><strong>{card.priority_explanation}</strong></span></div>
          <div><DatabaseZap aria-hidden="true" size={16} /><span><small>仍需补充</small><strong>{pattern?.missing_information.join("；") || "由责任人核验样本与业务数据"}</strong></span></div>
        </footer>

        <div className="forbidden-claims">
          <ShieldAlert aria-hidden="true" size={15} />
          <div><strong>当前禁止下结论</strong><p>{card.forbidden_claims.length ? card.forbidden_claims.join("；") : "不得将样本内相关性表述为因果关系。"}</p></div>
        </div>
      </div>
    </article>
  );
}


export function InsightsPage({ loadInsight = getProductDecisionInsight }: InsightsPageProps) {
  const [insight, setInsight] = useState<ProductDecisionInsight | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    loadInsight("养生壶")
      .then((result) => active && setInsight(result))
      .catch((cause: unknown) => active && setError(cause instanceof Error ? cause.message : "深度洞察加载失败"));
    return () => { active = false; };
  }, [loadInsight]);

  const patternsByCard = useMemo(() => insight?.decision_cards.map(
    (card) => relatedPattern(card, insight.patterns),
  ) ?? [], [insight]);

  if (error) return <div className="state-panel" role="alert">{error}</div>;
  if (!insight) return <div className="state-panel" role="status">正在生成产品决策视图…</div>;

  return (
    <div className="insights-page">
      <header className="page-heading insight-heading">
        <div><p className="eyebrow">多维信号 · 产品改进</p><h1>产品决策洞察</h1><p>把分散原声转成可验证、可负责的产品改进决策。</p></div>
        <div className="insight-heading__scope"><strong>{insight.product}</strong><span>{insight.coverage.channels.join(" · ") || "渠道未提供"}</span></div>
      </header>

      <section className="insight-boundary" aria-label="分析边界">
        <div><span>分析范围</span><strong>{insight.coverage.total_voices} 条去重原声 / {insight.coverage.total_signals} 个信号</strong></div>
        <div><span>观察窗口</span><strong>{compactDate(insight.coverage.period_start)} 至 {compactDate(insight.coverage.period_end)} · {insight.coverage.days} 天</strong></div>
        <div><span>证据版本</span><strong>{insight.analysis_run_id}</strong></div>
      </section>

      <aside className="roi-boundary" role="note">
        <DatabaseZap aria-hidden="true" size={20} />
        <div><strong>ROI 待补数据</strong><p>{insight.coverage.denominator_notice} 当前不展示问题率、损失金额或 ROI，避免把原声占比误当经营结果。</p></div>
      </aside>

      <section className="dimension-section" aria-labelledby="dimension-heading">
        <div className="section-heading"><div><p className="eyebrow">问题雷达</p><h2 id="dimension-heading">多维切片摘要</h2></div><span>百分比均为当前去重样本内部占比</span></div>
        <div className="dimension-grid">
          {DIMENSIONS.map(({ key, label }) => {
            const slices = insight.dimensions[key].slice(0, 3);
            return (
              <article className="dimension-card" key={key}>
                <header><strong>{label}</strong><span>{insight.dimensions[key].length} 个切片</span></header>
                {slices.length ? <ol>{slices.map((slice) => (
                  <li key={slice.value}>
                    <div><span>{slice.value}</span><strong>{slice.count}</strong></div>
                    <span className="dimension-card__track"><i style={{ width: `${Math.min(100, slice.percentage)}%` }} /><small>{slice.percentage.toFixed(1)}%</small></span>
                  </li>
                ))}</ol> : <p>该维度尚无可用数据</p>}
              </article>
            );
          })}
        </div>
      </section>

      <section className="pattern-strip" aria-labelledby="patterns-heading">
        <div className="section-heading"><div><p className="eyebrow">交叉发现</p><h2 id="patterns-heading">高价值问题模式</h2></div><span>{insight.patterns.length} 个可追溯模式</span></div>
        {insight.patterns.length ? <div className="pattern-list">{insight.patterns.slice(0, 4).map((pattern) => (
          <article key={pattern.pattern_id}>
            <div><span className={pattern.risk_level === "critical" || pattern.risk_level === "high" ? "tag tag--safety" : "tag"}>{riskLabel(pattern.risk_level)}</span><small>{pattern.voice_count} 条 · {pattern.share.toFixed(1)}%</small></div>
            <h3>{pattern.object_name ? `${pattern.object_name} · ` : ""}{pattern.issue}</h3>
            <p>{[...pattern.channels, ...pattern.skus, ...pattern.versions].slice(0, 4).join(" / ") || "维度信息待补充"}</p>
            {pattern.conflict_notice ? <small className="pattern-conflict">{pattern.conflict_notice}</small> : null}
          </article>
        ))}</div> : <div className="state-panel">当前分析运行尚未形成跨维度模式。</div>}
      </section>

      <section className="decision-section" aria-labelledby="decisions-heading">
        <div className="section-heading"><div><p className="eyebrow">行动优先级</p><h2 id="decisions-heading">Top 产品决策卡</h2></div><span>安全风险优先，其次看样本内影响面与跨维覆盖</span></div>
        {insight.decision_cards.length ? <div className="product-decision-list">{insight.decision_cards.map((card, index) => (
          <DecisionCard card={card} index={index} key={card.card_id} pattern={patternsByCard[index]} />
        ))}</div> : <div className="state-panel">当前证据不足以生成产品决策卡，请先补充或审核数据。</div>}
      </section>

      <footer className="insight-governance">
        <strong>决策使用边界</strong>
        <ul><li>{insight.governance.scope_notice}</li><li>{insight.governance.causality_notice}</li><li>{insight.governance.financial_notice}</li><li>{insight.governance.human_review_notice}</li></ul>
      </footer>
    </div>
  );
}
