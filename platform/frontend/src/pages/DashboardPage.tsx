import { lazy, Suspense, useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, Layers3, MessageSquareText, Search, Sparkles } from "lucide-react";

import { getDashboard } from "../api/client";
import type { DashboardSnapshot } from "../api/types";
import { ClusterRanking } from "../components/ClusterRanking";
import { DataBoundaryNotice } from "../components/DataBoundaryNotice";
import { KpiStrip } from "../components/KpiStrip";
import { OpportunityList } from "../components/OpportunityList";


const SignalComposition = lazy(async () => {
  const module = await import("../components/SignalComposition");
  return { default: module.SignalComposition };
});


interface DashboardPageProps {
  loadDashboard?: (product: string) => Promise<DashboardSnapshot>;
  onOpenOpportunities?: (opportunityId?: string) => void;
  onOpenTaxonomy?: (clusterId: string) => void;
}


export function DashboardPage({
  loadDashboard = getDashboard,
  onOpenOpportunities,
  onOpenTaxonomy,
}: DashboardPageProps) {
  const [dashboard, setDashboard] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let active = true;
    setError(null);
    loadDashboard("养生壶")
      .then((result) => active && setDashboard(result))
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "驾驶舱加载失败");
        }
      });
    return () => {
      active = false;
    };
  }, [loadDashboard]);

  if (error) {
    return <div className="state-panel" role="alert">{error}</div>;
  }
  if (!dashboard) {
    return <div className="state-panel" role="status">正在核对驾驶舱数据…</div>;
  }

  const chartSubtitle = `基于 ${dashboard.denominator} 条去重原声 · ${dashboard.coverage.channel}咨询`;
  const priorityOpportunity = dashboard.opportunities.find((item) => item.priority_override === "safety" || item.safety_level === "critical")
    ?? dashboard.opportunities.find((item) => /炸裂|开裂|召回/.test(item.title))
    ?? dashboard.opportunities.find((item) => /冒烟|漏电/.test(item.title))
    ?? [...dashboard.opportunities].sort((left, right) => {
      const leftPriority = Number(left.severity?.match(/P([0-3])/i)?.[1] ?? 9);
      const rightPriority = Number(right.severity?.match(/P([0-3])/i)?.[1] ?? 9);
      return leftPriority - rightPriority || right.evidence_count - left.evidence_count;
    })[0];
  const normalizedQuery = query.trim().toLowerCase();
  const visibleClusters = dashboard.top_clusters.filter((item) => item.name.toLowerCase().includes(normalizedQuery));
  const visibleOpportunities = dashboard.opportunities.filter((item) => item.title.toLowerCase().includes(normalizedQuery));
  return (
    <div className="dashboard-page">
      <div className="context-toolbar" aria-label="数据范围与搜索">
        <div className="context-toolbar__scope"><span>{dashboard.product}</span><span>{dashboard.coverage.channel}咨询</span><span>{dashboard.coverage.period_start} 至 {dashboard.coverage.period_end}</span></div>
        <label className="dashboard-search"><Search aria-hidden="true" size={16} /><span className="sr-only">搜索主题或机会</span><input aria-label="搜索主题或机会" onChange={(event) => setQuery(event.target.value)} placeholder="搜索主题或机会" type="search" value={query} /></label>
      </div>
      <header className="page-heading">
        <div>
          <p className="eyebrow">产品决策 · 客户证据</p>
          <h1>证据优先驾驶舱</h1>
          <p>先处理高影响风险，再用真实原声验证产品机会。</p>
        </div>
      </header>

      {priorityOpportunity ? (
        <section className="priority-hero" aria-labelledby="priority-title">
          <div className="priority-hero__icon"><AlertTriangle aria-hidden="true" size={23} /></div>
          <div className="priority-hero__body">
            <div className="priority-hero__meta"><span>当前最高优先级</span><span className="tag tag--safety">{priorityOpportunity.severity ?? "高风险"}</span></div>
            <h2 id="priority-title">{priorityOpportunity.title}</h2>
            <p>{priorityOpportunity.impact_scope ?? `${priorityOpportunity.evidence_count} 条独立证据`} · 安全风险优先于声量排序，需人工确认处置。</p>
          </div>
          <button className="button button--priority" onClick={() => onOpenOpportunities?.(priorityOpportunity.id)} type="button">查看决策依据<ArrowRight aria-hidden="true" size={16} /></button>
        </section>
      ) : null}

      <KpiStrip
        items={[
          {
            label: "去重原声",
            value: dashboard.total_voices,
            context: `${dashboard.coverage.days} 天 · ${dashboard.coverage.channel}咨询`,
            icon: <MessageSquareText aria-hidden="true" size={19} />,
          },
          {
            label: "可行动原声",
            value: dashboard.actionable_voices,
            context: `${dashboard.actionable_voices} 条含改进信号`,
            tone: "attention",
            icon: <Sparkles aria-hidden="true" size={19} />,
          },
          {
            label: "主题聚类",
            value: dashboard.top_clusters.length,
            context: `覆盖全部 ${dashboard.denominator} 条原声`,
            icon: <Layers3 aria-hidden="true" size={19} />,
          },
          {
            label: "待审核机会",
            value: dashboard.opportunities.length,
            context: "不以声量单独决定优先级",
            tone: "positive",
            icon: <AlertTriangle aria-hidden="true" size={19} />,
          },
        ]}
      />

      <DataBoundaryNotice coverage={dashboard.coverage} sampleSize={dashboard.denominator} />

      <div className="dashboard-grid">
        <Suspense fallback={<section className="panel state-panel" role="status">正在加载信号图…</section>}>
          <SignalComposition signals={dashboard.signals} subtitle={chartSubtitle} />
        </Suspense>
        <ClusterRanking
          clusters={visibleClusters}
          onSelect={onOpenTaxonomy}
          subtitle={chartSubtitle}
        />
      </div>
      <OpportunityList
        onOpenCenter={() => onOpenOpportunities?.()}
        onSelect={(id) => onOpenOpportunities?.(id)}
        opportunities={visibleOpportunities}
      />
    </div>
  );
}
