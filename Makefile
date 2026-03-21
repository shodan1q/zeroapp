.PHONY: install run test lint migrate worker dashboard dashboard-frontend clean \
       build-android build-ios build-ohos test-all generate-app

install:
	pip install -e ".[dev]"

run:
	zerodev run

crawl:
	zerodev crawl

pipeline:
	zerodev pipeline

worker:
	celery -A zerodev.celery_app worker --loglevel=info

worker-beat:
	celery -A zerodev.celery_app beat --loglevel=info

dashboard:
	uvicorn zerodev.api.app:app --reload --host 0.0.0.0 --port 9716

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
	pytest -v --cov=zerodev

test-all:
	pytest -v --cov=zerodev
	cd dashboard && npx tsc --noEmit

lint:
	ruff check zerodev/ tests/
	ruff format --check zerodev/ tests/

format:
	ruff check --fix zerodev/ tests/
	ruff format zerodev/ tests/

typecheck:
	mypy zerodev/

migrate:
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(msg)"

generate-app:
	zerodev pipeline

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
