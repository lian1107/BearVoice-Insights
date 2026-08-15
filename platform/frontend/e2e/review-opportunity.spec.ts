import { expect, test } from "@playwright/test";


const dashboard = {
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
  top_clusters: [{ id: "cluster-1", name: "安全与异常", signal_type: "缺陷", count: 13, percentage: 3.5, denominator: 370 }],
  opportunities: [{
    id: "glass-crack",
    title: "优化壶体防炸裂和高温安全设计",
    opportunity_type: "improvement",
    status: "pending_review",
    safety_level: "critical",
    priority_override: "safety",
    severity: "P0",
    impact_scope: "13 条，占 3.5%",
    evidence_count: 13,
  }],
  coverage: { channel: "天猫", period_start: "2026-08-01", period_end: "2026-08-03", days: 3, trend_allowed: false, limitation: "仅支持截面分析，不支持趋势、同比或环比判断" },
};

const opportunity = {
  ...dashboard.opportunities[0],
  problem: "玻璃壶体在使用中存在炸裂反馈",
  evidence_ids: ["evidence-1"],
  audit_timeline: [],
};

const evidence = {
  id: "evidence-1",
  quote: "亲，我买的玻璃壶炸了一个",
  voice_record_id: "voice-1",
  source: "天猫咨询",
  product: "养生壶",
  channel: "天猫",
  occurred_at: "2026-08-02T10:00:00+08:00",
  analysis_run_id: "run-1",
  signal_type: "缺陷",
  object_name: "玻璃壶体",
  privacy_status: "passed",
  direction: "support",
};


test("review decision appears in the audit timeline with its actor", async ({ page }) => {
  await page.route("**/api/dashboard?**", (route) => route.fulfill({ json: dashboard }));
  await page.route("**/api/opportunities/glass-crack", (route) => route.fulfill({ json: opportunity }));
  await page.route("**/api/evidence/evidence-1**", (route) => route.fulfill({ json: evidence }));
  await page.route("**/api/opportunities/glass-crack/reviews", async (route) => {
    const request = route.request().postDataJSON() as { reason: string };
    await route.fulfill({
      json: {
        status: "accepted",
        audit: {
          id: "audit-1",
          action: "opportunity.review",
          actor_id: "reviewer@example.com",
          reason: request.reason,
          created_at: "2026-08-15T17:00:00+08:00",
        },
      },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "查看决策依据" }).click();
  await expect(page.getByRole("heading", { name: "证据与人工审核" })).toBeVisible();
  await page.getByRole("button", { name: "查看 13 条证据" }).click();
  await expect(page.getByText("亲，我买的玻璃壶炸了一个")).toBeVisible();
  await expect(page.getByText("来源：天猫咨询")).toBeVisible();
  await page.getByRole("button", { name: "关闭证据" }).click();

  await page.getByLabel("审核理由").fill("涉及人身安全，转品控复核");
  await page.getByRole("button", { name: "接受机会" }).click();
  await expect(page.getByRole("heading", { name: "审计时间线" })).toBeVisible();
  await expect(page.getByText("reviewer@example.com")).toBeVisible();
  await expect(page.getByText("涉及人身安全，转品控复核")).toBeVisible();
});
