.PHONY: help venv install run test lint up down migrate seed token logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "%-12s %s\n", $$1, $$2}'

venv: ## Create a local virtualenv at .venv
	python3.12 -m venv .venv

install: ## Install Python dependencies
	pip install -r requirements.txt

run: ## Run the API locally with autoreload (requires DB already running)
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run the test suite (same command CI runs)
	PYTHONPATH=. pytest --cov --cov-report=term-missing

lint: ## Run static checks (ruff)
	ruff check app

up: ## Start app + Postgres via docker-compose
	docker-compose up --build

down: ## Stop docker-compose services
	docker-compose down

migrate: ## Apply Alembic migrations
	alembic upgrade head

seed: ## Populate the database with sample doctors
	python -m app.scripts.seed

token: ## Generate a bearer token for a random patient_id (or PATIENT_ID=<uuid> for a fixed one)
	PATIENT_ID=$(PATIENT_ID) python -c "\
	import os, uuid; \
	from app.api.deps import issue_token; \
	pid = os.environ.get('PATIENT_ID') or None; \
	print(issue_token(uuid.UUID(pid) if pid else uuid.uuid4()))"

logs: ## Tail docker-compose logs
	docker-compose logs -f

psql: ## Open a psql shell into the running db container
	docker-compose exec db psql -U postgres -d clinic