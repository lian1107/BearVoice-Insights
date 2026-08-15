import { expect, test } from "@playwright/test";


test("local login loads canonical kettle data through the real compose stack", async ({ page }) => {
  const apiResponses: Array<{ url: string; status: number; contentType: string | null }> = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/")) {
      apiResponses.push({
        url: response.url(),
        status: response.status(),
        contentType: response.headers()["content-type"] ?? null,
      });
    }
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "本地开发登录" })).toBeVisible();
  await page.getByRole("button", { name: "进入本地开发环境" }).click();

  await expect(page.getByRole("heading", { name: "证据优先驾驶舱" })).toBeVisible();
  await expect(page.getByText("赛事视图")).toHaveCount(0);
  await expect(page.getByText("企业视图")).toHaveCount(0);
  const deduplicatedMetric = page.getByRole("article").filter({ hasText: "去重原声" });
  await expect(deduplicatedMetric.locator("strong")).toHaveText(/^[1-9]\d*$/);
  await expect(page.getByText(/\d+ 条含改进信号/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top 10 反馈聚类" })).toBeVisible();

  const dashboardResponse = apiResponses.find((item) => item.url.includes("/api/dashboard?"));
  expect(dashboardResponse).toBeTruthy();
  expect(dashboardResponse?.status).toBe(200);
  expect(dashboardResponse?.contentType).toContain("application/json");
  expect(dashboardResponse?.url.startsWith("http://127.0.0.1:4173/api/")).toBe(true);
  expect(new URL(dashboardResponse!.url).searchParams.has("view")).toBe(false);
});


test("real compose previews CSV mapping and exposes only approved analysis engines", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "进入本地开发环境" }).click();
  await expect(page.getByRole("heading", { name: "证据优先驾驶舱" })).toBeVisible();

  await page.getByRole("button", { name: "数据接入", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "数据接入与分析" })).toBeVisible();
  await page.getByLabel("客户原声 CSV").setInputFiles("e2e/fixtures/roadshow-upload.csv");
  await page.getByRole("button", { name: "1. 预检数据" }).click();

  await expect(page.getByLabel("数据质量预检结果")).toBeVisible();
  await expect(page.getByText("确定性别名规则 · 未调用 AI")).toBeVisible();
  await expect(page.getByLabel("原声 ID映射")).toHaveValue("原声id");
  await expect(page.getByLabel("原声内容映射")).toHaveValue("原声内容");

  const engine = page.getByLabel("分析引擎");
  await expect(engine).toHaveValue("local");
  const providerResponse = await page.request.get("/api/analysis/providers");
  expect(providerResponse.status()).toBe(200);
  const providers = await providerResponse.json() as Array<{
    provider: string;
    configured: boolean;
    approved: boolean;
    model: string;
  }>;
  expect(JSON.stringify(providers)).not.toMatch(/api_key|base_url/i);
  for (const provider of providers) {
    const providerOption = engine.locator(`option[value="${provider.provider}"]`);
    if (provider.configured && provider.approved) {
      await expect(providerOption).not.toHaveAttribute("disabled", "");
    } else {
      await expect(providerOption).toHaveAttribute("disabled", "");
    }
  }
});


test("real compose turns canonical evidence into bounded product decision insights", async ({ page }) => {
  const apiResponses: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/insights/decision")) {
      apiResponses.push(`${response.status()}:${response.url()}`);
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "进入本地开发环境" }).click();
  await page.getByRole("button", { name: "产品决策洞察", exact: true }).first().click();

  await expect(page.getByRole("heading", { name: "产品决策洞察" })).toBeVisible();
  await expect(page.getByText("ROI 待补数据")).toBeVisible();
  await expect(page.getByRole("heading", { name: "多维切片摘要" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top 产品决策卡" })).toBeVisible();
  await expect(page.getByText(/\d+ 条去重原声 \/ \d+ 个信号/)).toBeVisible();
  await expect(page.getByText(/成本与 ROI 因缺经营分母为 TBD/).first()).toBeVisible();
  await expect(page.locator("main")).not.toContainText(/¥|￥/);
  expect(apiResponses.some((item) => item.startsWith("200:http://127.0.0.1:4173/api/"))).toBe(true);
});
