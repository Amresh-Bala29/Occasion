# @occasion/shared

Cross-cutting contracts shared by `apps/web` and `services/agent`.

- `schemas/` — JSON Schemas defining the wire contract for events, tasks, and
  approvals. Consumed by both the TypeScript frontend and the Python backend, so
  the two stay in sync.
- `constants/` — shared constant values.
