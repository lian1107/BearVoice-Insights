import { expect, test } from "bun:test";
import { fireEvent, render, screen } from "@testing-library/react";

import { App } from "../src/app/App";

test("local developer explicitly starts a secure session before seeing the workspace", async () => {
  const originalFetch = globalThis.fetch;
  let loggedIn = false;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/auth/options")) {
      return Response.json({ local_dev_session: true, oidc_configured: false });
    }
    if (url.endsWith("/api/auth/dev-session") && init?.method === "POST") {
      loggedIn = true;
      return Response.json({ mode: "local_development" }, { status: 201 });
    }
    if (url.endsWith("/api/auth/session")) {
      return loggedIn
        ? Response.json({
            subject: "local-dev-admin",
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
          })
        : Response.json({ detail: "身份凭证无效" }, { status: 401 });
    }
    return Response.json({ detail: "测试停止在工作区入口" }, { status: 503 });
  }) as typeof fetch;
  render(<App />);

  expect(await screen.findByRole("heading", { name: "本地开发登录" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "进入本地开发环境" }));

  const heading = await screen.findByRole("heading", { name: "产品机会决策平台" });

  expect(heading.hasAttribute("hidden")).toBe(false);
  expect(screen.getByText("模型外发受白名单与脱敏门禁控制").hasAttribute("hidden")).toBe(false);
  globalThis.fetch = originalFetch;
});
