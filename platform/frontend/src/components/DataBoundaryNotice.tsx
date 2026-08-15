import type { CoverageBoundary } from "../api/types";


function compactEndDate(value: string | null): string {
  return value ? value.slice(5) : "未知";
}


export function DataBoundaryNotice({
  coverage,
  sampleSize,
}: {
  coverage: CoverageBoundary;
  sampleSize: number;
}) {
  const channel = coverage.channel.endsWith("咨询")
    ? coverage.channel
    : `${coverage.channel}咨询`;
  const trendLabel = coverage.trend_allowed
    ? "可支持趋势判断"
    : "不支持趋势判断";
  return (
    <aside className="boundary-notice" aria-label="数据边界">
      <span className="boundary-notice__mark" aria-hidden="true">范围</span>
      <div>
        <strong>
          仅{channel} · {coverage.period_start ?? "未知"} 至{" "}
          {compactEndDate(coverage.period_end)} · {trendLabel}
        </strong>
        <p>
          当前分母 {sampleSize} 条去重原声。{coverage.limitation}。
        </p>
      </div>
    </aside>
  );
}
