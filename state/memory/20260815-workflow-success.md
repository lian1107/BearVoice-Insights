---
name: workflow-success-requires-persisted-evidence
description: 耐久工作流阶段必须核验真实持久化产物并写幂等账本；不允许用返回 completed 的空 Activity 代替业务完成。
type: architecture-pitfall
---

## 为什么

首轮架构审查发现，Temporal 编排、重试和人工暂停测试都能通过，但生产 Activity 只返回阶段名和 `completed`，没有读取或写入真实分析数据。这样验证的是“编排能走”，不是“业务阶段完成”，会在演示、恢复和审计中制造假成功。

## 怎么用

新增或修改工作流阶段时，成功条件必须能回到权威真相源：校验输入哈希、前置阶段、真实产物数量与关系约束，并把幂等键、事实摘要和完成阶段写回 `AnalysisRun.stage_status`。缺少产物要失败关闭；跳过阶段必须写明可验证原因，不能伪造默认结果。测试至少覆盖真实产物缺失、哈希漂移和同一幂等键重放。
