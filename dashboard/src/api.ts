/**
 * Dashboard API. Hits the backend if available; falls back to realistic
 * mock data so the dashboard renders standalone for the demo.
 */

const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:8000";

export interface EvalMetrics {
  context_precision: number;
  context_recall: number;
  faithfulness: number;
  answer_relevancy: number;
  citation_accuracy: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  cost_usd_total: number;
  n_questions: number;
}

export interface EvalRun {
  id: string;
  trigger?: string;
  agent_id?: string;
  retrieval_strategy: "vector" | "hybrid" | "hybrid_rerank";
  git_sha: string | null;
  status: "running" | "completed" | "failed";
  metrics: EvalMetrics | null;
  started_at: string;
  finished_at: string | null;
}

export interface EvalResult {
  id: string;
  eval_run_id: string;
  question_id?: string;
  question?: string;
  retrieved_ids: string[];
  answer: string;
  metrics: Record<string, number>;
  latency_ms: number;
}

export interface Chunk {
  id: string;
  text: string;
  source_url: string | null;
  rank: number;
}

export async function listRuns(): Promise<EvalRun[]> {
  try {
    const r = await fetch(`${API_BASE}/evals/runs?limit=200`);
    if (r.ok) {
      const rows: EvalRun[] = await r.json();
      if (rows.length > 0) return rows;
    }
  } catch { /* fall through */ }
  return mockRuns();
}

export async function getResult(_runId: string, _questionId: string) {
  return mockDrilldown();
}

function mockRuns(): EvalRun[] {
  const now = new Date();
  const runs: EvalRun[] = [];
  for (let day = 29; day >= 0; day--) {
    const date = new Date(now.getTime() - day * 86_400_000);
    for (const strategy of ["vector", "hybrid", "hybrid_rerank"] as const) {
      const trend = (30 - day) * 0.002;
      const base = strategy === "vector" ? 0.62 : strategy === "hybrid" ? 0.74 : 0.83;
      const noise = () => (Math.random() - 0.5) * 0.04;
      const lat = strategy === "vector" ? 480 : strategy === "hybrid" ? 720 : 950;
      runs.push({
        id: `${strategy}-${day}`,
        retrieval_strategy: strategy,
        git_sha: day % 4 === 0 ? `a${day.toString().padStart(2, "0")}c01b` : null,
        status: "completed",
        started_at: date.toISOString(),
        finished_at: new Date(date.getTime() + 60_000).toISOString(),
        metrics: {
          context_precision: clamp01(base + trend + noise()),
          context_recall: clamp01(base + trend + noise() + 0.02),
          faithfulness: clamp01(base + trend + noise() + 0.05),
          answer_relevancy: clamp01(base + trend + noise() + 0.03),
          citation_accuracy: clamp01(base + trend + noise() - 0.02),
          latency_p50_ms: lat + Math.floor(Math.random() * 60),
          latency_p95_ms: lat * 1.6 + Math.floor(Math.random() * 200),
          cost_usd_total: 0.42 + Math.random() * 0.18,
          n_questions: 50,
        },
      });
    }
  }
  return runs;
}

function mockDrilldown() {
  return {
    result: {
      id: "demo-q-1",
      eval_run_id: "hybrid_rerank-0",
      question_id: "q1",
      question: "What's the difference between Query and Path parameters?",
      retrieved_ids: ["tutorial_path-params::0001", "tutorial_query-params::0002", "tutorial_query-params::0007"],
      answer:
        "Path parameters are part of the URL path itself and are declared with curly braces, like /items/{item_id} [SOURCE 1]. " +
        "Query parameters are key-value pairs after the '?' in a URL and are declared as function arguments with default values [SOURCE 2]. " +
        "Path parameters are typically used to identify a specific resource, while query parameters typically filter or modify the result set [SOURCE 3].",
      metrics: {
        context_precision: 1.0,
        context_recall: 1.0,
        faithfulness: 0.94,
        answer_relevancy: 0.96,
        citation_accuracy: 1.0,
      },
      latency_ms: 873,
    },
    chunks: [
      {
        id: "tutorial_path-params::0001",
        text: "You can declare path \"parameters\" or \"variables\" with the same syntax used by Python format strings. The value of the path parameter is passed to your function as the argument. By declaring the type of the parameter, you give FastAPI automatic request parsing and validation.",
        source_url: "https://fastapi.tiangolo.com/tutorial/path-params/",
        rank: 0,
      },
      {
        id: "tutorial_query-params::0002",
        text: "When you declare other function parameters that are not part of the path parameters, they are automatically interpreted as \"query\" parameters. The query is the set of key-value pairs that go after the ? in a URL, separated by & characters.",
        source_url: "https://fastapi.tiangolo.com/tutorial/query-params/",
        rank: 1,
      },
      {
        id: "tutorial_query-params::0007",
        text: "You can declare default values for query parameters; the parameter will be optional. To make a query parameter required, just don't give it a default value.",
        source_url: "https://fastapi.tiangolo.com/tutorial/query-params/",
        rank: 2,
      },
    ],
  };
}

function clamp01(x: number) { return Math.max(0, Math.min(1, x)); }
