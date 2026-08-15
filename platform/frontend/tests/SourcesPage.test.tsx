import { expect, test } from "bun:test";
import { fireEvent, render, screen } from "@testing-library/react";

import type { SourceSummary, UploadAnalysisResult } from "../src/api/types";
import { SourcesPage } from "../src/pages/SourcesPage";


const source: SourceSummary = {
  id: "source-1",
  name: "路演文件上传",
  channel: "天猫",
  connection_status: "verified",
  raw_count: 3,
  deduplicated_count: 3,
  quarantined_count: 0,
};


test("operator uploads a real CSV and sees the backend pipeline result", async () => {
  const uploaded: string[] = [];
  const result: UploadAnalysisResult = {
    batch_id: "batch-1",
    analysis_run_id: "run-1",
    raw_count: 3,
    deduplicated_count: 3,
    quarantined_count: 0,
    signal_count: 3,
    cluster_count: 2,
    opportunity_count: 2,
    status: "pending_review",
    reused: false,
    analysis_mode: "offline_keyword_rules",
    model_calls: 0,
    notice: "本地规则基线已生成，主题与机会发布前必须人工复核",
  };
  render(
    <SourcesPage
      loadSources={async () => [source]}
      uploadCsv={async (file, command) => {
        uploaded.push(`${file.name}:${command.product}`);
        return result;
      }}
    />,
  );

  expect(await screen.findByText("路演文件上传")).toBeTruthy();
  const file = new File(
    ["原声id,原声内容,商品标题\n1,怎么清洗,养生壶"],
    "voices.csv",
    { type: "text/csv" },
  );
  fireEvent.change(screen.getByLabelText("客户原声 CSV"), {
    target: { files: [file] },
  });
  fireEvent.click(screen.getByRole("button", { name: "上传并开始分析" }));

  expect(await screen.findByText("分析基线已生成")).toBeTruthy();
  expect(screen.getAllByText("2", { selector: "strong" })).toHaveLength(2);
  expect(screen.getByText(result.notice)).toBeTruthy();
  expect(uploaded).toEqual(["voices.csv:养生壶"]);
});
