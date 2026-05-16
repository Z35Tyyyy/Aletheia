/**
 * Trends view.
 *
 * Time series of a selected metric, faceted by retrieval strategy.
 * Deploy markers (vertical lines) are overlaid where eval_runs have a git_sha
 * different from the previous run — these are the "what shipped" moments
 * you want to correlate with metric movements.
 */
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { EvalRun, listRuns } from "../api";

const METRICS: Array<{ key: keyof MetricFlatRow; label: string }> = [
  { key: "context_precision", label: "Context Precision" },
  { key: "context_recall", label: "Context Recall" },
  { key: "faithfulness", label: "Faithfulness" },
  { key: "answer_relevancy", label: "Answer Relevancy" },
  { key: "citation_accuracy", label: "Citation Accuracy" },
];

const STRATEGY_COLOR: Record<string, string> = {
  vector: "#888888",
  hybrid: "#3b6db5",
  hybrid_rerank: "#c8472b",
};

interface MetricFlatRow {
  date: string;
  context_precision?: number;
  context_recall?: number;
  faithfulness?: number;
  answer_relevancy?: number;
  citation_accuracy?: number;
}

export function Trends() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [selectedMetric, setSelectedMetric] =
    useState<keyof MetricFlatRow>("context_recall");

  useEffect(() => {
    listRuns().then(setRuns);
  }, []);

  // Group runs by date + strategy; pivot into chart rows.
  const { chartData, deploys } = useMemo(() => {
    const byDate: Map<string, Record<string, number>> = new Map();
    const deploys: { date: string; sha: string }[] = [];
    let lastSha: string | null = null;

    const sorted = [...runs].sort(
      (a, b) => +new Date(a.started_at) - +new Date(b.started_at),
    );

    for (const r of sorted) {
      if (!r.metrics) continue;
      const date = r.started_at.slice(0, 10);
      const entry = byDate.get(date) ?? {};
      entry[`${r.retrieval_strategy}`] = r.metrics[selectedMetric] as number;
      byDate.set(date, entry);

      if (r.git_sha && r.git_sha !== lastSha) {
        deploys.push({ date, sha: r.git_sha });
        lastSha = r.git_sha;
      }
    }

    const chartData = Array.from(byDate.entries()).map(([date, vals]) => ({ date, ...vals }));
    return { chartData, deploys };
  }, [runs, selectedMetric]);

  const latest = runs[0]?.metrics;
  const prev = runs.find(
    (r) =>
      r.retrieval_strategy === runs[0]?.retrieval_strategy &&
      r.id !== runs[0]?.id,
  )?.metrics;

  return (
    <>
      <header className="page-head">
        <h1 className="page-title">Trends</h1>
        <p className="page-sub">
          Metrics over time, faceted by retrieval strategy. Deploy markers
          highlight where the underlying code or config changed.
        </p>
      </header>

      {latest && (
        <div className="metrics">
          {METRICS.map((m) => {
            const v = latest[m.key as keyof typeof latest] as number;
            const p = prev?.[m.key as keyof typeof prev] as number | undefined;
            const delta = p == null ? null : v - p;
            return (
              <div className="metric" key={m.key as string}>
                <div className="metric-label">{m.label}</div>
                <div className="metric-value">{(v * 100).toFixed(1)}</div>
                {delta != null && (
                  <div
                    className={`metric-delta ${delta >= 0 ? "up" : "down"}`}
                  >
                    {delta >= 0 ? "▲" : "▼"} {(delta * 100).toFixed(1)} pts
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="controls">
        {METRICS.map((m) => (
          <button
            key={m.key as string}
            className={`chip ${selectedMetric === m.key ? "active" : ""}`}
            onClick={() => setSelectedMetric(m.key)}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="card">
        <div className="card-head">
          <h2 className="card-title">
            {METRICS.find((m) => m.key === selectedMetric)?.label} — last 30 days
          </h2>
          <span className="card-sub">{chartData.length} runs · 3 strategies</span>
        </div>
        <div className="chart-wrap">
          <ResponsiveContainer>
            <LineChart data={chartData} margin={{ top: 16, right: 24, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="var(--grid)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} />
              <YAxis
                domain={[0.5, 1]}
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
              {deploys.map((d) => (
                <ReferenceLine
                  key={d.date + d.sha}
                  x={d.date}
                  stroke="var(--ink-faint)"
                  strokeDasharray="3 3"
                  label={{ value: d.sha.slice(0, 6), position: "top", className: "deploy-label" }}
                />
              ))}
              {(["vector", "hybrid", "hybrid_rerank"] as const).map((s) => (
                <Line
                  key={s}
                  type="monotone"
                  dataKey={s}
                  stroke={STRATEGY_COLOR[s]}
                  strokeWidth={s === "hybrid_rerank" ? 2.5 : 1.5}
                  dot={false}
                  name={s.replace("_", " + ")}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}
