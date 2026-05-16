-- 001_init.sql
-- Single-tenant. Two tables: chunks (the corpus) and eval_runs/results.
-- pgvector for dense retrieval; Postgres FTS for keyword retrieval.
-- One database, two indexes, no other services.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- The corpus. One row per chunk. text_tsv is a generated column for FTS.
CREATE TABLE IF NOT EXISTS chunks (
  id            text PRIMARY KEY,
  source_url    text,
  source_title  text,
  text          text NOT NULL,
  text_tsv      tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- 1536 for text-embedding-3-small. Change to 384 for all-MiniLM-L6-v2.
  embedding     vector(1536) NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- Full-text search index.
CREATE INDEX IF NOT EXISTS chunks_text_tsv_idx ON chunks USING GIN(text_tsv);

-- Vector index. IVFFlat is the default-friendly choice; HNSW would be
-- faster at recall>0.95 but needs Postgres 16 + pgvector >= 0.5 and tuning.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
  ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Per-query log for the production-promoted eval loop.
CREATE TABLE IF NOT EXISTS query_logs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  query          text NOT NULL,
  retrieved_ids  text[] NOT NULL DEFAULT '{}',
  answer         text,
  latency_ms     int,
  cost_usd       numeric(10,6),
  user_feedback  text CHECK (user_feedback IN ('up','down') OR user_feedback IS NULL),
  trace_id       text,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS query_logs_created_idx ON query_logs(created_at DESC);

-- Eval bookkeeping.
CREATE TABLE IF NOT EXISTS eval_runs (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  retrieval_strategy text NOT NULL CHECK (retrieval_strategy IN ('vector','hybrid','hybrid_rerank')),
  git_sha            text,
  metrics            jsonb,
  status             text NOT NULL DEFAULT 'running',
  started_at         timestamptz NOT NULL DEFAULT now(),
  finished_at        timestamptz,
  error              text
);
CREATE INDEX IF NOT EXISTS eval_runs_started_idx ON eval_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS eval_results (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  eval_run_id    uuid NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
  question       text NOT NULL,
  reference_answer text,
  expected_chunk_ids text[] NOT NULL DEFAULT '{}',
  retrieved_ids  text[] NOT NULL DEFAULT '{}',
  answer         text,
  metrics        jsonb NOT NULL,
  latency_ms     int,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS eval_results_run_idx ON eval_results(eval_run_id);
