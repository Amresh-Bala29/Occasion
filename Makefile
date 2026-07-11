.PHONY: setup dev web agent up down seed test

setup:
	bash infra/setup.sh

dev:
	bash infra/run-dev.sh

web:
	cd apps/web && npm run dev

agent:
	cd services/agent && uvicorn main:app --reload --port 8000

up:
	docker compose up --build

down:
	docker compose down

seed:
	python infra/seed-demo-data.py

test:
	cd services/agent && pytest -q
