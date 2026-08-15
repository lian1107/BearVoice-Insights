import { expect, test } from "bun:test";
import { render, screen } from "@testing-library/react";

import { App } from "../src/app/App";

test("shows the enterprise product opportunity workspace", () => {
  render(<App />);

  const heading = screen.getByRole("heading", { name: "产品机会决策平台" });
  const securityStatus = screen.getByText("模型外发默认关闭");

  expect(heading.hasAttribute("hidden")).toBe(false);
  expect(securityStatus.hasAttribute("hidden")).toBe(false);
});
