"""Task DAG — builds and resolves task dependencies.

Turns the plan's flat, per-item checklist into the two groupings the dashboard's plan
tab reads: task *groups* (by owner) and lifecycle *phases* (by stage). The phases are the
event lifecycle in order — Discovery → Sourcing → Booking → Production → Day-of → Wrap-up
— and that order is the dependency edge set: a later stage cannot finish before the
earlier ones, so a phase's progress is simply how many of its tasks are done. The
checklist carries no explicit dependencies, so this canonical lifecycle is where they
come from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from database import models as orm
from planning.constraints import parse_iso_date
from workflows.event_planning import slug

if TYPE_CHECKING:
    from workflows.event_planning import ChecklistItem, EventPlan


# category -> (group name, owner label, tone). Decor and merch share one group, matching
# the seed's "Brand & decor"; anything unrecognized falls to the default coordinator group.
_CATEGORY_GROUPS: dict[str, tuple[str, str, str]] = {
    "venue": ("Venue & space", "Venue", "blue"),
    "catering": ("Food & beverage", "Catering", "green"),
    "entertainment": ("Experience", "Entertainment", "amber"),
    "decorations": ("Brand & decor", "Merch", "gray"),
    "merchandise": ("Brand & decor", "Merch", "gray"),
    "staffing": ("People & logistics", "Staffing", "blue"),
}
_DEFAULT_GROUP: tuple[str, str, str] = ("Logistics", "Coordinator", "gray")

# Free-text checklist categories reach the canonical keys above by keyword.
_CATEGORY_SYNONYMS: dict[str, str] = {
    "food": "catering",
    "beverage": "catering",
    "menu": "catering",
    "decor": "decorations",
    "signage": "decorations",
    "brand": "merchandise",
    "merch": "merchandise",
    "swag": "merchandise",
    "entertain": "entertainment",
    "experience": "entertainment",
    "staff": "staffing",
    "crew": "staffing",
    "people": "staffing",
}

# Group display order = the seed's order, with the default group last.
_GROUP_ORDER: list[str] = [
    "Venue & space",
    "Food & beverage",
    "Experience",
    "Brand & decor",
    "People & logistics",
    _DEFAULT_GROUP[0],
]

# The canonical lifecycle. Discovery is the plan itself — done by the time a plan is
# stored — and each other phase claims a task by a whole word in its title. Matching whole
# words, not substrings, keeps "signage" out of Booking's "sign".
_PHASES: list[str] = ["Discovery", "Sourcing", "Booking", "Production", "Day-of", "Wrap-up"]
_PHASE_KEYWORDS: dict[str, frozenset[str]] = {
    "Sourcing": frozenset({"research", "compare", "source", "sourcing", "find", "shortlist", "quote", "quotes", "explore"}),
    "Booking": frozenset({"book", "sign", "contract", "confirm", "deposit", "pay", "approve", "reserve", "hire", "negotiate"}),
    "Production": frozenset({"order", "upload", "produce", "print", "build", "install", "setup", "prepare", "rehearse", "rehearsal", "assemble", "design"}),
    "Day-of": frozenset({"loadin", "checkin", "arrivals", "onsite", "runofshow", "dayof"}),
    "Wrap-up": frozenset({"thank", "refund", "reconcile", "survey", "teardown", "payout", "wrap", "returns", "recap"}),
}
_DEFAULT_PHASE = "Production"
_WORD = re.compile(r"[a-z]+")


@dataclass
class PlannedGroup:
    """One task group with its tasks. The tasks' `group_id` is left unset — the repository
    fills it after the group row is flushed and assigns its database id."""

    name: str
    owner: str
    tone: str
    ordinal: int
    tasks: list[orm.PlanTask] = field(default_factory=list)


@dataclass
class _RawGroup:
    name: str
    owner: str
    tone: str
    items: list[ChecklistItem]


class TaskGraph:
    """The checklist resolved into ordered owner-groups and lifecycle phases."""

    def __init__(self, groups: list[_RawGroup], phase_counts: dict[str, list[int]]) -> None:
        self._groups = groups
        self._phase_counts = phase_counts  # phase name -> [done, total]

    @classmethod
    def from_plan(cls, plan: EventPlan) -> TaskGraph:
        by_name: dict[str, _RawGroup] = {}
        phase_counts: dict[str, list[int]] = {name: [0, 0] for name in _PHASES}
        phase_counts["Discovery"] = [1, 1]  # the plan exists, so discovery is complete

        for item in plan.checklist:
            name, owner, tone = _group_for(item.category)
            group = by_name.get(name)
            if group is None:
                group = _RawGroup(name=name, owner=owner, tone=tone, items=[])
                by_name[name] = group
            group.items.append(item)
            phase_counts[_phase_for(item.title)][1] += 1  # a fresh plan has nothing done yet

        groups = sorted(by_name.values(), key=lambda g: _group_ordinal(g.name))
        return cls(groups, phase_counts)

    def phase_rows(self, event_id: str) -> list[orm.PlanPhase]:
        rows = []
        for ordinal, name in enumerate(_PHASES):
            done, total = self._phase_counts[name]
            rows.append(
                orm.PlanPhase(
                    event_id=event_id,
                    name=name,
                    percent=_phase_percent(done, total),
                    note=_phase_note(done, total),
                    ordinal=ordinal,
                )
            )
        return rows

    def group_rows(self, event_id: str) -> list[PlannedGroup]:
        result = []
        seen_ids: set[str] = set()
        for ordinal, raw in enumerate(self._groups):
            tasks = [
                orm.PlanTask(
                    id=_unique_id(f"{event_id}-task-{slug(item.title)}", seen_ids),
                    label=item.title,
                    done=False,
                    ordinal=index,
                )
                for index, item in enumerate(_ordered_by_due(raw.items))
            ]
            result.append(PlannedGroup(name=raw.name, owner=raw.owner, tone=raw.tone, ordinal=ordinal, tasks=tasks))
        return result

    def percent_complete(self) -> int:
        percents = [_phase_percent(*self._phase_counts[name]) for name in _PHASES]
        return round(sum(percents) / len(percents)) if percents else 0


def _group_for(category: str) -> tuple[str, str, str]:
    key = _canonical_category(category)
    return _CATEGORY_GROUPS[key] if key is not None else _DEFAULT_GROUP


def _canonical_category(category: str) -> str | None:
    text = (category or "").strip().lower()
    if text in _CATEGORY_GROUPS:
        return text
    for keyword, canonical in _CATEGORY_SYNONYMS.items():
        if keyword in text:
            return canonical
    return None


def _group_ordinal(name: str) -> int:
    return _GROUP_ORDER.index(name) if name in _GROUP_ORDER else len(_GROUP_ORDER)


def _phase_for(title: str) -> str:
    lowered = title.lower()
    words = set(_WORD.findall(lowered))
    # Hyphenated compounds ("load-in", "day-of") also count as one word, so the
    # collapsed Day-of keywords can match them; plain tokens still cover the rest.
    words.update(_WORD.findall(lowered.replace("-", "")))
    for phase, keywords in _PHASE_KEYWORDS.items():
        if words & keywords:
            return phase
    return _DEFAULT_PHASE


def _phase_percent(done: int, total: int) -> int:
    return round(100 * done / total) if total else 0


def _phase_note(done: int, total: int) -> str:
    if total == 0:
        return "Not started"
    if done == total:
        return "Done"
    return f"{done} of {total}"


def _ordered_by_due(items: list[ChecklistItem]) -> list[ChecklistItem]:
    # Dated tasks first, in date order; undated tasks keep their original order at the end.
    def key(pair: tuple[int, ChecklistItem]) -> tuple[date, int]:
        index, item = pair
        return (parse_iso_date(item.due) or date.max, index)

    return [item for _, item in sorted(enumerate(items), key=key)]


def _unique_id(base: str, seen: set[str]) -> str:
    candidate, suffix = base, 2
    while candidate in seen:
        candidate = f"{base}-{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate
