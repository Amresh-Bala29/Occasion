"""Tests for agent memory: the domain models, the behavior handles, and the workflow
wiring that reads and writes them.

Nothing here touches a database. Pure-domain cases test the models directly; handle and
facade cases run the real memory handles against an in-memory FakeMemoryRepository; the
workflow choreography cases reuse the H/Models-API doubles from test_workflows and assert
what each workflow records. The repository's real SQL (Postgres full-text) is validated
out-of-band, exactly as EventRepository's is.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

# The agent root (for `core`, `memory`, …) and the tests dir (to reuse test_workflows).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.requirements_agent import EventRequirements  # noqa: E402
from core.config import settings  # noqa: E402
from core.state import Memory  # noqa: E402
from integrations.h_company.client import HClient  # noqa: E402
from memory.event_memory import PLAN_SNAPSHOT, REQUIREMENTS, SHORTLIST  # noqa: E402
from memory.user_preferences import DEFAULT_USER_ID, PreferencesMemory, UserPreferences  # noqa: E402
from memory.vector_store import (  # noqa: E402
    MemoryDocument,
    MemoryHit,
    SemanticMemory,
    event_scope,
    user_scope,
    vendor_scope,
)
from memory.vendor_memory import VendorEngagement, VendorMemory, VendorReputation, vendor_key_for  # noqa: E402
from workflows.event_planning import EventPlanningWorkflow  # noqa: E402
from workflows.vendor_outreach import VendorOutreachWorkflow  # noqa: E402
from workflows.vendor_sourcing import VendorCandidate, VendorSourcingWorkflow  # noqa: E402
from test_workflows import (  # noqa: E402
    FakeResearch,
    FakeSDK,
    briefs_content,
    browser_failure,
    browser_success,
    completion_script,
    drafts_content,
    make_plan,
    make_shortlist,
    plan_content,
    requirements_content,
    shortlist_content,
)


class FakeMemoryRepository:
    """In-memory stand-in for MemoryRepository: exercises the real memory handles and facade
    without a database. Full-text search degrades to a case-insensitive substring match,
    enough to assert recall wiring; scope filtering mirrors the repository's prefix rule.
    """

    def __init__(self) -> None:
        self.prefs: dict[str, UserPreferences] = {}
        self.vendors: dict[str, VendorReputation] = {}
        self.events: dict[tuple[str, str], Any] = {}
        self.documents: list[MemoryDocument] = []

    def get_user_preferences(self, user_id: str) -> UserPreferences | None:
        return self.prefs.get(user_id)

    def upsert_user_preferences(self, prefs: UserPreferences) -> UserPreferences:
        self.prefs[prefs.user_id] = prefs.model_copy(deep=True)
        return self.prefs[prefs.user_id]

    def get_vendor_reputation(self, vendor_key: str) -> VendorReputation | None:
        return self.vendors.get(vendor_key)

    def record_engagement(
        self, *, vendor_key, name, kind, category=None, url=None, event_id=None, note=None
    ) -> VendorReputation:
        counter = {"contacted": "times_contacted", "quoted": "times_quoted", "booked": "times_booked"}[kind]
        rep = self.vendors.get(vendor_key) or VendorReputation(
            vendor_key=vendor_key, name=name, category=category, url=url
        )
        setattr(rep, counter, getattr(rep, counter) + 1)
        rep.history = [*rep.history, VendorEngagement(event_id=event_id, kind=kind, note=note)]
        rep.name = name or rep.name
        rep.category = category or rep.category
        rep.url = url or rep.url
        self.vendors[vendor_key] = rep
        return rep

    def top_vendors(self, *, category: str, limit: int = 5) -> list[VendorReputation]:
        matches = [v for v in self.vendors.values() if v.category == category]
        return sorted(matches, key=lambda v: v.times_booked, reverse=True)[:limit]

    def get_event_memory(self, event_id: str, key: str) -> Any | None:
        return self.events.get((event_id, key))

    def set_event_memory(self, *, event_id: str, key: str, value: Any) -> None:
        self.events[(event_id, key)] = value

    def all_event_memory(self, event_id: str) -> dict[str, Any]:
        return {key: value for (eid, key), value in self.events.items() if eid == event_id}

    def add_document(self, *, scope, kind, content, metadata=None, event_id=None) -> MemoryDocument:
        doc = MemoryDocument(
            id=len(self.documents) + 1, scope=scope, kind=kind, content=content, metadata=metadata or {}, event_id=event_id
        )
        self.documents.append(doc)
        return doc

    def search(self, *, query: str, scope: str | None = None, limit: int = 5) -> list[MemoryHit]:
        hits = []
        for doc in self.documents:
            if scope is not None and not (doc.scope == scope or doc.scope.startswith(f"{scope}:")):
                continue
            if query.casefold() in doc.content.casefold():
                hits.append(MemoryHit(document=doc, rank=1.0))
        return hits[:limit]


# ---- Pure domain ----


def test_vendor_key_prefers_domain_and_strips_www() -> None:
    assert vendor_key_for("The Grand Hall", "https://www.GrandHall.com/contact") == "grandhall.com"
    # A bare host (no scheme) still resolves to the domain.
    assert vendor_key_for("X", "grandhall.example.com/quote") == "grandhall.example.com"


def test_vendor_key_falls_back_to_a_stable_name_slug() -> None:
    key = vendor_key_for("The Grand Hall!")
    assert key == "the-grand-hall"
    # Case- and punctuation-insensitive, and idempotent when re-applied to its own output.
    assert vendor_key_for("the grand hall") == key
    assert vendor_key_for(key) == key
    assert vendor_key_for("") == "vendor"


def test_user_preferences_merge_unions_dedupes_and_is_order_independent() -> None:
    base = UserPreferences(user_id="u1", dietary_restrictions=["Vegan"])
    first = EventRequirements(dietary_restrictions=["vegan", "nut-free"], priorities=["budget"])
    second = EventRequirements(dietary_restrictions=["gluten-free"], priorities=["budget", "sustainability"])

    forward = base.merge(first).merge(second)
    backward = base.merge(second).merge(first)

    # Case-insensitive dedupe keeps the first spelling; order of merges doesn't change the set.
    assert forward.dietary_restrictions == ["Vegan", "nut-free", "gluten-free"]
    assert set(forward.dietary_restrictions) == set(backward.dietary_restrictions)
    assert set(forward.priorities) == {"budget", "sustainability"}


def test_reputation_score_is_neutral_by_default_and_rises_with_evidence() -> None:
    unseen = VendorReputation(vendor_key="x", name="X")
    assert unseen.reputation_score == 0.5

    rated = VendorReputation(vendor_key="x", name="X", reliability_rating=5, quality_rating=5)
    assert rated.reputation_score > unseen.reputation_score

    booked_once = VendorReputation(vendor_key="x", name="X", times_booked=1)
    booked_twice = VendorReputation(vendor_key="x", name="X", times_booked=2)
    assert booked_twice.reputation_score >= booked_once.reputation_score > unseen.reputation_score
    assert VendorReputation(vendor_key="x", name="X", reliability_rating=5, quality_rating=5, times_booked=3).reputation_score <= 1.0


def test_scope_builders() -> None:
    assert event_scope("evt-9") == "event:evt-9"
    assert event_scope("evt-9", "catering") == "event:evt-9:catering"
    assert vendor_scope("grandhall.com") == "vendor:grandhall.com"
    assert user_scope("u1") == "user:u1"


def test_as_prompt_note_summarizes_only_known_fields() -> None:
    assert UserPreferences(user_id="u1").as_prompt_note() is None
    note = UserPreferences(user_id="u1", dietary_restrictions=["vegan"], blocked_vendors=["BadCo"]).as_prompt_note()
    assert "Dietary restrictions: vegan" in note
    assert "Vendors to avoid: BadCo" in note
    assert "Food preferences" not in note  # empty fields are omitted


# ---- Handles and facade (real handles over the in-memory repository) ----


def test_preferences_accumulate_persists_and_merges_across_events() -> None:
    prefs = PreferencesMemory(FakeMemoryRepository())
    prefs.accumulate(EventRequirements(dietary_restrictions=["vegan"]), user_id="u1")
    merged = prefs.accumulate(EventRequirements(dietary_restrictions=["nut-free"], food_preferences=["tacos"]), user_id="u1")

    assert merged.dietary_restrictions == ["vegan", "nut-free"]
    assert merged.food_preferences == ["tacos"]
    # A never-seen user reads back empty, not an error.
    assert prefs.get("someone-else").dietary_restrictions == []
    assert prefs.get().user_id == DEFAULT_USER_ID


def test_vendor_memory_records_increment_counters_and_history() -> None:
    vendors = VendorMemory(FakeMemoryRepository())
    candidate = VendorCandidate(category="venue", name="The Grand Hall", url="https://grandhall.example.com")

    vendors.record_contacted(candidate, event_id="evt-9")
    vendors.record_quoted(candidate, total_usd=7500, event_id="evt-9")
    rep = vendors.record_booked(candidate, event_id="evt-9")

    assert (rep.times_contacted, rep.times_quoted, rep.times_booked) == (1, 1, 1)
    assert [engagement.kind for engagement in rep.history] == ["contacted", "quoted", "booked"]
    assert vendors.reputation_for(candidate).vendor_key == "grandhall.example.com"
    assert vendors.top_by_category("venue")[0].name == "The Grand Hall"


def test_event_memory_roundtrips_values() -> None:
    memory = Memory(FakeMemoryRepository())
    event = memory.event("evt-9")
    assert event.get(PLAN_SNAPSHOT) is None
    event.set(PLAN_SNAPSHOT, {"event_summary": "A conference"})
    assert event.get(PLAN_SNAPSHOT) == {"event_summary": "A conference"}
    assert memory.event("evt-9").all() == {PLAN_SNAPSHOT: {"event_summary": "A conference"}}


def test_semantic_add_and_search_by_scope() -> None:
    semantic = SemanticMemory(FakeMemoryRepository())
    semantic.add_document("The Grand Hall seats 150", scope=event_scope("evt-9", "venue"), kind="research", event_id="evt-9")
    semantic.add_document("Verde does vegan catering", scope=event_scope("evt-9", "catering"), kind="research", event_id="evt-9")
    semantic.add_document("Unrelated note", scope=event_scope("evt-1"), kind="note")

    # Event-level scope recalls every document filed under the event's sub-scopes.
    hits = semantic.search("grand", scope=event_scope("evt-9"))
    assert [hit.document.content for hit in hits] == ["The Grand Hall seats 150"]
    assert semantic.search("note", scope=event_scope("evt-9")) == []


# ---- Workflow choreography (real memory over the in-memory repository) ----


def test_planning_writes_preferences_and_snapshot_then_resumes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    memory = Memory(FakeMemoryRepository())
    repo = memory._repo

    http, _ = completion_script(requirements_content(), plan_content())
    flow = EventPlanningWorkflow(client=HClient(FakeSDK()), http_client=http, memory=memory)
    report = asyncio.run(flow.run("We want a 150-person conference in Austin.", event_id="evt-9", user_id="u1"))

    assert report.succeeded is True
    assert repo.get_event_memory("evt-9", REQUIREMENTS)["headcount"] == 150
    assert repo.get_event_memory("evt-9", PLAN_SNAPSHOT)["event_summary"].startswith("A 150-person")
    assert repo.get_user_preferences("u1") is not None  # the user's preference row now exists

    # A re-run recalls the plan snapshot: only requirements is parsed, synthesis is skipped.
    http2, requests2 = completion_script(requirements_content())
    flow2 = EventPlanningWorkflow(client=HClient(FakeSDK()), http_client=http2, memory=memory)
    report2 = asyncio.run(flow2.run("We want a 150-person conference in Austin.", event_id="evt-9", user_id="u1"))

    assert report2.succeeded is True
    assert report2.plan.event_summary.startswith("A 150-person")
    assert report2.plan_run is None  # synthesis was skipped
    assert len(requests2) == 1


def test_planning_accumulates_stated_dietary_preferences(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    memory = Memory(FakeMemoryRepository())
    requirements = {**requirements_content(), "dietary_restrictions": ["vegan", "nut-free"]}
    http, _ = completion_script(requirements, plan_content())
    flow = EventPlanningWorkflow(client=HClient(FakeSDK()), http_client=http, memory=memory)

    asyncio.run(flow.run("Conference brief", event_id="evt-9", user_id="u1"))

    assert memory._repo.get_user_preferences("u1").dietary_restrictions == ["vegan", "nut-free"]


def test_book_records_reputation_only_on_success(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    candidate = VendorCandidate(category="venue", name="The Grand Hall", url="https://grandhall.example.com")

    booked = Memory(FakeMemoryRepository())
    flow = VendorSourcingWorkflow(client=HClient(FakeSDK(default=browser_success("booked"))), memory=booked)
    asyncio.run(flow.book(candidate, event_id="evt-9", approval="approved for $7,500"))
    assert booked._repo.get_vendor_reputation("grandhall.example.com").times_booked == 1

    failed = Memory(FakeMemoryRepository())
    flow = VendorSourcingWorkflow(client=HClient(FakeSDK(default=browser_failure("site down"))), memory=failed)
    asyncio.run(flow.book(candidate, event_id="evt-9", approval="approved"))
    assert failed._repo.get_vendor_reputation("grandhall.example.com") is None


def test_sourcing_records_research_then_resumes_from_shortlist(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    memory = Memory(FakeMemoryRepository())
    repo = memory._repo
    sdk = FakeSDK(
        routes=[
            ("peerspace", browser_success(FakeResearch(options=[{"name": "The Grand Hall"}]))),
            ("corporate+catering", browser_success(FakeResearch(options=[{"name": "Verde Catering"}]))),
        ]
    )
    http, _ = completion_script(briefs_content(), shortlist_content())
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http, memory=memory)
    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert report.succeeded is True
    assert any(doc.scope.startswith("event:evt-9") and doc.kind == "research" for doc in repo.documents)
    assert repo.get_event_memory("evt-9", SHORTLIST) is not None

    # A re-run returns the cached shortlist: no research fan-out, no completions.
    sdk2 = FakeSDK()
    http2, requests2 = completion_script()
    flow2 = VendorSourcingWorkflow(client=HClient(sdk2), http_client=http2, memory=memory)
    report2 = asyncio.run(flow2.run(make_plan(), event_id="evt-9"))

    assert report2.succeeded is True
    assert report2.shortlist.candidates[0].name == "The Grand Hall"
    assert sdk2.calls == []
    assert requests2 == []


def test_outreach_records_contacts_and_quotes_but_not_failed_sends(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    memory = Memory(FakeMemoryRepository())
    repo = memory._repo
    sdk = FakeSDK(default=browser_success("sent"), routes=[("Riverside Loft", browser_failure("form rejected"))])
    comparison = {
        "quotes": [
            {"vendor_name": "The Grand Hall", "category": "venue", "contacted": True, "channel": "form", "quoted_total_usd": 7500}
        ]
    }
    http, _ = completion_script(drafts_content(), comparison)
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=http, memory=memory)
    report = asyncio.run(flow.run(make_shortlist(), event_id="evt-9"))

    assert report.succeeded is True
    grand = repo.get_vendor_reputation(vendor_key_for("The Grand Hall", "https://grandhall.example.com"))
    assert (grand.times_contacted, grand.times_quoted) == (1, 1)
    # Riverside's send failed, so it was neither contacted nor quoted.
    assert repo.get_vendor_reputation(vendor_key_for("Riverside Loft", "https://riversideloft.example.com")) is None
