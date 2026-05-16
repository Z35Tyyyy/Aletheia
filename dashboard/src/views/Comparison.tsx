/**
 * Comparison view.
 *
 * The single most defensible engineering artifact in the proposal: a
 * side-by-side of vector / hybrid / hybrid+rerank on the same question set.
 * If this view doesn't show hybrid+rerank winning, the architecture's
 * central claim is in trouble.
 *
 * Shows: a grouped bar chart across all metrics, a latency tradeoff card,
 * and the raw numbers in a table.
 */
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { EvalRun, listRuns } from "../api";

const STRATEGIES = ["vector", "hybrid", "hybrid_rerank"] as const;
type Strategy = (typeof STRATEGIES)[number];

const STRATEGY_LABEL: Record<Strategy, string> = {
  vector: "Vector only",
  hybrid: "Hybrid (no rerank)",
  hybrid_rerank: "Hybrid + Rerank",
};

const STRATEGY_COLOR: Record<Strategy, string> = {
  vector: "#888888",
  hybrid: "#3b6db5",
  hybrid_rerank: "#c8472b",
};

const METRIC_KEYS = [
  "context_precision",
  "context_recall",
  "faithfulness",
  "answer_relevancy",
  "citation_accuracy",
] as const;

export function Comparison() {
  const [runs, setRuns] = useState<EvalRun[]>([]);

  useEffect(() => {
    listRuns().then(setRuns);
  }, []);

  // Take the latest completed run per strategy.
  const latestByStrategy = useMemo(() => {
    const result: Partial<Record<Strategy, EvalRun>> = {};
    for (const s of STRATEGIES) {
      result[s] = runs
        .filter((r) => r.retrieval_strategy === s && r.status === "completed")
        .sort((a, b) => +new Date(b.started_at) - +new Date(a.started_at))[0];
    }
    return result;
  }, [runs]);

  const chartData = useMemo(() => {
    return METRIC_KEYS.map((m) => {
      const row: Record<string, number | string> = {
        metric: m.replace(/_/g, " "),
      };
      for (const s of STRATEGIES) {
        const r = latestByStrategy[s];
        if (r?.metrics) row[s] = r.metrics[m];
      }
      return row;
    });
  }, [latestByStrategy]);

  return (
    <>
      <header className="page-head">
        <h1 className="page-title">Comparison</h1>
        <p className="page-sub">
          Three retrieval strategies, same questions, same agent. Latency and
          quality move in opposite directions; this view exists to make the
          tradeoff visible.
        </p>
      </header>

      <div className="card">
        <div className="card-head">
          <h2 className="card-title">Quality metrics</h2>
          <span className="card-sub">{runs[0]?.metrics?.n_questions ?? 50} questions · latest run</span>
        </div>
        <div className="chart-wrap">
          <ResponsiveContainer>
            <BarChart data={chartData} margin={{ top: 16, right: 16, left: 0, bottom: 16 }}>
              <CartesianGrid stroke="var(--grid)" />
              <XAxis dataKey="metric" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} />
              <YAxis
                domain={[0, 1]}
                tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }}
                tickFormatter={(v) => v.toFixed(2)}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--paper)",
                  border: "1px solid var(--hairline)",
                  fontFamily: "IBM Plex Mono",
                  fontSize: 11,
                }}
                formatter={(v: number) => v.toFixed(3)}
              />
              <Legend wrapperStyle={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} />
              {STRATEGIES.map((s) => (
                <Bar key={s} dataKey={s} fill={STRATEGY_COLOR[s]} name={STRATEGY_LABEL[s]} isAnimationActive={false}>
                  {chartData.map((_, i) => (
                    <Cell key={i} fill={STRATEGY_COLOR[s]} />
                  ))}
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2 className="card-title">Latency & cost</h2>
          <span className="card-sub">milliseconds · USD per run</span>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Strategy</th>
              <th>p50 latency</th>
              <th>p95 latency</th>
              <th>Cost (USD)</th>
              <th>Cost / question</th>
            </tr>
          </thead>
          <tbody>
            {STRATEGIES.map((s) => {
              const r = latestByStrategy[s];
              const m = r?.metrics;
              if (!m) return null;
              return (
                <tr key={s}>
                  <td>
                    <span
                      style={{
                        display: "inline-block",
                        width: 8,
                        height: 8,
                        borderRadius: 4,
                        background: STRATEGY_COLOR[s],
                        marginRight: 8,
                        verticalAlign: 1,
                      }}
                    />
                    {STRATEGY_LABEL[s]}
                  </td>
                  <td className="num">{m.latency_p50_ms.toFixed(0)} ms</td>
                  <td className="num">{m.latency_p95_ms.toFixed(0)} ms</td>
                  <td className="num">${m.cost_usd_total.toFixed(3)}</td>
                  <td className="num">
                    ${(m.cost_usd_total / m.n_questions).toFixed(5)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
