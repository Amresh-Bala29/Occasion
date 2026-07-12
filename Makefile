.PHONY: setup dev web agent up down migrate seed test

setup:
	bash infra/setup.sh

dev:
	bash infra/run-dev.sh

web:
	cd apps/web && npm run dev

agent:
	cd services/agent && ./.venv/bin/uvicorn main:app --reload --port 8000

up:
	docker compose up --build

down:
	docker compose down

migrate:
	services/agent/.venv/bin/python infra/apply-migrations.py

seed:
	services/agent/.venv/bin/python infra/seed-demo-data.py

test:
	cd services/agent && pytest -q
