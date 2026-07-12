# Occasion

Amresh Balakrishnan - 7/11 sf hackathon

Plan any event end-to-end with a team of autonomous agents. A Next.js frontend
drives a Python agent service that sources vendors, negotiates over email,
schedules, budgets, markets, and distributes the event — using computer-use
browser automation, with human approval gates on spending and sensitive actions.

## Monorepo layout

```
apps/web            Next.js frontend (dashboard, event workspace, voice, chat)
services/agent      FastAPI backend — the agent team, workflows, integrations
packages/shared     JSON Schemas + constants shared across web and agent
infra/              Dockerfiles and dev scripts
docs/               Architecture notes and runbooks
.github/workflows   CI for web and agent
```

## Agent service (`services/agent`)

- `core/` — orchestrator (routes tasks to agents), supervisor (monitors them),
  workflow state, config, logging, security.
- `agents/` — one domain agent per concern: requirements, venue, catering,
  staffing, entertainment, decorations, merchandise, purchasing, marketing,
  distribution, scheduling, budget, post-event.
- `workflows/` — multi-agent flows (event planning, vendor sourcing, outreach).
- `integrations/` — external services: `h_company` (computer use), `gradium`
  (voice), `email` (Gmail), `calendar` (Google Calendar), `distribution` (Luma,
  Partiful, Eventbrite, Meetup).
- `tools/` — capabilities exposed to agents (browser, email, calendar, search,
  payment, file).
- `planning/` — task DAG, constraints, budget/schedule optimizers, risk.
- `approvals/` — human-in-the-loop gates and spending rules.
- `memory/` — event / user / vendor memory + vector store.
- `models/`, `database/`, `tests/`.

## Quickstart

```bash
cp .env.example .env          # fill in credentials
make setup                    # install web + agent deps (creates .venv)
make dev                      # run web (:3000) and agent (:8000) together
# or, containerized:
make up                       # docker compose: web + agent + postgres
```

See the `Makefile` for individual targets (`web`, `agent`, `seed`, `test`).
