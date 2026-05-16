"""
Seed: fetch and ingest a curated list of FastAPI documentation pages.

Usage:
    cd backend && python -m scripts.seed_fastapi_docs

This is the one-time setup that primes the corpus. ~15 pages, ~340 chunks
after the recursive splitter. Takes ~30s with text-embedding-3-small.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Make `app.*` importable when invoked from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db import store  # noqa: E402
from app.ingestion.pipeline import ingest_url  # noqa: E402
from app.retrieval.embedder import get_embedder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# The corpus. Curated for breadth: tutorial fundamentals, dependencies,
# response handling, async, deployment. Replace with your own list to
# point this RAG at a different corpus.
URLS = [
    "https://fastapi.tiangolo.com/tutorial/first-steps/",
    "https://fastapi.tiangolo.com/tutorial/path-params/",
    "https://fastapi.tiangolo.com/tutorial/query-params/",
    "https://fastapi.tiangolo.com/tutorial/query-params-str-validations/",
    "https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/",
    "https://fastapi.tiangolo.com/tutorial/body/",
    "https://fastapi.tiangolo.com/tutorial/body-multiple-params/",
    "https://fastapi.tiangolo.com/tutorial/request-files/",
    "https://fastapi.tiangolo.com/tutorial/response-status-code/",
    "https://fastapi.tiangolo.com/tutorial/dependencies/",
    "https://fastapi.tiangolo.com/tutorial/security/",
    "https://fastapi.tiangolo.com/tutorial/cors/",
    "https://fastapi.tiangolo.com/tutorial/bigger-applications/",
    "https://fastapi.tiangolo.com/tutorial/background-tasks/",
    "https://fastapi.tiangolo.com/async/",
    "https://fastapi.tiangolo.com/deployment/server-workers/",
    "https://fastapi.tiangolo.com/advanced/custom-response/",
]


def url_to_source_id(url: str) -> str:
    """Stable, filesystem-safe ID derived from the URL path."""
    path = urlparse(url).path.strip("/").replace("/", "_") or "root"
    return path


def main() -> None:
    embedder = get_embedder()
    total = 0
    t0 = time.perf_counter()
    for url in URLS:
        sid = url_to_source_id(url)
        try:
            result = ingest_url(url, source_id=sid, store=store, embedder=embedder)
            total += result.chunks_added
            log.info("%s → %d chunks", url, result.chunks_added)
        except Exception as e:  # noqa: BLE001
            log.warning("failed to ingest %s: %s", url, e)
    elapsed = time.perf_counter() - t0
    log.info("Done. %d chunks ingested in %.1fs (corpus total: %d)",
             total, elapsed, store.chunk_count())


if __name__ == "__main__":
    main()
