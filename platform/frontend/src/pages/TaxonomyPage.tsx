import { useEffect, useState } from "react";

import { createTaxonomyRevision, getTaxonomies } from "../api/client";
import type { TaxonomyRevisionCommand, TaxonomySummary } from "../api/types";
import { TaxonomyRevisionForm } from "../components/TaxonomyRevisionForm";


export function TaxonomyPage({
  loadTaxonomies = getTaxonomies,
  submitRevision = createTaxonomyRevision,
}: {
  loadTaxonomies?: () => Promise<TaxonomySummary[]>;
  submitRevision?: (id: string, command: TaxonomyRevisionCommand) => Promise<TaxonomySummary>;
}) {
  const [taxonomies, setTaxonomies] = useState<TaxonomySummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadTaxonomies().then(setTaxonomies).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "分类法加载失败"));
  }, [loadTaxonomies]);
  const current = taxonomies[0];
  return (
    <div>
      <header className="page-heading"><div><p className="eyebrow">主题结构 · 版本留痕</p><h1>主题治理</h1><p>所有修订生成新版本，保留历史成员关系与理由。</p></div></header>
      {error ? <div className="state-panel" role="alert">{error}</div> : current ? (
        <div className="governance-grid">
          <section className="panel version-panel"><h2>当前版本</h2><strong>{current.id}</strong><dl><div><dt>状态</dt><dd>{current.status}</dd></div><div><dt>来源</dt><dd>{current.origin}</dd></div><div><dt>聚类</dt><dd>{current.cluster_count}</dd></div></dl></section>
          <TaxonomyRevisionForm submitRevision={submitRevision} taxonomy={current} />
        </div>
      ) : <div className="state-panel" role="status">正在读取分类法…</div>}
    </div>
  );
}
