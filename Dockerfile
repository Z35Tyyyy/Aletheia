# Multi-stage build: widget + dashboard + backend → one image, one deploy.
# Used by `fly deploy`. The static assets land under /app/static/ and are
# served by FastAPI in production.

# ---- 1) Widget bundle ----
FROM node:20-alpine AS widget-builder
WORKDIR /widget
COPY widget/package.json widget/tsconfig.json widget/vite.config.ts ./
RUN npm install --no-audit --no-fund
COPY widget/index.html .
COPY widget/src ./src
RUN npm run build

# ---- 2) Dashboard bundle ----
FROM node:20-alpine AS dashboard-builder
WORKDIR /dashboard
COPY dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts ./
RUN npm install --no-audit --no-fund
COPY dashboard/index.html .
COPY dashboard/src ./src
# Bake the API base URL into the dashboard. Defaults to "" → relative requests
# work against the same origin. Set --build-arg VITE_API_BASE=https://... when
# deploying widget/dashboard to a different origin than the API.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# ---- 3) Python backend ----
FROM python:3.12-slim AS backend
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY scripts ./scripts
COPY eval_questions.yaml ./eval_questions.yaml

# Static assets from previous stages
COPY --from=widget-builder /widget/dist /app/static/widget
COPY --from=dashboard-builder /dashboard/dist /app/static/dashboard

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
