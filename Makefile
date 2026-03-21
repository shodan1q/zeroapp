.PHONY: install run test lint migrate worker dashboard dashboard-frontend clean \
       build-android build-ios build-ohos test-all generate-app

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

dashboard-frontend:
	cd dashboard && npm run dev

build-android:
	cd workspace/$$(ls workspace/ | head -1) && flutter build apk --release

build-ios:
	cd workspace/$$(ls workspace/ | head -1) && flutter build ipa --release

build-ohos:
	cd workspace/$$(ls workspace/ | head -1) && \
		DEVECO_SDK_HOME=$${DEVECO_SDK_HOME} \
		OHOS_SDK_HOME=$${OHOS_SDK_HOME} \
		flutter build hap --release

test:
	pytest -v --cov=autodev

test-all:
	pytest -v --cov=autodev
	cd dashboard && npx tsc --noEmit

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

generate-app:
	autodev pipeline

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
