.PHONY: dev down serve test lint format worker migrate

# Starts the databases in the background
dev:
	docker-compose -f infra/docker-compose.yml up -d

# Runs the FastAPI development server (requires infra running via `make dev`)
serve:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Stops and removes the database containers
down:
	docker-compose -f infra/docker-compose.yml down

# Runs all our automated tests
test:
	pytest tests/

# Checks for coding errors and type issues
lint:
	ruff check src tests
	mypy src tests

# Automatically formats the code to look perfectly clean
format:
	ruff check --fix src tests
	ruff format src tests

# (We will use this in Day 13) Starts the background worker for file processing
worker:
	celery -A src.infrastructure.message_queue.celery_app worker -Q ingestion.documents -l info

# Runs Alembic database migrations (Day 2+)
migrate:
	alembic upgrade head