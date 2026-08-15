import type { ClusterMetric } from "../api/types";


export function ClusterRanking({
  clusters,
  onSelect,
  subtitle,
}: {
  clusters: ClusterMetric[];
  onSelect?: (clusterId: string) => void;
  subtitle: string;
}) {
  const maximum = Math.max(...clusters.map((cluster) => cluster.count), 1);
  return (
    <section className="panel cluster-ranking" aria-labelledby="cluster-title">
      <header className="panel__header">
        <div>
          <h2 id="cluster-title">Top 10 反馈聚类</h2>
          <p>{subtitle}</p>
        </div>
        <span className="panel__unit">单位：条</span>
      </header>
      <ol className="ranking-list">
        {clusters.map((cluster, index) => (
          <li key={cluster.id}>
            <span className="ranking-list__rank">{String(index + 1).padStart(2, "0")}</span>
            <button
              className="ranking-list__name"
              onClick={() => onSelect?.(cluster.id)}
              type="button"
            >
              {cluster.name}
            </button>
            <div className="ranking-list__track">
              <span
                aria-label={`${cluster.name} ${cluster.count} 条，${cluster.percentage}%`}
                className="ranking-list__bar"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={maximum}
                aria-valuenow={cluster.count}
                style={{ width: `${(cluster.count / maximum) * 100}%` }}
              />
            </div>
            <strong>{cluster.count}</strong>
            <span className="ranking-list__percentage">{cluster.percentage}%</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
