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

  await expect(page.getByRole("heading", { name: "产品决策驾驶舱" })).toBeVisible();
  await expect(page.getByText("赛事视图")).toHaveCount(0);
  await expect(page.getByText("企业视图")).toHaveCount(0);
  await expect(page.getByText("370", { exact: true })).toBeVisible();
  await expect(page.getByText("254 条含改进信号")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top 10 反馈聚类" })).toBeVisible();

  const dashboardResponse = apiResponses.find((item) => item.url.includes("/api/dashboard?"));
  expect(dashboardResponse).toBeTruthy();
  expect(dashboardResponse?.status).toBe(200);
  expect(dashboardResponse?.contentType).toContain("application/json");
  expect(dashboardResponse?.url.startsWith("http://127.0.0.1:4173/api/")).toBe(true);
  expect(new URL(dashboardResponse!.url).searchParams.has("view")).toBe(false);
});
