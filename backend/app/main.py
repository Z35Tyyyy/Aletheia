"""FastAPI app. Two routers: query and evals. Static assets in production."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import get_pool, store
from .routers import evals, query

log = logging.getLogger(__name__)

# In the production Docker image these directories are populated by the
# multi-stage build. In dev they don't exist and we skip mounting — Vite's
# dev servers handle the widget and dashboard on :5173 / :5174.
STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ragfast", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(query.router)
    app.include_router(evals.router)

    # Production static assets — only mounted if the multi-stage build copied them in.
    widget_dir = STATIC_ROOT / "widget"
    if widget_dir.is_dir():
        app.mount("/widget", StaticFiles(directory=widget_dir, html=True), name="widget")
    dashboard_dir = STATIC_ROOT / "dashboard"
    if dashboard_dir.is_dir():
        app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

    @app.get("/healthz")
    def healthz() -> dict:
        """Exercises real dependencies, not a stub 200."""
        problems = []
        try:
            with get_pool().connection() as conn:
                conn.execute("SELECT 1").fetchone()
        except Exception as e:  # noqa: BLE001
            problems.append(f"postgres: {e}")
        try:
            n = store.chunk_count()
            if n == 0:
                problems.append("chunks: 0 — run scripts/seed_fastapi_docs.py")
        except Exception as e:  # noqa: BLE001
            problems.append(f"chunks: {e}")
        if problems:
            raise HTTPException(503, detail={"problems": problems})
        return {"status": "ok", "chunk_count": n}

    @app.get("/")
    def root() -> dict:
        return {"name": "ragfast", "docs": "/docs"}

    return app


app = create_app()
