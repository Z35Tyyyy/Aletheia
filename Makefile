# Makefile for ragfast. `make help` lists everything.
.DEFAULT_GOAL := help
.PHONY: help up down migrate seed api widget dashboard test eval clean

PSQL := docker compose exec -T postgres psql -U rag -d rag

help:                           ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:                             ## Start Postgres (+pgvector) in the background.
	docker compose up -d
	@echo "Waiting for Postgres..."
	@until $(PSQL) -c "SELECT 1" >/dev/null 2>&1; do sleep 1; done
	@echo "Postgres ready."

down:                           ## Stop and remove containers.
	docker compose down

migrate: up                     ## Apply the schema.
	$(PSQL) -f /migrations/001_init.sql

seed: migrate                   ## Ingest the FastAPI docs corpus.
	cd backend && python -m scripts.seed_fastapi_docs || (cd .. && python scripts/seed_fastapi_docs.py)

api:                            ## Run the FastAPI server (foreground).
	cd backend && uvicorn app.main:app --reload --port 8000

widget:                         ## Run the widget dev server (foreground).
	cd widget && npm install && npm run dev

dashboard:                      ## Run the dashboard dev server (foreground).
	cd dashboard && npm install && npm run dev

test:                           ## Run the unit tests.
	cd backend && python -m pytest ../tests -v

eval:                           ## Run the full eval suite (all 3 strategies).
	python scripts/run_eval.py

eval-vector:                    ## Run only the vector-only eval.
	python scripts/run_eval.py --strategy vector

eval-rerank:                    ## Run only the hybrid+rerank eval.
	python scripts/run_eval.py --strategy hybrid_rerank

clean:                          ## Reset the database (destructive).
	docker compose down -v
