import { useEffect, useState } from "react";

import { getDashboard } from "../api/client";
import type { DashboardSnapshot, DashboardView } from "../api/types";
import { ClusterRanking } from "../components/ClusterRanking";
import { DataBoundaryNotice } from "../components/DataBoundaryNotice";
import { KpiStrip } from "../components/KpiStrip";
import { OpportunityList } from "../components/OpportunityList";
import { SignalComposition } from "../components/SignalComposition";


interface DashboardPageProps {
  initialView?: DashboardView;
  loadDashboard?: (
    product: string,
    view: DashboardView,
  ) => Promise<DashboardSnapshot>;
  onOpenOpportunities?: (opportunityId?: string) => void;
  onOpenTaxonomy?: (clusterId: string) => void;
}


export function DashboardPage({
  initialView = "enterprise",
  loadDashboard = getDashboard,
  onOpenOpportunities,
  onOpenTaxonomy,
}: DashboardPageProps) {
  const [view, setView] = useState<DashboardView>(initialView);
  const [dashboard, setDashboard] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setError(null);
    loadDashboard("养生壶", view)
      .then((result) => active && setDashboard(result))
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "驾驶舱加载失败");
        }
      });
    return () => {
      active = false;
    };
  }, [loadDashboard, view]);

  if (error) {
    return <div className="state-panel" role="alert">{error}</div>;
  }
  if (!dashboard) {
    return <div className="state-panel" role="status">正在核对驾驶舱数据…</div>;
  }

  const chartSubtitle = `分母 ${dashboard.denominator} 条 · ${dashboard.coverage.period_start} 至 ${dashboard.coverage.period_end} · ${dashboard.coverage.channel}`;
  return (
    <div className="dashboard-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">养生壶 · 客户原声</p>
          <h1>产品决策驾驶舱</h1>
          <p>从真实需求到可审核机会，所有数字可下钻回证据。</p>
        </div>
        <div className="view-switch" aria-label="驾驶舱视图">
          <button
            aria-pressed={view === "competition"}
            onClick={() => setView("competition")}
            type="button"
          >
            赛事视图
          </button>
          <button
            aria-pressed={view === "enterprise"}
            onClick={() => setView("enterprise")}
            type="button"
          >
            企业视图
          </button>
        </div>
      </header>

      <DataBoundaryNotice
        coverage={dashboard.coverage}
        sampleSize={dashboard.denominator}
      />
      <KpiStrip
        items={[
          {
            label: "去重原声",
            value: dashboard.total_voices,
            context: `${dashboard.coverage.days} 天 · ${dashboard.coverage.channel}咨询`,
          },
          {
            label: "可行动原声",
            value: dashboard.actionable_voices,
            context: `${dashboard.actionable_voices} 条含改进信号`,
            tone: "attention",
          },
          {
            label: "主题聚类",
            value: dashboard.top_clusters.length,
            context: "覆盖全部 370 条原声",
          },
          {
            label: "待审核机会",
            value: dashboard.opportunities.length,
            context: "不以声量单独决定优先级",
          },
        ]}
      />

      <div className="dashboard-grid">
        <SignalComposition signals={dashboard.signals} subtitle={chartSubtitle} />
        <ClusterRanking
          clusters={dashboard.top_clusters}
          onSelect={onOpenTaxonomy}
          subtitle={chartSubtitle}
        />
      </div>
      <OpportunityList
        onOpenCenter={() => onOpenOpportunities?.()}
        onSelect={(id) => onOpenOpportunities?.(id)}
        opportunities={dashboard.opportunities}
      />
    </div>
  );
}
