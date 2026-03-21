.PHONY: install run test lint migrate worker dashboard clean

install:
	pip install -e ".[dev]"

run:
	autodev run

crawl:
	autodev crawl

pipeline:
	autodev pipeline

worker:
	celery -A autodev.celery_app worker --loglevel=info

worker-beat:
	celery -A autodev.celery_app beat --loglevel=info

dashboard:
	uvicorn autodev.api.app:app --reload --host 0.0.0.0 --port 9716

test:
	pytest -v --cov=autodev

lint:
	ruff check autodev/ tests/
	ruff format --check autodev/ tests/

format:
	ruff check --fix autodev/ tests/
	ruff format autodev/ tests/

typecheck:
	mypy autodev/

migrate:
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(msg)"

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
