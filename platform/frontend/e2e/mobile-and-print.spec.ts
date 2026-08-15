import { expect, test } from "@playwright/test";

import { mockAuthenticatedAdmin } from "./mock-auth";


const dashboard = {
  product: "养生壶",
  view: "competition",
  analysis_run_id: "run-print",
  total_voices: 370,
  actionable_voices: 254,
  denominator: 370,
  signals: [
    { signal_type: "预期", count: 136, percentage: 36.8, denominator: 370 },
    { signal_type: "咨询", count: 116, percentage: 31.4, denominator: 370 },
    { signal_type: "缺陷", count: 61, percentage: 16.5, denominator: 370 },
    { signal_type: "认知", count: 57, percentage: 15.4, denominator: 370 },
  ],
  top_clusters: [{ id: "long-cluster", name: "玻璃壶身开裂炸裂与高温使用安全风险反馈", signal_type: "缺陷", count: 13, percentage: 3.5, denominator: 370 }],
  opportunities: [{ id: "op-1", title: "优化壶体防炸裂和高温安全设计", opportunity_type: "improvement", status: "pending_review", safety_level: "critical", priority_override: "safety", severity: "P0", impact_scope: "13 条，占 3.5%", evidence_count: 13 }],
  coverage: { channel: "天猫", period_start: "2026-08-01", period_end: "2026-08-03", days: 3, trend_allowed: false, limitation: "仅支持截面分析，不支持趋势、同比或环比判断" },
};


test("long labels, mobile width and print view preserve decision context", async ({ page }, testInfo) => {
  await mockAuthenticatedAdmin(page);
  await page.route("**/api/dashboard?**", (route) => route.fulfill({ json: dashboard }));
  await page.goto("/");

  const longLabel = page.getByRole("button", { name: dashboard.top_clusters[0].name });
  await expect(longLabel).toBeVisible();
  expect(await longLabel.evaluate((node) => getComputedStyle(node).whiteSpace)).toBe("normal");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);

  await page.emulateMedia({ media: "print" });
  await expect(page.getByLabel("主导航")).toBeHidden();
  await expect(page.getByText(/仅天猫咨询.*不支持趋势判断/)).toBeVisible();
  await testInfo.attach(`print-${testInfo.project.name}`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});
