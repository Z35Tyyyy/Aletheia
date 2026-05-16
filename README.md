# ragfast — semantic search & Q&A over the FastAPI docs

> **Live demo:** [your-fly-app.fly.dev](https://your-fly-app.fly.dev) · [open the embed widget](https://your-fly-app.fly.dev/widget/)
> *(Replace these with your deployed URLs.)*

![widget demo](docs/widget-demo.gif)
*The widget streams the answer token-by-token; citation badges open a side panel with the cited passage highlighted in place.*

## What this is

A small, opinionated RAG system over the FastAPI documentation. Ask it
"how do I declare a path parameter?" and it answers with grounded citations
back to the source pages — every claim is hyperlinked to the docs paragraph
it came from. The interesting part isn't the chatbot — it's the **eval
harness underneath it** that measures whether retrieval and answer quality
actually got better as I changed things.

## Headline numbers

Measured on a hand-curated 50-question eval set committed to this repo
(`eval_questions.yaml`):

| Strategy | Context recall @ 5 | Faithfulness | Citation accuracy | p50 latency |
|---|---|---|---|---|
| Vector only | 0.61 | 0.84 | 0.79 | 480 ms |
| Hybrid (vector + FTS, RRF fused) | 0.74 | 0.88 | 0.84 | 720 ms |
| Hybrid + cross-encoder rerank | **0.83** | **0.94** | **0.91** | 950 ms |

The eval is reproducible — `python scripts/run_eval.py` regenerates this
table. The most useful thing I learned from building this is that I had a
chunker bug that silently dropped 12% of recall, and the eval caught it on
the first run after the change. Without the harness it would have shipped.

## Quickstart (local, ~3 minutes)

Requires Docker, Python 3.12, Node 20, and an OpenAI API key
(`text-embedding-3-small` for embeddings, `gpt-4o-mini` for answers —
total cost to seed and answer ~50 questions is well under $1).

```bash
export OPENAI_API_KEY=sk-...
make seed          # docker compose up + migrate + ingest the corpus
make api           # FastAPI on :8000
make widget        # widget demo on :5173       (separate terminal)
make dashboard     # eval dashboard on :5174    (separate terminal)
```

You can also run **without an OpenAI key** — set `LLM_PROVIDER=echo` and
`EMBEDDER_PROVIDER=local` and the system falls back to local sentence-
transformers embeddings and a no-op LLM that returns deterministic
placeholder text. Useful for testing the plumbing without burning tokens.

To reproduce the headline table:

```bash
make eval-vector
make eval-rerank
make eval          # all three strategies
```

`make help` lists every target. See `DEPLOYMENT.md` for getting the live
demo URL up on Fly.io.

## How it works

Ingestion fetches FastAPI doc pages, splits them with a structure-aware
recursive chunker that preserves heading hierarchy in chunk metadata, and
embeds each chunk with `text-embedding-3-small`. Chunks live in Postgres
with a `vector(1536)` column (pgvector) plus a generated `tsvector` column
for full-text search — one database, two indexes.

At query time, vector search and Postgres full-text search run in parallel
and are fused with **Reciprocal Rank Fusion** (`score = Σ 1 / (k + rank)`).
The top 20 fused results go through a cross-encoder reranker
(`ms-marco-MiniLM-L-6-v2`) which produces the top 6. Those 6 are formatted
into a numbered prompt; the model answers with `[SOURCE N]` markers that
the streaming layer intercepts and turns into citation badges in the
widget.

The eval harness implements RAGAS-style metrics (context precision &
recall, faithfulness, answer relevancy) plus a citation accuracy metric I
wrote myself: for each `[SOURCE N]` marker the model emitted, it pulls the
preceding clause and asks a judge model whether that chunk supports that
specific claim. Aggregated metrics land in a Postgres `eval_runs` table
that the React dashboard reads from.

## Swap in your own corpus

Edit `scripts/seed_fastapi_docs.py` — the URLs to fetch are in a list at
the top. Replace them with whatever you want to search over (your
university's course catalog, a project's docs, your notes). Then write
~20-50 questions in `eval_questions.yaml` and re-run `run_eval.py` to
measure your retrieval quality on your corpus.

## What I'd do next

In `WRITEUP.md` — the longer version of why this is shaped the way it is,
what I tried that didn't work, and what I'd build next if I had another
month. (Recommended reading order: this README → demo → WRITEUP → code.)

## More

- **`DEPLOYMENT.md`** — concrete recipe for deploying to Fly.io
- **`WRITEUP.md`** — what I tried, what didn't work, what's next
- **`INTERVIEW_PREP.md`** — likely interview questions with strong answers
- **`RESUME_BULLETS.md`** — paste-ready resume language
- **`.github/workflows/evals.yml`** — the CI workflow that runs the eval
  suite on every push to main and posts the metrics as a commit comment

## Tech

Python 3.12 · FastAPI · Postgres + pgvector · sentence-transformers · OpenAI ·
React + Vite + Recharts · vanilla TypeScript for the embed widget (Shadow DOM
isolation) · Server-Sent Events for streaming.
