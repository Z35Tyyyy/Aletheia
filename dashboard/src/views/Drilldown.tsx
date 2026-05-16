/**
 * Drilldown view.
 *
 * Given one question, show: the retrieved chunks (ranked, with highlights
 * on relevant sentences), the generated answer with citation badges, and
 * the per-question metric values.
 *
 * This is where you'd go to debug an individual regression. The mock here
 * uses a representative question; in production this view would be
 * populated by selecting a question from the eval_results table.
 */
import { useEffect, useState } from "react";

import { Chunk, EvalResult, getResult } from "../api";

const METRIC_ORDER = [
  ["context_precision", "Context Precision"],
  ["context_recall", "Context Recall"],
  ["faithfulness", "Faithfulness"],
  ["answer_relevancy", "Answer Relevancy"],
  ["citation_accuracy", "Citation Accuracy"],
] as const;

export function Drilldown() {
  const [data, setData] = useState<{ result: EvalResult; chunks: Chunk[] } | null>(null);

  useEffect(() => {
    getResult("hybrid_rerank-0", "q1").then(setData);
  }, []);

  if (!data) return <div className="empty">Loading…</div>;
  const { result, chunks } = data;

  return (
    <>
      <header className="page-head">
        <h1 className="page-title">Drilldown</h1>
        <p className="page-sub">
          One question, every artifact: the question, the retrieved chunks (with
          relevant sentences highlighted), the generated answer, and the metric
          values. This is the regression-debugging view.
        </p>
      </header>

      <div className="card">
        <div className="card-head">
          <h2 className="card-title">Question</h2>
          <span className="card-sub">id · {result.question_id}</span>
        </div>
        <p style={{ fontSize: 18, fontFamily: "Fraunces, serif", margin: 0 }}>
          {result.question}
        </p>
      </div>

      <div className="card">
        <div className="card-head">
          <h2 className="card-title">Retrieved chunks</h2>
          <span className="card-sub">top {chunks.length} after rerank</span>
        </div>
        {chunks.map((c, idx) => (
          <ChunkBlock key={c.id} chunk={c} index={idx} question={result.question ?? ""} />
        ))}
      </div>

      <div className="card">
        <div className="card-head">
          <h2 className="card-title">Generated answer</h2>
          <span className="card-sub">{result.latency_ms} ms</span>
        </div>
        <div className="answer-block">{renderAnswer(result.answer)}</div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2 className="card-title">Per-question metrics</h2>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Value</th>
              <th>Pass threshold</th>
            </tr>
          </thead>
          <tbody>
            {METRIC_ORDER.map(([k, label]) => {
              const v = result.metrics[k] ?? 0;
              const pass = v >= 0.7;
              return (
                <tr key={k}>
                  <td>{label}</td>
                  <td className="num">{(v * 100).toFixed(1)}</td>
                  <td className="num" style={{ color: pass ? "var(--good)" : "var(--bad)" }}>
                    {pass ? "PASS" : "FAIL"}  ≥ 70.0
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

function ChunkBlock({
  chunk,
  index,
  question,
}: {
  chunk: Chunk;
  index: number;
  question: string;
}) {
  // Highlight the sentence with the most lexical overlap with the question.
  const sentences = splitSentences(chunk.text);
  const qTerms = new Set(
    question.toLowerCase().split(/\s+/).filter((w) => w.length > 2),
  );
  let bestIdx = 0;
  let bestOverlap = -1;
  sentences.forEach((s, i) => {
    const sTerms = new Set(s.toLowerCase().split(/\s+/));
    let overlap = 0;
    qTerms.forEach((t) => sTerms.has(t) && overlap++);
    if (overlap > bestOverlap) {
      bestOverlap = overlap;
      bestIdx = i;
    }
  });

  return (
    <div className="chunk">
      <div className="chunk-head">
        <span className="rank-pill">#{index + 1}</span>
        <span>{chunk.id}</span>
        {chunk.source_url && (
          <a href={chunk.source_url} target="_blank" rel="noopener" style={{ marginLeft: "auto" }}>
            {chunk.source_url}
          </a>
        )}
      </div>
      <div>
        {sentences.map((s, i) =>
          i === bestIdx ? <mark key={i}>{s} </mark> : <span key={i}>{s} </span>,
        )}
      </div>
    </div>
  );
}

function renderAnswer(text: string) {
  const parts = text.split(/(\[SOURCE\s+\d+\])/g);
  return parts.map((p, i) => {
    const m = p.match(/^\[SOURCE\s+(\d+)\]$/);
    if (m) return <span key={i} className="cite">{m[1]}</span>;
    return <span key={i}>{p}</span>;
  });
}

function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+(?=[A-Z])/)
    .map((s) => s.trim())
    .filter(Boolean);
}
