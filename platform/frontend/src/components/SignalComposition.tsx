import type { SignalMetric } from "../api/types";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";


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
  const chartData = [signals.reduce<Record<string, string | number>>((row, signal) => {
    row[signal.signal_type] = signal.count;
    return row;
  }, { name: "原声信号" })];
  return (
    <section className="panel signal-composition" aria-labelledby="signal-title">
      <header className="panel__header">
        <div>
          <h2 id="signal-title">信号构成</h2>
          <p>{subtitle}</p>
        </div>
      </header>
      <div className="signal-chart" aria-label="四类原声信号数量图表">
        <ResponsiveContainer width="100%" height="100%" minWidth={300}>
          <BarChart data={chartData} layout="vertical" margin={{ top: 8, right: 0, bottom: 8, left: 0 }}>
            <XAxis hide type="number" />
            <YAxis dataKey="name" hide type="category" />
            <Tooltip cursor={{ fill: "#f4f7fb" }} formatter={(value) => [`${value} 条`, "原声数量"]} />
            {signals.map((signal, index) => (
              <Bar
                dataKey={signal.signal_type}
                fill={SIGNAL_COLORS[signal.signal_type] ?? "#667085"}
                key={signal.signal_type}
                radius={index === 0 ? [6, 0, 0, 6] : index === signals.length - 1 ? [0, 6, 6, 0] : 0}
                stackId="signals"
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="signal-legend">
        {signals.map((signal) => (
          <li aria-label={`${signal.signal_type} ${signal.count} 条，${signal.percentage}%`} aria-valuemax={signal.denominator} aria-valuemin={0} aria-valuenow={signal.count} key={signal.signal_type} role="progressbar">
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
