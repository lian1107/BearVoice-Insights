import type { Page } from "@playwright/test";


export async function mockAuthenticatedAdmin(page: Page) {
  await page.route("**/api/auth/session", (route) => route.fulfill({
    json: {
      subject: "e2e-admin",
      roles: ["admin"],
      permissions: [
        "read_voice",
        "manage_sources",
        "review_taxonomy",
        "review_opportunity",
        "manage_evaluation",
        "admin",
      ],
      product_lines: ["养生壶"],
    },
  }));
}
