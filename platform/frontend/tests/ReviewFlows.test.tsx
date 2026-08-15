import { expect, test } from "bun:test";
import { fireEvent, render, screen } from "@testing-library/react";

import type {
  AuditEntry,
  EvidenceDetail,
  GoldenReviewItem,
  OpportunityDetail,
  TaxonomySummary,
} from "../src/api/types";
import { EvaluationPage } from "../src/pages/EvaluationPage";
import { OpportunityPage } from "../src/pages/OpportunityPage";
import { TaxonomyPage } from "../src/pages/TaxonomyPage";


const opportunity: OpportunityDetail = {
  id: "glass-crack",
  title: "优化壶体防炸裂和高温安全设计",
  problem: "玻璃壶体在使用中存在炸裂反馈",
  status: "pending_review",
  opportunity_type: "improvement",
  safety_level: "critical",
  priority_override: "safety",
  severity: "P0",
  impact_scope: "13 条，占 3.5%",
  evidence_count: 13,
  evidence_ids: ["evidence-1"],
  audit_timeline: [],
};

const evidence: EvidenceDetail = {
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


test("reviewer can inspect evidence before accepting an opportunity", async () => {
  const submitted: string[] = [];
  render(
    <OpportunityPage
      loadEvidence={async () => evidence}
      loadOpportunity={async () => opportunity}
      opportunityId="glass-crack"
      submitReview={async (_id, command) => {
        submitted.push(command.reason);
        const audit: AuditEntry = {
          id: "audit-1",
          action: "opportunity.review",
          actor_id: "reviewer@example.com",
          reason: command.reason,
          created_at: "2026-08-15T17:00:00+08:00",
        };
        return { status: "accepted", audit };
      }}
    />,
  );

  fireEvent.click(await screen.findByRole("button", { name: "查看 13 条证据" }));
  expect(await screen.findByText("亲，我买的玻璃壶炸了一个")).toBeTruthy();
  expect(screen.getByText("来源：天猫咨询")).toBeTruthy();
  expect(screen.getByRole("button", { name: "接受机会" }).hasAttribute("disabled")).toBe(true);

  fireEvent.change(screen.getByLabelText("审核理由"), {
    target: { value: "涉及人身安全，转品控复核" },
  });
  const accept = screen.getByRole("button", { name: "接受机会" });
  expect(accept.hasAttribute("disabled")).toBe(false);
  fireEvent.click(accept);

  expect(await screen.findByText("reviewer@example.com")).toBeTruthy();
  expect(submitted).toEqual(["涉及人身安全，转品控复核"]);
});


test("taxonomy revision previews a new version instead of overwriting current state", async () => {
  const taxonomy: TaxonomySummary = {
    id: "taxonomy-current",
    status: "published",
    origin: "legacy_import",
    parent_version_id: null,
    cluster_count: 10,
  };
  const operations: string[] = [];
  render(
    <TaxonomyPage
      loadTaxonomies={async () => [taxonomy]}
      submitRevision={async (_id, command) => {
        operations.push(command.operation);
        return { ...taxonomy, id: "taxonomy-draft", status: "draft", parent_version_id: taxonomy.id };
      }}
    />,
  );

  expect(await screen.findByText("taxonomy-current")).toBeTruthy();
  expect(screen.getByText("原版本继续保留，发布前还需人工复核。")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("聚类 ID（逗号或换行分隔）"), { target: { value: "cluster-1" } });
  fireEvent.change(screen.getByLabelText("新名称 / 拆分目标"), { target: { value: "容量预期" } });
  fireEvent.change(screen.getByLabelText("修订理由"), { target: { value: "消除歧义" } });
  fireEvent.click(screen.getByRole("button", { name: "创建修订草稿" }));

  expect(await screen.findByText("已创建草稿版本 taxonomy-draft")).toBeTruthy();
  expect(operations).toEqual(["rename"]);
});


test("pending evaluation sample keeps model and human labels separate", async () => {
  const item: GoldenReviewItem = {
    id: "golden-1",
    redacted_input: "壶体用着裂了",
    model_suggestion: "候选：缺陷 / 玻璃壶体",
    reviewer_one: null,
    reviewer_two: null,
    adjudication: null,
    review_status: "pending_human_review",
    difficulty_tags: ["safety"],
  };
  render(
    <EvaluationPage
      loadQueue={async () => [item]}
      submitReview={async (_id, command) => ({
        ...item,
        reviewer_one: `${command.signal} / ${command.object_name}`,
        review_status: "pending_second_review",
      })}
    />,
  );

  expect(await screen.findByText("待人工定标 · 当前内容不是黄金真相")).toBeTruthy();
  expect(screen.getByText("候选：缺陷 / 玻璃壶体")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("信号类型"), { target: { value: "缺陷" } });
  fireEvent.change(screen.getByLabelText("对象"), { target: { value: "玻璃壶体" } });
  fireEvent.change(screen.getByLabelText("直接证据片段"), { target: { value: "壶体用着裂了" } });
  fireEvent.click(screen.getByRole("button", { name: "提交独立审核" }));

  expect(await screen.findByText("缺陷 / 玻璃壶体")).toBeTruthy();
  expect(screen.getByText("待提交")).toBeTruthy();
});
