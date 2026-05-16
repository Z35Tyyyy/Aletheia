/**
 * SSE consumer for the single-agent backend.
 *
 * EventSource is GET-only, so for POST-with-body we use fetch + ReadableStream
 * and parse SSE on the fly.
 */

export interface AgentConfig {
  name: string;
  color: string;
  greeting: string;
  placeholder: string;
  suggested_questions: string[];
}

export interface CitationData {
  n: number;
  chunk_id: string;
  source_url: string | null;
  source_title: string | null;
  text: string;
  highlight_start: number;
  highlight_end: number;
}

export interface StreamHandlers {
  onMeta?: (data: { trace_id: string; n_candidates: number }) => void;
  onText?: (chunk: string) => void;
  onCite?: (cite: CitationData) => void;
  onDone?: (data: { latency_ms: number; cost_usd: number; query_log_id: string }) => void;
  onError?: (data: { message: string; trace_id?: string }) => void;
  signal?: AbortSignal;
}

export async function getConfig(apiBase: string): Promise<AgentConfig> {
  const r = await fetch(`${apiBase}/config`);
  if (!r.ok) throw new Error(`config fetch failed: ${r.status}`);
  return (await r.json()) as AgentConfig;
}

export async function streamQuery(
  apiBase: string,
  query: string,
  handlers: StreamHandlers,
): Promise<void> {
  const r = await fetch(`${apiBase}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ query }),
    signal: handlers.signal,
  });
  if (!r.ok || !r.body) throw new Error(`query failed: ${r.status}`);

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split: number;
    while ((split = buffer.indexOf("\n\n")) >= 0) {
      dispatchEvent(buffer.slice(0, split), handlers);
      buffer = buffer.slice(split + 2);
    }
  }
}

export async function sendFeedback(
  apiBase: string,
  queryLogId: string,
  feedback: "up" | "down",
): Promise<void> {
  await fetch(`${apiBase}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query_log_id: queryLogId, feedback }),
  });
}

function dispatchEvent(raw: string, h: StreamHandlers): void {
  let event = "message";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;
  let payload: unknown;
  try { payload = JSON.parse(data); } catch { payload = data; }
  switch (event) {
    case "meta": h.onMeta?.(payload as { trace_id: string; n_candidates: number }); break;
    case "text": h.onText?.(typeof payload === "string" ? payload : String(payload)); break;
    case "cite": h.onCite?.(payload as CitationData); break;
    case "done": h.onDone?.(payload as { latency_ms: number; cost_usd: number; query_log_id: string }); break;
    case "error": h.onError?.(payload as { message: string }); break;
  }
}
