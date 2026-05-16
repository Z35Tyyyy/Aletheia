"""
Chunking.

Recursive character splitter with structure-aware separators. Tries the
strongest natural boundaries first (paragraph breaks), falls back to
sentence boundaries, then word boundaries, then characters. This matches
the proposal's "chunking refactor" reference in §6.4.

Chunk metadata records the source URL and a best-effort heading hierarchy
so the widget's citation side panel can show "from: Setup > Authentication".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 800       # characters; ~200 tokens for typical English prose
DEFAULT_CHUNK_OVERLAP = 100

# Tried in order, strongest semantic break first.
DEFAULT_SEPARATORS = ["\n\n\n", "\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]


@dataclass
class Chunk:
    id: str
    text: str
    source_id: str
    source_url: str | None = None
    metadata: dict = field(default_factory=dict)


def chunk_text(
    text: str,
    source_id: str,
    source_url: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split a single text blob into Chunk objects with stable IDs."""
    base_meta = metadata or {}
    pieces = _recursive_split(text, chunk_size, overlap, DEFAULT_SEPARATORS)
    return [
        Chunk(
            id=f"{source_id}::{i:04d}",
            text=p.strip(),
            source_id=source_id,
            source_url=source_url,
            metadata=base_meta,
        )
        for i, p in enumerate(pieces)
        if p.strip()
    ]


def chunk_html(
    html: str,
    source_id: str,
    source_url: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """
    HTML chunker that preserves heading hierarchy in metadata so the citation
    panel can show "Setup > Authentication > API keys" as breadcrumbs.
    """
    soup = BeautifulSoup(html, "lxml")

    # Strip noise. Pages without these stripped produce chunks that are 80% nav.
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()

    chunks: list[Chunk] = []
    headings: list[str] = [""] * 6  # h1..h6
    buf: list[str] = []
    buf_len = 0

    def flush():
        nonlocal buf, buf_len
        if not buf_len:
            return
        text = " ".join(buf).strip()
        for i, piece in enumerate(_recursive_split(text, chunk_size, overlap, DEFAULT_SEPARATORS)):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                Chunk(
                    id=f"{source_id}::{len(chunks):04d}",
                    text=piece,
                    source_id=source_id,
                    source_url=source_url,
                    metadata={"headings": [h for h in headings if h]},
                )
            )
        buf = []
        buf_len = 0

    for elem in soup.body.descendants if soup.body else soup.descendants:
        if not hasattr(elem, "name"):
            continue
        name = elem.name
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            flush()
            level = int(name[1])
            headings[level - 1] = elem.get_text(strip=True)
            # Lower headings reset.
            for k in range(level, 6):
                headings[k] = ""
        elif name in ("p", "li", "td", "blockquote"):
            t = elem.get_text(" ", strip=True)
            if t:
                buf.append(t)
                buf_len += len(t)
                if buf_len >= chunk_size:
                    flush()
    flush()
    return chunks


def _recursive_split(
    text: str, chunk_size: int, overlap: int, separators: list[str]
) -> list[str]:
    """Splits text into chunks no larger than chunk_size, preferring strong boundaries."""
    if len(text) <= chunk_size:
        return [text]

    # Pick the first separator that actually appears.
    sep = ""
    for s in separators:
        if s and s in text:
            sep = s
            break

    if not sep:
        # No separator present anywhere — hard-split by characters with overlap.
        return _hard_split(text, chunk_size, overlap)

    parts = text.split(sep)
    chunks: list[str] = []
    current = ""

    for part in parts:
        candidate = (current + sep + part) if current else part
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(part) > chunk_size:
            # The part itself is too big — recurse with the next-weaker separator.
            next_seps = separators[separators.index(sep) + 1 :] or [""]
            for sub in _recursive_split(part, chunk_size, overlap, next_seps):
                chunks.append(sub)
            current = ""
        else:
            current = part

    if current:
        chunks.append(current)

    # Apply overlap between adjacent chunks (last `overlap` chars repeated).
    if overlap > 0 and len(chunks) > 1:
        out = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:]
            out.append(prev_tail + chunks[i] if not chunks[i].startswith(prev_tail) else chunks[i])
        chunks = out

    return chunks


def _hard_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    stride = max(1, chunk_size - overlap)
    return [text[i : i + chunk_size] for i in range(0, len(text), stride)]


# ---- Token estimation (cheap, no tokenizer load) ----

def estimate_tokens(text: str) -> int:
    """~4 chars per token is the standard rule of thumb for English. Good enough for budgeting."""
    return max(1, len(text) // 4)
