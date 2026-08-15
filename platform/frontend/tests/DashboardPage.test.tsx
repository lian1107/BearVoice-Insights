import { expect, test } from "bun:test";
import { render, screen } from "@testing-library/react";

import type { DashboardSnapshot } from "../src/api/types";
import { DashboardPage } from "../src/pages/DashboardPage";


const fixture: DashboardSnapshot = {
  product: "养生壶",
  view: "competition",
  analysis_run_id: "run-1",
  total_voices: 370,
  actionable_voices: 254,
  denominator: 370,
  signals: [
    { signal_type: "预期", count: 136, percentage: 36.8, denominator: 370 },
    { signal_type: "咨询", count: 116, percentage: 31.4, denominator: 370 },
    { signal_type: "缺陷", count: 61, percentage: 16.5, denominator: 370 },
    { signal_type: "认知", count: 57, percentage: 15.4, denominator: 370 },
  ],
  top_clusters: Array.from({ length: 10 }, (_, index) => ({
    id: `cluster-${index}`,
    name: index === 0 ? "容量与尺寸预期" : `聚类 ${index + 1}`,
    signal_type: index === 0 ? "预期" : "咨询",
    count: 70 - index * 4,
    percentage: Number((((70 - index * 4) / 370) * 100).toFixed(1)),
    denominator: 370,
  })),
  opportunities: [
    {
      id: "opportunity-1",
      title: "优化壶体防炸裂和高温安全设计",
      opportunity_type: "improvement",
      status: "draft",
      safety_level: "critical",
      priority_override: "safety",
      severity: "P0",
      impact_scope: "13 条，占 3.5%",
      evidence_count: 13,
    },
  ],
  coverage: {
    channel: "天猫",
    period_start: "2026-08-01",
    period_end: "2026-08-03",
    days: 3,
    trend_allowed: false,
    limitation: "仅支持截面分析，不支持趋势、同比或环比判断",
  },
};


test("competition view leads with evidence-backed decision context", async () => {
  render(
    <DashboardPage
      initialView="competition"
      loadDashboard={async () => fixture}
    />,
  );

  expect(await screen.findByText("370")).toBeTruthy();
  expect(screen.getByText("254 条含改进信号")).toBeTruthy();
  expect(
    screen.getByText("仅天猫咨询 · 2026-08-01 至 08-03 · 不支持趋势判断"),
  ).toBeTruthy();
  expect(screen.getByRole("heading", { name: "产品机会" })).toBeTruthy();
  expect(screen.getAllByRole("progressbar")).toHaveLength(14);
});


test("cluster and opportunity controls open their governance workspaces", async () => {
  const openedClusters: string[] = [];
  const openedOpportunities: Array<string | undefined> = [];
  render(
    <DashboardPage
      initialView="competition"
      loadDashboard={async () => fixture}
      onOpenOpportunities={(id) => openedOpportunities.push(id)}
      onOpenTaxonomy={(id) => openedClusters.push(id)}
    />,
  );

  await screen.findByText("370");
  screen.getByRole("button", { name: "容量与尺寸预期" }).click();
  screen.getByRole("button", { name: "查看决策依据" }).click();
  screen.getByRole("button", { name: "进入机会中心" }).click();

  expect(openedClusters).toEqual(["cluster-0"]);
  expect(openedOpportunities).toEqual(["opportunity-1", undefined]);
});
