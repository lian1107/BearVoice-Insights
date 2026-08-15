import { expect, test } from "@playwright/test";

import { mockAuthenticatedAdmin } from "./mock-auth";


const dashboard = {
  product: "养生壶",
  analysis_run_id: "11111111-1111-1111-1111-111111111111",
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
    name: index === 0 ? "容量与尺寸预期" : `反馈聚类 ${index + 1}`,
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
    {
      id: "opportunity-2",
      title: "降低清洗与水垢维护成本",
      opportunity_type: "improvement",
      status: "draft",
      safety_level: null,
      priority_override: null,
      severity: "P1",
      impact_scope: "21 条，占 5.7%",
      evidence_count: 21,
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


test.beforeEach(async ({ page }) => {
  await mockAuthenticatedAdmin(page);
  await page.route("**/api/dashboard?**", async (route) => {
    await route.fulfill({ json: dashboard });
  });
});


test("decision dashboard keeps evidence and data boundaries visible", async ({ page }, testInfo) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "证据优先驾驶舱" })).toBeVisible();
  await expect(page.getByText("赛事视图")).toHaveCount(0);
  await expect(page.getByText("企业视图")).toHaveCount(0);
  await expect(page.getByText("254 条含改进信号")).toBeVisible();
  await expect(page.getByText(/仅天猫咨询.*不支持趋势判断/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top 10 反馈聚类" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "产品机会", exact: true })).toBeVisible();

  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(horizontalOverflow).toBeLessThanOrEqual(0);
  await testInfo.attach(`decision-dashboard-${testInfo.project.name}`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});
