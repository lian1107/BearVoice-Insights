import { useMemo, useState } from "react";

import type { TaxonomyRevisionCommand, TaxonomySummary } from "../api/types";


const OPERATIONS: Array<{ value: TaxonomyRevisionCommand["operation"]; label: string }> = [
  { value: "rename", label: "改名" },
  { value: "merge", label: "合并" },
  { value: "split", label: "拆分" },
  { value: "remove", label: "移出" },
  { value: "restore", label: "恢复" },
];


export function TaxonomyRevisionForm({
  taxonomy,
  submitRevision,
}: {
  taxonomy: TaxonomySummary;
  submitRevision: (id: string, command: TaxonomyRevisionCommand) => Promise<TaxonomySummary>;
}) {
  const [operation, setOperation] = useState<TaxonomyRevisionCommand["operation"]>("rename");
  const [clusterIds, setClusterIds] = useState("");
  const [newName, setNewName] = useState("");
  const [reason, setReason] = useState("");
  const [splitGroupsText, setSplitGroupsText] = useState("");
  const [result, setResult] = useState<TaxonomySummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const parsedClusterIds = useMemo(
    () => clusterIds.split(/[,\n]/).map((value) => value.trim()).filter(Boolean),
    [clusterIds],
  );
  const splitGroups = useMemo(() => {
    if (operation !== "split" || !splitGroupsText.trim()) return [];
    try {
      const parsed = JSON.parse(splitGroupsText) as Array<{ name?: unknown; signal_ids?: unknown }>;
      return Array.isArray(parsed)
        ? parsed.filter((item): item is { name: string; signal_ids: string[] } => (
            typeof item.name === "string"
            && Array.isArray(item.signal_ids)
            && item.signal_ids.every((value) => typeof value === "string")
          ))
        : [];
    } catch {
      return [];
    }
  }, [operation, splitGroupsText]);
  const hasOperationFields = operation === "remove" || operation === "restore"
    || (operation === "split" ? splitGroups.length >= 2 : Boolean(newName.trim()));
  const canSubmit = Boolean(reason.trim() && parsedClusterIds.length && hasOperationFields);

  async function submit() {
    if (!canSubmit) return;
    setError(null);
    try {
      setResult(await submitRevision(taxonomy.id, {
        operation,
        cluster_ids: parsedClusterIds,
        new_name: newName.trim(),
        reason: reason.trim(),
        split_groups: operation === "split" ? splitGroups : undefined,
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "分类法修订失败");
    }
  }

  return (
    <section className="panel revision-panel" aria-labelledby="revision-title">
      <header className="panel__header"><div><h2 id="revision-title">创建分类法修订</h2><p>当前版本只读，操作会生成带父版本的新草稿。</p></div></header>
      <div className="form-grid">
        <label className="field"><span>操作</span><select value={operation} onChange={(event) => setOperation(event.target.value as TaxonomyRevisionCommand["operation"])}>{OPERATIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label className="field field--wide"><span>聚类 ID（逗号或换行分隔）</span><textarea rows={3} value={clusterIds} onChange={(event) => setClusterIds(event.target.value)} /></label>
        <label className="field"><span>新名称 / 拆分目标</span><input value={newName} onChange={(event) => setNewName(event.target.value)} /></label>
        {operation === "split" ? (
          <label className="field field--wide"><span>拆分成员分组 JSON</span><textarea rows={5} placeholder='[{"name":"组一","signal_ids":["..."]},{"name":"组二","signal_ids":["..."]}]' value={splitGroupsText} onChange={(event) => setSplitGroupsText(event.target.value)} /></label>
        ) : null}
        <label className="field field--wide"><span>修订理由</span><textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      </div>
      <div className="revision-preview"><strong>版本预览</strong><span>{taxonomy.id.slice(0, 8)} → 新草稿</span><p>原版本继续保留，发布前还需人工复核。</p></div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {result ? <p className="form-success" role="status">已创建草稿版本 {result.id}</p> : null}
      <button className="button button--primary" disabled={!canSubmit} onClick={() => void submit()} type="button">创建修订草稿</button>
    </section>
  );
}
