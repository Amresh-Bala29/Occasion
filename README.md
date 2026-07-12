# Occasion

**An autonomous AI event coordinator that does the work — not just the planning.**

Occasion researches, communicates, purchases, schedules, and manages an entire
event by driving real websites and applications, the same ones a human organizer
would open in a browser. Tell it what you're throwing — an offsite, a launch
party, a conference — and a team of domain agents sources venues, negotiates with
caterers over email, hires staff, books entertainment, buys decorations, produces
custom-branded merchandise, publishes listings, tracks a live budget, and runs the
day-of logistics. It doesn't hand you a checklist; it executes the checklist.

Occasion is built on **[H Company](https://hub.hcompany.ai/computer-use-agents/introduction)'s
browser-use agent stack** and **[Gradium](https://docs.gradium.ai/) voice**. H's
computer-use agents give it hands on the real web — logging in, dismissing cookie
walls and popups, scrolling infinite feeds, filling inquiry forms, comparing
quotes, uploading artwork, and completing purchases — so a signed-in cloud Chrome
profile stands in for a wall of per-service API keys. Gradium gives it a voice:
streaming speech-to-text and text-to-speech so you can brief it, hear progress, and
approve decisions out loud. Every critical action — an important email, a contract,
a booking, a deposit — passes through a **human approval gate** before it happens,
with user-defined spending limits that let routine spend flow through unattended.

That is exactly the track: *an autonomous event coordinator that navigates the
messy real web — logins, popups, cookie walls, infinite scroll — to research, book,
purchase, schedule, and manage events end-to-end, with approval gates for critical
actions.* Occasion is the working implementation of it.

---

## How it works

```
              voice / chat / dashboard
                       │
              apps/web  (Next.js 16 · React 19 · Tailwind v4)
                       │  REST  (async runs + polling)
              services/agent  (FastAPI · Python)
                       │
        ┌──────────────┼───────────────────────────┐
        │              │                            │
   Orchestrator   13 domain agents            Workflows
   (task router)  + shared BaseAgent    (planning · sourcing · outreach)
        │              │                            │
        └──────────────┴───────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
   H Company                       Gradium
   · Models API (holo3, routing)   · STT / TTS
   · Computer-use (cloud Chrome)   · streaming voice
```

A request enters as chat or voice, becomes a durable **run**, and the orchestrator
routes it to the agent or workflow that owns it. Domain agents do their real work
inside H computer-use sessions on a live browser. Sensitive results wait at an
approval gate; everything else is persisted to memory and surfaced on the
dashboard. The frontend polls run state and re-renders as the work lands.

---

## The agent stack

**Orchestrator (`core/orchestrator.py`).** Routing is explicit when a task already
names its agent; otherwise a fast Holo completion picks across the roster — the
domain fleet, H's managed read-only agents for general web work no specialist owns,
and the `workflows/` pipelines for end-to-end jobs no single agent covers. Dispatch
fans out as independent **top-level** H sessions grouped per event: at capacity H
queues top-level sessions but fails subagent children with `429`, so client-side
fan-out over top-level sessions is the shape the platform rewards.

**Domain fleet (`agents/`).** Thirteen agents, one responsibility each, over a
shared `BaseAgent` — requirements, venue, catering, staffing, entertainment,
decorations, merchandise, purchasing, marketing, distribution, scheduling, budget,
post-event. Each runs as an **inline H web agent**: its own model, instructions, and
skills, carrying the same signed-in cloud browser. A shared instruction appended to
every agent encodes the product's contract — clear routine web obstacles (cookie
walls, popups) autonomously, but stop at true blockers (logins without credentials,
security checks) and at any sensitive commitment, which needs explicit authorization
in the task text itself. Every agent returns a **typed Pydantic schema**, so its
web work comes back as structured, comparable data rather than prose.

| Agent | Model | What it does |
|-------|-------|--------------|
| **Requirements** | deep | Interviews the client and structures the brief — type, date, headcount, budget, food, staffing, entertainment, branding, accessibility, shipping deadlines, and stated priorities. Emits open follow-up questions; an empty list means the interview is complete. → `EventRequirements` |
| **Venue** | deep | Searches venue marketplaces and venue sites, verifies capacity / price / availability / equipment / house rules on the primary page (never inferred), then contacts managers for quotes and tours. → `VenueResearch` (compared shortlist + recommendation) |
| **Catering** | deep | Finds caterers, reads menus and per-person pricing at the source, treats dietary restrictions as hard requirements, and computes food/drink quantities from headcount and duration *showing the arithmetic*. → `CateringPlan` |
| **Staffing** | deep | Sources temporary staff — registration, security, bartenders, servers, AV, photographers, medical — across platforms and agencies, matching each to a role, shift window, and arrival time. Reports uncovered roles as coverage gaps rather than stretching weak options. → `StaffingPlan` |
| **Entertainment** | deep | Evaluates DJs, bands, speakers, hosts, comedians, photobooths, and activities on price, date availability, and reviews, and captures each act's technical requirements (stage, power, AV, space) to decide whether it fits the venue. → `EntertainmentResearch` |
| **Decorations** | deep | Sources signage, linens, lighting, name tags, furniture, stage gear, gifts, and cleaning supplies; sizes quantities from the headcount and disqualifies items that arrive after the shipping deadline. Assembles carts as evidence but never enters a payment flow. → `SupplyShortlist` |
| **Merchandise** | deep | From the event's logo, finds manufacturers for custom swag, collects quotes with quantity breaks and setup fees, captures artwork requirements, and weighs production + shipping time against the event deadline. → `MerchandiseResearch` |
| **Purchasing** | deep | The **only** agent that completes checkouts. Proceeds only when the task text explicitly grants approval for that exact item and amount; otherwise researches up to the payment step and aborts. States the tradeoff weighed (budget cap, deadline, quality, cancellation policy) before paying. → `PurchaseReport` |
| **Marketing** | deep | Produces ready-to-publish collateral — listing descriptions, announcement emails, social posts — per channel, audience, and tone, grounded in the event's real facts, plus visual direction for a designer or image tool. → `MarketingCollateral` |
| **Distribution** | fast | Publishes and maintains listings on **Luma, Partiful, Eventbrite, and Meetup** using the marketing agent's copy, records each live public URL, and edits existing listings on updates. One platform being blocked never stops the others. → `DistributionReport` |
| **Scheduling** | fast | Manages the signed-in Google Calendar — vendor calls, tours, payment deadlines, delivery windows, staff shifts, setup, rehearsals, catering arrivals, sessions, cleanup — checking each slot for collisions before booking. → `ScheduleReport` |
| **Budget** | deep | Keeps the live budget honest: estimated vs. confirmed vs. paid, deposits, refund policies, and savings, verifying every figure at its source URL so an estimate never masquerades as a commitment. → `BudgetReview` |
| **Post-event** | deep | Settles the wrap-up — final vendor payments, thank-yous, feedback surveys, receipt collection, refund requests, and media gathering — replying in-thread per vendor. Payments and refunds are approval-gated; the rest runs on its own. → `PostEventReport` |

**Workflows (`workflows/`).** Multi-agent pipelines for jobs that cross agent
boundaries. They chain browserless Holo reasoning with fleets of parallel
computer-use sessions (run in **waves of three**, the H session cap), and keep
binding actions behind their own approval-gated calls.

*`event_planning`* — turns a client brief into a full plan and the tasks to execute
it. (1) the requirements agent structures the brief; (2) a deep Holo completion
synthesizes the plan — timeline, budget, checklist, vendor categories, deadlines,
schedules, backups, risks; (3) pure code derives one pinned, guard-railed research
task per vendor category, so every planned category is dispatchable by construction;
(4) the scheduling agent optionally drops key deadlines on the calendar. This module
is the pipeline's import root — sourcing and outreach build on its plan models.

*`vendor_sourcing`* — turns the plan into a ranked, compared shortlist. (1) H's deep-
search agent optionally sweeps the web for candidate URLs; (2) a deep Holo completion
compiles each category's needs into a browser brief shaped the way H's docs say runs
succeed — explicit start URL, ordered steps, success criteria; (3) the category
agents research in parallel waves, each session bounded at 40 minutes; (4) a deep
completion merges every category's findings into one shortlist with per-category
rankings, gaps, and cross-category tradeoffs. Booking is a separate, approval-gated
`book` call, never part of research.

*`vendor_outreach`* — contacts shortlisted vendors and tracks what returns. (1) code
picks the best-ranked candidates per category; (2) a deep completion drafts a
personalized inquiry per vendor; (3) H's general web agent sends each — inquiry form
where one exists, signed-in Gmail otherwise — in parallel waves; (4) a deep completion
turns the send reports into a quote comparison with escalations for the decisions only
the user can make. `follow_up` chases silent vendors (checking the thread first so a
reply is never double-nudged) and `negotiate` sends one propose-only counter; sends go
through the general web agent so an unrepeatable action never reads as a retryable
failure.

**Planning (`planning/`).** The reasoning layer behind the plan — `task_graph` (the
DAG), `constraints`, `budget_optimizer`, `schedule_optimizer`, `risk_analyzer`.

**Memory (`memory/`).** Event, user, and vendor memory plus a semantic store. H's
Models API exposes no embeddings, so retrieval uses **Postgres full-text search
(`tsvector`)** rather than a vector index. On every event-scoped run, stored context
— the brief, plan, decisions, preferences, and relevant notes — is threaded into the
H prompt so a fresh session inherits what the project already knows.

**Approvals (`approvals/`).** `sensitive_actions` classifies what needs a human,
`spending_rules` enforces user-defined limits (spend under the limit bypasses the
gate), and `approval_manager` holds the pending decision until it's resolved.

**Runs & recovery (`core/runs.py`, `core/supervisor.py`).** Work is asynchronous:
`POST /chat` creates an `agent_runs` row and kicks off a background execution the
frontend polls via `GET /runs/{id}`. On boot, a sweep marks runs left `running` by a
dead process as interrupted, and a reconciler republishes what their finished H
sessions and memory snapshots still hold — no run is silently lost.

---

## Integrations

**H Company (`integrations/h_company/`).** Two seams, both key-driven from the
environment:

- **Models API** — OpenAI-compatible completions on Holo models
  (`holo3-1-35b-a3b` fast for routing, `holo3-122b-a10b` deep for agent reasoning).
  Used for task routing and any browserless step.
- **Computer-use sessions** — the AGP host drives a real **cloud Chrome** that opens
  at Google and reuses a persisted, signed-in profile. That logged-in profile is why
  Occasion needs no Gmail / Calendar / Luma / Eventbrite API keys — H operates those
  sites the way a person does. `session.py` builds both the per-run browser
  `overrides` for H's managed `h/web-surfer-flash` and full inline web-agent
  definitions for the domain fleet.

**Gradium (`integrations/gradium/`).** Voice over REST (`x-api-key`), served under
`/voice`: `speech_to_text`, `text_to_speech`, and `streaming` for conversational
turns. STT ingests WAV / PCM / ogg-opus, so the browser mic capture is transcoded to
WAV client-side before upload.

**Security (`core/security.py`, `core/config.py`).** Sandboxing is enforced in code,
not external infra: a domain **allow-list** in config plus a prompt-level
`domain_guardrail`, alongside the approval gates and full run logging.

---

## Monorepo layout

```
apps/web            Next.js frontend — dashboard, event workspace, voice, chat
services/agent      FastAPI backend — orchestrator, agent fleet, workflows, integrations
packages/shared     JSON Schemas (event, task, approval) + constants shared across web & agent
infra/              Dockerfiles and dev scripts (setup, run-dev, migrate, seed)
docs/               Architecture notes and runbooks
.github/workflows   CI for web and agent
```

**`services/agent`** — `core/` (orchestrator, supervisor, runs, state, config,
security, logging) · `agents/` (the 13-agent fleet + base) · `workflows/` ·
`integrations/` (`h_company`, `gradium`) · `planning/` · `approvals/` · `memory/` ·
`api/routes/` (events, chat, runs, approvals, voice, webhooks, computer-use) ·
`database/` · `models/` · `tests/`.

**`apps/web`** — App Router pages (`/` landing, `/ask` intake, `/dashboard`,
`/event`, `/projects`) over components like `EventDashboard`, `ChatPanel`,
`ApprovalsPanel`, `BudgetTracker`, `VoiceAssistant`, and `TaskBoard`. Cross-panel
state lives in `hooks/useEvent.ts`; the API seam is `lib/api.ts`.

---

## Tech stack

| Layer      | Choice |
|------------|--------|
| Frontend   | Next.js 16 (App Router), React 19, Tailwind CSS v4 |
| Backend    | FastAPI, Python 3, `hai-agents` SDK |
| Data       | Postgres (Supabase-compatible or local), sync SQLAlchemy 2.0 + `psycopg` 3 |
| Web agency | H Company computer-use (cloud Chrome) + Holo Models API |
| Voice      | Gradium STT / TTS |
| HTTP       | `httpx` (async) |

---

## Quickstart

```bash
make setup      # install web + agent deps (creates services/agent/.venv)
make migrate    # apply database/migrations/*.sql (tracked in schema_migrations)
make seed       # insert the demo event (novaflow-summit-2026)
make dev        # run web (:3000) and agent (:8000) together
# or, containerized:
make up         # docker compose: web + agent + postgres
```

Credentials live next to the code that reads them: the agent service loads
`services/agent/.env` (see `core/config.py`) and the web app loads
`apps/web/.env.local`. The repo-root **`.env.example`** documents both sets and every
`HAI_*` / `GRADIUM_*` variable. Individual targets (`web`, `agent`, `migrate`,
`seed`, `test`) live in the `Makefile`.

---

Built by Amresh Balakrishnan · SF hackathon, July 2026.
