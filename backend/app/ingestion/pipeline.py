"""
Sync ingestion: fetch URL → chunk → embed → upsert.

Driven directly from a CLI script (scripts/seed_fastapi_docs.py). No
worker queue. For a static-ish corpus this is fine; for a frequently
updated one you'd want a queue, which the WRITEUP discusses.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from ..db import VectorStore
from ..retrieval.embedder import Embedder
from .chunker import Chunk, chunk_html, chunk_text

log = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    source_id: str
    source_url: str | None
    source_title: str | None
    chunks_added: int


def fetch_url(url: str) -> tuple[str, str | None]:
    """Returns (html_content, page_title)."""
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        r = client.get(url, headers={"User-Agent": "ragfast/0.1"})
        r.raise_for_status()
        # Extract the <title> if present so the citation panel can show
        # something nicer than the URL.
        title = None
        try:
            soup = BeautifulSoup(r.text, "lxml")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
        except Exception:  # noqa: BLE001
            pass
        return r.text, title


def ingest_url(url: str, source_id: str, store: VectorStore, embedder: Embedder) -> IngestionResult:
    html, title = fetch_url(url)
    chunks = chunk_html(html, source_id=source_id, source_url=url)
    # The chunker doesn't know the page title — patch it in here.
    for c in chunks:
        c.metadata = {**c.metadata, "page_title": title}
    return _ingest_chunks(chunks, store, embedder, source_id, url, title)


def ingest_text(
    text: str, source_id: str, store: VectorStore, embedder: Embedder,
    title: str | None = None,
) -> IngestionResult:
    chunks = chunk_text(text, source_id=source_id)
    return _ingest_chunks(chunks, store, embedder, source_id, None, title)


def _ingest_chunks(
    chunks: list[Chunk],
    store: VectorStore,
    embedder: Embedder,
    source_id: str,
    source_url: str | None,
    source_title: str | None,
) -> IngestionResult:
    if not chunks:
        log.warning("No chunks produced for %s", source_id)
        return IngestionResult(source_id, source_url, source_title, 0)

    texts = [c.text for c in chunks]
    embs = embedder.embed_documents(texts)

    docs = [
        {
            "id": c.id,
            "source_url": source_url,
            "source_title": source_title,
            "text": c.text,
            "metadata": c.metadata,
            "embedding": embs[i],
        }
        for i, c in enumerate(chunks)
    ]
    n = store.upsert(docs)
    log.info("Ingested %d chunks from %s", n, source_url or source_id)
    return IngestionResult(source_id, source_url, source_title, n)
