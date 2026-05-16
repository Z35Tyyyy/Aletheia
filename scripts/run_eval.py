"""
Run the eval suite and print results as a markdown table.

Usage:
    python scripts/run_eval.py                          # all three strategies
    python scripts/run_eval.py --strategy hybrid_rerank # one strategy
    python scripts/run_eval.py --git-sha $(git rev-parse --short HEAD)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db import store  # noqa: E402
from app.eval.runner import run_eval  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

STRATEGIES = ("vector", "hybrid", "hybrid_rerank")


def load_questions(path: Path) -> list[dict]:
    """Load YAML and resolve `expected_url_contains` to actual chunk_ids."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    questions = []
    for q in raw:
        url_patterns = q.get("expected_url_contains", [])
        if isinstance(url_patterns, str):
            url_patterns = [url_patterns]
        chunk_ids = store.find_chunks_by_url_substring(url_patterns)
        if not chunk_ids:
            log.warning("No chunks matched %r for question: %s", url_patterns, q["question"])
        questions.append({
            "question": q["question"],
            "reference_answer": q.get("reference_answer"),
            "expected_chunk_ids": chunk_ids,
        })
    return questions


def format_table(results_by_strategy: dict[str, dict]) -> str:
    """Render a markdown table of the headline metrics."""
    headers = ["Strategy", "Recall@5", "Precision@5", "Faithfulness", "Cite acc.", "p50 ms"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for s, m in results_by_strategy.items():
        if not m:
            continue
        lines.append(
            "| " + " | ".join([
                s,
                f"{m.get('context_recall', 0):.2f}",
                f"{m.get('context_precision', 0):.2f}",
                f"{m.get('faithfulness', 0):.2f}",
                f"{m.get('citation_accuracy', 0):.2f}",
                f"{m.get('latency_p50_ms', 0):.0f}",
            ]) + " |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=STRATEGIES, default=None,
                        help="Run only this strategy (default: all three).")
    parser.add_argument("--questions", default="eval_questions.yaml")
    parser.add_argument("--git-sha", default=None)
    args = parser.parse_args()

    questions = load_questions(Path(args.questions))
    log.info("Loaded %d questions", len(questions))

    strategies = [args.strategy] if args.strategy else list(STRATEGIES)
    results: dict[str, dict] = {}
    for s in strategies:
        log.info("=== %s ===", s)
        results[s] = run_eval(questions, retrieval_strategy=s, git_sha=args.git_sha)

    print()
    print(format_table(results))


if __name__ == "__main__":
    main()
