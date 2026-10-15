SHELL := /bin/bash
COMPOSE := docker compose
.DEFAULT_GOAL := help

.PHONY: help env setup up down clean ps logs psql lint fmt test test-dags dashboards trigger

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

env: ## Create .env with freshly generated secrets (no-op if it exists)
	@python3 scripts/init_env.py

setup: ## Install local dev environment and git hooks
	uv sync
	uv run pre-commit install

up: env ## Build and start the stack; waits for bootstrap and dashboard provisioning
	$(COMPOSE) up -d --build --wait --wait-timeout 600
	@$(COMPOSE) wait metabase-provision >/dev/null && echo "Dashboards provisioned: http://localhost:$${METABASE_PORT:-3001}"

down: ## Stop the stack, keep data
	$(COMPOSE) down

clean: ## Stop the stack and delete all data (volumes and landing zone; the dataset cache stays)
	$(COMPOSE) down -v --remove-orphans
	rm -rf data/landing

ps: ## Show service status
	$(COMPOSE) ps -a

logs: ## Follow logs (SERVICE=name to filter)
	$(COMPOSE) logs -f --tail=100 $(SERVICE)

psql: ## psql session on the warehouse as the pipeline role
	$(COMPOSE) exec postgres sh -c 'psql "postgresql://dwh_etl:$$DWH_ETL_PASSWORD@localhost/dwh"'

lint: ## Lint Python (ruff) and SQL (sqlfluff)
	uv run ruff check .
	uv run ruff format --check .
	uv run sqlfluff lint warehouse bi

fmt: ## Auto-format Python and SQL
	uv run ruff check --fix .
	uv run ruff format .
	uv run sqlfluff fix warehouse bi

test: ## Unit tests
	uv run pytest

test-dags: ## DAG integrity tests inside the Airflow image
	$(COMPOSE) run --rm --no-deps airflow-cli bash -c "cd /opt/hotelpulse && python -m pytest -p no:cacheprovider tests/dags"

dashboards: ## Re-provision Metabase dashboards from bi/metabase
	$(COMPOSE) run --rm --no-deps metabase-provision

trigger: ## Trigger a DAG run now (DAG=pms_ingest)
	$(COMPOSE) exec airflow-scheduler airflow dags trigger $(or $(DAG),pms_ingest)
