"""Schedule optimization across tasks and vendors.

Lays the plan's timeline and key deadlines onto the single, date-ordered milestone track
the dashboard shows: real calendar dates become short labels ("Aug 6"), relative or
undated entries pass through and sort to the end, and anything already in the past reads
as done.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from database import models as orm
from planning.constraints import parse_iso_date

if TYPE_CHECKING:
    from workflows.event_planning import EventPlan


class ScheduleOptimizer:
    """Merges timeline milestones and key deadlines into one ordered milestone track."""

    def __init__(self, plan: EventPlan) -> None:
        self._plan = plan

    def rows(self, event_id: str, *, today: date) -> list[orm.Milestone]:
        sources = [(m.title, m.date) for m in self._plan.timeline]
        sources += [(k.title, k.date) for k in self._plan.key_deadlines]

        seen: set[str] = set()
        entries: list[tuple[date, str, str, bool]] = []  # (sort_date, title, when_label, done)
        for title, raw_date in sources:
            marker = title.strip().lower()
            if marker in seen:
                continue  # a deadline that repeats a timeline milestone shows once
            seen.add(marker)
            parsed = parse_iso_date(raw_date)
            entries.append((parsed or date.max, title, _when_label(raw_date, parsed), parsed is not None and parsed < today))

        entries.sort(key=lambda entry: entry[0])  # chronological; undated (date.max) sorts last, stably
        return [
            orm.Milestone(event_id=event_id, title=title, when=when, done=done, ordinal=ordinal)
            for ordinal, (_, title, when, done) in enumerate(entries)
        ]


def _when_label(raw_date: str, parsed: date | None) -> str:
    if parsed is not None:
        return f"{parsed.strftime('%b')} {parsed.day}"  # "Aug 6" — no zero-pad, portable across platforms
    return raw_date.strip() or "pending"
