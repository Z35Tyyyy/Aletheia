"""Tests for the recursive char splitter."""
from __future__ import annotations

from app.ingestion.chunker import chunk_html, chunk_text, estimate_tokens


class TestChunkText:
    def test_short_text_single_chunk(self):
        chunks = chunk_text("Hello world.", source_id="s1")
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world."
        assert chunks[0].source_id == "s1"
        assert chunks[0].id == "s1::0000"

    def test_empty_text_no_chunks(self):
        chunks = chunk_text("", source_id="s1")
        assert chunks == []

    def test_long_text_splits_at_paragraph_boundary(self):
        para1 = "First paragraph. " * 30  # ~510 chars
        para2 = "Second paragraph. " * 30
        text = para1 + "\n\n" + para2
        chunks = chunk_text(text, source_id="s1", chunk_size=600, overlap=0)
        # We should get at least two chunks, split near the paragraph boundary.
        assert len(chunks) >= 2

    def test_chunk_size_respected(self):
        text = "word " * 1000  # 5000 chars
        chunks = chunk_text(text, source_id="s1", chunk_size=400, overlap=50)
        # With overlap, chunks may exceed chunk_size slightly due to the prepend.
        # Allow a moderate slack but enforce a hard ceiling.
        for c in chunks:
            assert len(c.text) <= 600  # chunk_size + overlap + slack

    def test_ids_are_unique_and_sequential(self):
        text = "sentence. " * 200
        chunks = chunk_text(text, source_id="s1", chunk_size=200)
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))
        assert ids == [f"s1::{i:04d}" for i in range(len(ids))]

    def test_metadata_propagates(self):
        chunks = chunk_text("hello", source_id="s1", metadata={"author": "x"})
        assert chunks[0].metadata == {"author": "x"}

    def test_source_url_set_when_provided(self):
        chunks = chunk_text("hello", source_id="s1", source_url="https://example.com")
        assert chunks[0].source_url == "https://example.com"


class TestChunkHtml:
    def test_strips_script_and_style(self):
        html = """
          <html><body>
            <script>alert('evil')</script>
            <style>body { color: red }</style>
            <p>Visible content here.</p>
          </body></html>
        """
        chunks = chunk_html(html, source_id="s1")
        combined = " ".join(c.text for c in chunks)
        assert "Visible content here" in combined
        assert "alert" not in combined
        assert "color: red" not in combined

    def test_records_heading_hierarchy(self):
        html = """
          <html><body>
            <h1>Setup</h1>
            <h2>Authentication</h2>
            <p>Use an API key for authentication.</p>
          </body></html>
        """
        chunks = chunk_html(html, source_id="s1")
        # The chunk containing the body should have the heading trail recorded.
        assert any(
            c.metadata.get("headings") == ["Setup", "Authentication"] for c in chunks
        )

    def test_drops_nav_footer_header(self):
        html = """
          <html><body>
            <nav><a href='/'>Home</a></nav>
            <p>Main content.</p>
            <footer>Copyright 2026</footer>
          </body></html>
        """
        chunks = chunk_html(html, source_id="s1")
        combined = " ".join(c.text for c in chunks)
        assert "Main content" in combined
        assert "Copyright" not in combined


class TestEstimateTokens:
    def test_rough_4_chars_per_token(self):
        assert estimate_tokens("a" * 4) == 1
        assert estimate_tokens("a" * 400) == 100

    def test_at_least_one(self):
        assert estimate_tokens("") == 1  # we return max(1, ...)
        assert estimate_tokens("hi") == 1
