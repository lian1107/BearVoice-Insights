import { useEffect, useState } from "react";

import { getSources } from "../api/client";
import type { SourceSummary } from "../api/types";


export function SourcesPage() {
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    getSources()
      .then(setSources)
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "来源加载失败");
      })
      .finally(() => setLoading(false));
  }, []);
  return (
    <div>
      <header className="page-heading">
        <div><p className="eyebrow">真实原声 · 可追溯</p><h1>数据资产</h1><p>核对每个来源批次的原始数、去重数与隔离数。</p></div>
      </header>
      {error ? <div role="alert" className="state-panel">{error}</div> : loading ? (
        <div role="status" className="state-panel">正在核对来源批次…</div>
      ) : (
        <div className="panel table-panel"><table><thead><tr><th>来源</th><th>渠道</th><th>健康状态</th><th>原始</th><th>去重</th><th>隔离</th></tr></thead><tbody>{sources.map((source) => <tr key={source.id}><td>{source.name}</td><td>{source.channel}</td><td>{source.connection_status}</td><td>{source.raw_count}</td><td>{source.deduplicated_count}</td><td>{source.quarantined_count}</td></tr>)}</tbody></table></div>
      )}
    </div>
  );
}
