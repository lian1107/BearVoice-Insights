import { useState } from "react";
import {
  BadgeCheck,
  ChartNoAxesCombined,
  Database,
  LayoutDashboard,
  Lightbulb,
  Menu,
  ShieldCheck,
  Tags,
  X,
  type LucideIcon,
} from "lucide-react";

import { DashboardPage } from "../pages/DashboardPage";
import { EvaluationPage } from "../pages/EvaluationPage";
import { InsightsPage } from "../pages/InsightsPage";
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

type RouteKey = "dashboard" | "insights" | "sources" | "taxonomy" | "opportunities" | "evaluation" | "system";

const routes: Array<{
  key: RouteKey;
  label: string;
  group: "决策" | "数据" | "治理";
  permission: UiPermission;
  icon: LucideIcon;
}> = [
  { key: "dashboard", label: "决策总览", group: "决策", permission: "read_voice", icon: LayoutDashboard },
  { key: "insights", label: "产品决策洞察", group: "决策", permission: "read_voice", icon: ChartNoAxesCombined },
  { key: "opportunities", label: "产品机会", group: "决策", permission: "review_opportunity", icon: Lightbulb },
  { key: "sources", label: "数据接入", group: "数据", permission: "manage_sources", icon: Database },
  { key: "taxonomy", label: "主题治理", group: "数据", permission: "review_taxonomy", icon: Tags },
  { key: "evaluation", label: "质量评测", group: "治理", permission: "manage_evaluation", icon: BadgeCheck },
  { key: "system", label: "系统状态", group: "治理", permission: "admin", icon: ShieldCheck },
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const routeGroups = ["决策", "数据", "治理"] as const;
  const primaryMobileRoutes = visibleRoutes.filter((route) => ["dashboard", "insights", "opportunities", "sources"].includes(route.key));
  const secondaryMobileRoutes = visibleRoutes.filter((route) => !primaryMobileRoutes.includes(route));

  function navigate(key: RouteKey) {
    setActive(key);
    setMobileMenuOpen(false);
  }
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
      : active === "insights"
        ? <InsightsPage />
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
          {routeGroups.map((group) => {
            const groupRoutes = visibleRoutes.filter((route) => route.group === group);
            return groupRoutes.length ? (
              <div className="nav-group" key={group}>
                <p>{group}</p>
                {groupRoutes.map((route) => {
                  const Icon = route.icon;
                  return (
                    <button aria-current={active === route.key ? "page" : undefined} key={route.key} onClick={() => navigate(route.key)} type="button">
                      <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
                      <span>{route.label}</span>
                    </button>
                  );
                })}
              </div>
            ) : null;
          })}
        </nav>
        <div className="sidebar__footer"><span className="status-dot" />私有化环境</div>
      </aside>
      <div className="workspace">
        <header className="topbar"><strong aria-label="产品机会决策平台" aria-level={1} role="heading">{routes.find((route) => route.key === active)?.label}</strong><span role="status"><ShieldCheck aria-hidden="true" size={14} />模型外发受白名单与脱敏门禁控制</span></header>
        <main className="content">{content}</main>
      </div>
      {mobileMenuOpen ? (
        <div className="mobile-more-sheet" role="dialog" aria-label="更多导航" aria-modal="true">
          <div className="mobile-more-sheet__header"><strong>更多工作区</strong><button aria-label="关闭更多导航" onClick={() => setMobileMenuOpen(false)} type="button"><X size={20} /></button></div>
          {secondaryMobileRoutes.map((route) => {
            const Icon = route.icon;
            return <button key={route.key} onClick={() => navigate(route.key)} type="button"><Icon size={19} /><span>{route.label}</span></button>;
          })}
        </div>
      ) : null}
      <nav className="mobile-nav" aria-label="移动端主导航">
        {primaryMobileRoutes.map((route) => {
          const Icon = route.icon;
          return <button aria-current={active === route.key ? "page" : undefined} key={route.key} onClick={() => navigate(route.key)} type="button"><Icon size={19} /><span>{route.label}</span></button>;
        })}
        {secondaryMobileRoutes.length ? <button aria-expanded={mobileMenuOpen} onClick={() => setMobileMenuOpen((open) => !open)} type="button"><Menu size={19} /><span>更多</span></button> : null}
      </nav>
    </div>
  );
}
