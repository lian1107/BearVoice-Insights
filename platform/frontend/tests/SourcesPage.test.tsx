import { expect, test } from "bun:test";
import { fireEvent, render, screen } from "@testing-library/react";

import type { CsvQualityPreview, SourceSummary, UploadAnalysisResult } from "../src/api/types";
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
  const previewed: string[] = [];
  const preview: CsvQualityPreview = {
    encoding: "utf-8",
    row_count: 3,
    columns: ["原声id", "原声内容", "商品标题"],
    required_fields_matched: true,
    missing_required_fields: [],
    mapping_suggestions: [
      { field: "voice_id", label: "原声 ID", required: true, suggested_column: "原声id", confidence: 1, method: "deterministic_alias_rules", reason: "列名命中已知别名" },
      { field: "text", label: "原声内容", required: true, suggested_column: "原声内容", confidence: 1, method: "deterministic_alias_rules", reason: "列名命中已知别名" },
      { field: "product", label: "商品标题", required: true, suggested_column: "商品标题", confidence: 1, method: "deterministic_alias_rules", reason: "列名命中已知别名" },
    ],
    column_mapping: { voice_id: "原声id", text: "原声内容", product: "商品标题" },
    column_profiles: [],
    date_parse_rate: null,
    duplicate_id_count: 0,
    exact_duplicate_count: 0,
    near_duplicate_or_template_count: 0,
    quality_hints: [],
    quarantined_count: 0,
    quarantine_reasons: [],
    suggestion_method: "deterministic_alias_rules",
    ai_used: false,
  };
  const result: UploadAnalysisResult = {
    batch_id: "batch-1",
    job_id: null,
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
    analysis_provider: "local",
    model_calls: 0,
    notice: "本地规则基线已生成，主题与机会发布前必须人工复核",
  };
  render(
    <SourcesPage
      loadSources={async () => [source]}
      loadProviders={async () => [{ provider: "local", configured: true, approved: true, model: "local-rule-baseline-v1" }]}
      previewCsv={async (file) => {
        previewed.push(file.name);
        return preview;
      }}
      uploadCsv={async (file, command) => {
        uploaded.push(`${file.name}:${command.product}:${command.columnMapping.text}`);
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
  expect(screen.getByRole("button", { name: "2. 确认映射并导入" }).hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "1. 预检数据" }));
  expect(await screen.findByLabelText("数据质量预检结果")).toBeTruthy();
  expect(screen.getByText("确定性别名规则 · 未调用 AI")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "2. 确认映射并导入" }));

  expect(await screen.findByText("可审核洞察已生成")).toBeTruthy();
  expect(screen.getAllByText("2", { selector: "strong" })).toHaveLength(2);
  expect(screen.getByText(result.notice)).toBeTruthy();
  expect(previewed).toEqual(["voices.csv"]);
  expect(uploaded).toEqual(["voices.csv:养生壶:原声内容"]);
});
