import type { SignalMetric } from "../api/types";


const SIGNAL_COLORS: Record<string, string> = {
  "预期": "#356ae6",
  "咨询": "#8da2c8",
  "缺陷": "#d87922",
  "认知": "#8a6fbc",
};


export function SignalComposition({
  signals,
  subtitle,
}: {
  signals: SignalMetric[];
  subtitle: string;
}) {
  return (
    <section className="panel signal-composition" aria-labelledby="signal-title">
      <header className="panel__header">
        <div>
          <h2 id="signal-title">信号构成</h2>
          <p>{subtitle}</p>
        </div>
      </header>
      <div className="composition-bar" aria-label="四类原声信号占比">
        {signals.map((signal) => (
          <div
            aria-label={`${signal.signal_type} ${signal.count} 条，${signal.percentage}%`}
            className="composition-bar__segment"
            key={signal.signal_type}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={signal.denominator}
            aria-valuenow={signal.count}
            style={{
              backgroundColor: SIGNAL_COLORS[signal.signal_type] ?? "#667085",
              width: `${signal.percentage}%`,
            }}
          />
        ))}
      </div>
      <ul className="signal-legend">
        {signals.map((signal) => (
          <li key={signal.signal_type}>
            <span
              className="signal-legend__swatch"
              style={{ backgroundColor: SIGNAL_COLORS[signal.signal_type] ?? "#667085" }}
            />
            <span>{signal.signal_type}</span>
            <strong>{signal.count} 条</strong>
            <span>{signal.percentage}%</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
