import { useState } from "react";

import { DashboardPage } from "../pages/DashboardPage";
import { EvaluationPage } from "../pages/EvaluationPage";
import { OpportunityPage } from "../pages/OpportunityPage";
import { SourcesPage } from "../pages/SourcesPage";
import { SystemPage } from "../pages/SystemPage";
import { TaxonomyPage } from "../pages/TaxonomyPage";


export type UiPermission =
  | "read_voice"
  | "manage_sources"
  | "review_taxonomy"
  | "review_opportunity"
  | "manage_evaluation"
  | "admin";

type RouteKey = "dashboard" | "sources" | "taxonomy" | "opportunities" | "evaluation" | "system";

const routes: Array<{
  key: RouteKey;
  label: string;
  section: string;
  permission: UiPermission;
}> = [
  { key: "dashboard", label: "驾驶舱", section: "决策", permission: "read_voice" },
  { key: "sources", label: "原声数据", section: "资产", permission: "manage_sources" },
  { key: "taxonomy", label: "聚类治理", section: "治理", permission: "review_taxonomy" },
  { key: "opportunities", label: "机会中心", section: "决策", permission: "review_opportunity" },
  { key: "evaluation", label: "质量中心", section: "质量", permission: "manage_evaluation" },
  { key: "system", label: "系统管理", section: "系统", permission: "admin" },
];


function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="state-panel">
      <h1>{title}</h1>
      <p>工作区将在下一个实施单元接入审核操作。</p>
    </div>
  );
}


export function EnterpriseRouter({ permissions }: { permissions: UiPermission[] }) {
  const visibleRoutes = routes.filter((route) => permissions.includes(route.permission));
  const [active, setActive] = useState<RouteKey>(visibleRoutes[0]?.key ?? "dashboard");
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<string>();
  const content = active === "dashboard"
    ? (
        <DashboardPage
          onOpenOpportunities={(id) => {
            setSelectedOpportunityId(id);
            setActive("opportunities");
          }}
          onOpenTaxonomy={() => setActive("taxonomy")}
        />
      )
    : active === "sources"
      ? <SourcesPage />
      : active === "taxonomy"
        ? <TaxonomyPage />
        : active === "opportunities"
          ? <OpportunityPage opportunityId={selectedOpportunityId} />
          : active === "evaluation"
            ? <EvaluationPage />
      : active === "system"
        ? <SystemPage />
        : <PlaceholderPage title={routes.find((route) => route.key === active)?.label ?? "工作区"} />;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand__mark" aria-hidden="true">B</span><div><strong>BearVoice</strong><small>产品机会决策平台</small></div></div>
        <nav aria-label="主导航">
          {visibleRoutes.map((route) => (
            <button aria-current={active === route.key ? "page" : undefined} key={route.key} onClick={() => setActive(route.key)} type="button"><span>{route.label}</span><small>{route.section}</small></button>
          ))}
        </nav>
        <div className="sidebar__footer"><span className="status-dot" />私有化环境</div>
      </aside>
      <div className="workspace">
        <header className="topbar"><strong aria-level={1} role="heading">产品机会决策平台</strong><span role="status">模型外发默认关闭</span></header>
        <main className="content">{content}</main>
      </div>
    </div>
  );
}
