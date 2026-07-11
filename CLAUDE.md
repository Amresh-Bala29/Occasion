## Code quality
Write code a human can read top-to-bottom and understand without a debugger.

- **Clarity over cleverness.** No dense one-liners, no implicit magic. If a line needs a comment to be understood, rewrite the line first.
- **Concise, not compressed.** Short because it's simple, not short because it's golfed. Prefer fewer moving parts over fewer characters.
- **Object-oriented, cohesive.** Model the domain with well-named classes/objects that own their data and behavior. One responsibility each. Favor composition over inheritance. Keep methods small.
- **Traceable.** Control flow should be obvious. Name things for what they do, not how. Avoid hidden side effects — a function's effects should be predictable from its signature and name.
- **Maintainable.** Optimize for the next person reading this cold in six months. Explicit over implicit, boring over surprising.

## Comments
- Comment the *why*, never the *what*. The code says what; comments explain intent, tradeoffs, and non-obvious constraints.
- Keep line comments short and concise. One line where possible — a brief note, not a paragraph.
- No commented-out code, no TODO graveyards. Delete dead code.

## Scaffold discipline — important
This project has an established structure. **Work within it.**

- **Do not create new files or folders unless absolutely necessary.** Default to editing existing files. New files are a last resort, not a convenience.
- Before creating anything, check whether an existing file is the right home for the code. It almost always is.
- If you believe a new file or folder is genuinely required, **stop and explain why first**, then wait for confirmation. Do not create it unprompted.
- Match the conventions already present: naming, directory layout, module boundaries, import style. Infer the pattern from neighboring files and follow it.
- Never restructure, rename, or move existing files/folders without being asked.

## Dependencies
- Install Python dependencies into the project's Pipenv environment: `pipenv install <package>`. Never use bare `pip`, and never install into the global or system environment.
- Run Python commands and scripts through Pipenv (`pipenv run ...`) so they resolve against the project environment.
- For non-Python deps, use the ecosystem's own manager (npm/pnpm, cargo) — don't route those through Pipenv.
- Don't add a dependency without a clear need. Prefer the standard library or something already installed first.

## Changes
- Make the smallest change that fully solves the problem. No opportunistic refactors, no scope creep.
- When touching existing code, preserve its style even if you'd have written it differently.
- If a task seems to require broad changes, surface the plan before executing.

## Before you finish
- Re-read your diff as a human reviewer would. Is the intent obvious? Could it be traced without running it?
- Confirm you added no files/folders that weren't strictly required.

## Project Objectives

Occasion is an autonomous AI event coordinator: it researches, communicates, purchases, schedules, and manages every part of an event directly through real websites and applications. The finished product must be able to:

1. **Gather event requirements conversationally.** Interview the user for event type, date and duration, location, headcount, budget, food, staffing, entertainment, branding/decoration, accessibility, and shipping deadlines — asking follow-up questions and capturing stated priorities. (`agents/requirements_agent.py`)
2. **Produce a full event plan.** Generate a timeline, estimated budget, task checklist, vendor categories, key deadlines, delivery and staffing schedules, backup options, and a risk assessment. (`workflows/event_planning.py`, `planning/`)
3. **Source venues end-to-end.** Search venue sites and marketplaces; check capacity, price, location, availability, equipment, and rules; contact managers, request quotes, schedule tours, compare options, and book the chosen venue after approval. (`agents/venue_agent.py`, `workflows/vendor_sourcing.py`)
4. **Arrange catering.** Find caterers, review menus and pricing, handle dietary restrictions, compute food quantities, request custom quotes, schedule meal and snack intervals, coordinate setup and cleanup, and book after approval. (`agents/catering_agent.py`)
5. **Run vendor communication.** Send emails, complete inquiry forms, request and compare quotes, follow up automatically, negotiate basic terms, keep each vendor thread organized, and escalate important decisions to the user. (`workflows/vendor_outreach.py`, `integrations/email/`)
6. **Source and manage temporary staffing.** Hire registration, setup/cleanup, security, bartenders, servers, technical support, photographers, videographers, coordinators, and medical personnel — managing shifts, arrival times, and contacts. (`agents/staffing_agent.py`)
7. **Book entertainment.** Find and hire DJs, musicians, speakers, hosts, comedians, performers, photobooths, and interactive activities, comparing price, availability, technical requirements, and reviews. (`agents/entertainment_agent.py`)
8. **Buy decorations and supplies.** Purchase signage, banners, linens, lighting, name tags, furniture, stage equipment, registration supplies, gifts, prizes, and cleaning materials. (`agents/decorations_agent.py`, `agents/purchasing_agent.py`)
9. **Produce custom-branded products.** From a user-uploaded logo, find manufacturers, request quotes, upload artwork, choose materials and quantities, weigh production and shipping times, pay for expedited runs when needed, and track delivery. (`agents/merchandise_agent.py`)
10. **Purchase intelligently.** Reason over budget limits, shipping deadlines, vendor reliability, quality-vs-cost, bulk discounts, expedited shipping, cancellation policies, and backup suppliers — and state the tradeoff before acting. (`agents/purchasing_agent.py`, `planning/budget_optimizer.py`)
11. **Manage the calendar.** Schedule vendor calls, venue tours, payment deadlines, delivery windows, staff shifts, setup, rehearsals, catering arrivals, event sessions, and cleanup. (`agents/scheduling_agent.py`, `integrations/calendar/`)
12. **Maintain a live budget.** Track estimated vs. confirmed cost, amount paid, remaining budget, deposits, refund policies, unexpected expenses, and suggested savings. (`agents/budget_agent.py`)
13. **Enforce human approval gates.** Research and prepare actions autonomously, but require approval before sensitive ones — important emails, contracts, bookings, purchases, deposits, sharing private data — honoring user-defined spending limits that bypass approval. (`approvals/`)
14. **Drive the event dashboard.** Surface overall completion percentage, budget status, confirmed vendors, pending approvals, upcoming deadlines, deliveries, staff schedules, vendor messages, risks, and recommended next actions. (`apps/web`, `components/EventDashboard.tsx`)
15. **Coordinate the day of the event.** Monitor vendor arrivals, deliveries, staff check-ins, schedule delays, catering intervals, missing supplies, last-minute changes, weather, and attendee communications — contacting backups or adjusting schedules when problems occur. (`core/supervisor.py`)
16. **Handle post-event tasks.** Pay vendors, send thank-you emails, run feedback surveys, organize receipts, reconcile the budget, request refunds, collect photos and video, and generate a performance report. (`agents/post_event_agent.py`)
17. **Market and distribute the event.** Publish and manage listings across Luma, Partiful, Eventbrite, and Meetup, and generate the collateral to promote them. (`agents/marketing_agent.py`, `agents/distribution_agent.py`, `integrations/distribution/`)
18. **Execute real work through computer use.** Control websites and desktop applications via H Company to search vendors, fill forms, send emails, upload files, schedule meetings, make purchases, and manage calendars. (`integrations/h_company/`)
19. **Run in a sandboxed, auditable runtime.** Operate under NemoClaw with permission limits, secured credentials, restricted website access, full action logging, and human approval gates. (`infra/nemoclaw/`, `core/security.py`)
20. **Offer a natural voice experience.** Provide speech-to-text, text-to-speech, streaming conversation, natural interruptions, spoken confirmations, and real-time progress updates via Gradium. (`integrations/gradium/`)
21. **Actually execute, not just recommend.** Beyond checklists and suggestions, carry the real work — researching, communicating, purchasing, scheduling, and managing — across live websites and apps, functioning as a complete AI event coordinator.