import { expect, test } from "bun:test";
import { render, screen } from "@testing-library/react";

import type { ProductDecisionInsight } from "../src/api/types";
import { InsightsPage } from "../src/pages/InsightsPage";


const fixture: ProductDecisionInsight = {
  product: "养生壶",
  analysis_run_id: "run-insight-1",
  coverage: {
    total_voices: 370,
    total_signals: 254,
    period_start: "2026-08-01",
    period_end: "2026-08-03",
    days: 3,
    trend_allowed: false,
    channels: ["天猫", "京东"],
    has_business_denominator: false,
    denominator_notice: "缺少销量、成本、退货与维修分母。",
    limitations: ["仅支持样本内截面分析"],
  },
  dimensions: {
    channel: [{ value: "天猫", count: 210, percentage: 56.8, denominator: 370 }],
    sku: [{ value: "YSH-A1", count: 96, percentage: 25.9, denominator: 370 }],
    batch: [{ value: "2026-07", count: 51, percentage: 13.8, denominator: 370 }],
    version: [{ value: "V2", count: 82, percentage: 22.2, denominator: 370 }],
    lifecycle_stage: [{ value: "使用中", count: 173, percentage: 46.8, denominator: 370 }],
    risk_level: [{ value: "critical", count: 13, percentage: 3.5, denominator: 370 }],
  },
  patterns: [{
    pattern_id: "pattern-1",
    signal_type: "缺陷",
    object_name: "壶体",
    issue: "高温使用后炸裂",
    risk_level: "critical",
    voice_count: 13,
    share: 3.5,
    denominator: 370,
    channels: ["天猫", "京东"],
    skus: ["YSH-A1"],
    batches: ["2026-07"],
    versions: ["V2"],
    lifecycle_stages: ["使用中"],
    scenarios: ["连续加热"],
    latent_needs: ["高温安全"],
    root_cause_hypotheses: ["密封圈公差可能扩大热应力"],
    improvement_directions: ["复核密封结构和材料耐热规格"],
    validation_suggestions: ["按批次进行热循环对照试验"],
    missing_information: ["生产批次质检数据"],
    supporting_evidence_ids: ["evidence-1", "evidence-2"],
    conflict_notice: null,
  }],
  decision_cards: [{
    card_id: "decision-1",
    problem: "优先验证壶体高温炸裂风险",
    why_now: "涉及人身安全，优先级高于单纯声量排序。",
    evidence_level: "local_descriptive",
    risk_level: "critical",
    voice_count: 13,
    share: 3.5,
    recommended_direction: "暂停推断根因，先验证材料与密封结构。",
    validation_plan: "按版本和批次完成热循环实验，并由质量负责人签字。",
    human_owner: "质量负责人",
    human_review_required: true,
    forbidden_claims: ["不得宣称已证明密封圈是炸裂根因", "不得计算 ROI"],
    priority_explanation: "安全风险优先，其次为跨渠道覆盖。",
    supporting_evidence_ids: ["evidence-1", "evidence-2"],
  }],
  governance: {
    scope_notice: "结论仅适用于当前样本。",
    causality_notice: "相关性不代表因果。",
    financial_notice: "缺少经营分母，不计算损失和 ROI。",
    human_review_notice: "所有决策卡均需人工确认。",
  },
};


test("deep insight page turns sample evidence into governed product decision cards", async () => {
  const loadedProducts: string[] = [];
  render(<InsightsPage loadInsight={async (product) => {
    loadedProducts.push(product);
    return fixture;
  }} />);

  expect(await screen.findByRole("heading", { name: "产品决策洞察" })).toBeTruthy();
  expect(loadedProducts).toEqual(["养生壶"]);
  expect(screen.getByText("ROI 待补数据")).toBeTruthy();
  expect(screen.getByText("多维切片摘要")).toBeTruthy();
  expect(screen.getByText("优先验证壶体高温炸裂风险")).toBeTruthy();
  expect(screen.getByText(/支持证据 2 条/)).toBeTruthy();
  expect(screen.getByText("待验证根因假设")).toBeTruthy();
  expect(screen.getByText("密封圈公差可能扩大热应力")).toBeTruthy();
  expect(screen.getByText("质量负责人")).toBeTruthy();
  expect(screen.getByText(/不得宣称已证明密封圈是炸裂根因/)).toBeTruthy();
  expect(screen.queryByText(/¥|￥/)).toBeNull();
});
