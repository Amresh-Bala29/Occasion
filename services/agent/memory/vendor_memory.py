"""Vendor history and reputation memory.

What we've learned about a vendor across every event we've used them on — how often we've
contacted, quoted, and booked them, and how they've rated — so shortlist ranking can favor
proven vendors. Keyed by vendor identity (domain or name slug), not by event, so it is
distinct from the per-event `vendors` display table.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from database.repositories.memory_repository import MemoryRepository
    from workflows.vendor_sourcing import VendorCandidate


def vendor_key_for(name: str, url: str | None = None) -> str:
    """A stable identity for a vendor across events: its bare domain when we have a URL,
    else a slug of its name. Case-insensitive and punctuation-normalized so the same
    vendor always resolves to the same key."""
    if url:
        host = _domain(url)
        if host:
            return host
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return slug or "vendor"


def _domain(url: str) -> str:
    # urlparse needs a scheme to populate netloc; add a bare-authority one for "example.com".
    candidate = url if "://" in url else f"//{url}"
    host = urlparse(candidate).netloc.casefold()
    return host[4:] if host.startswith("www.") else host


class VendorEngagement(BaseModel):
    """One recorded touch with a vendor, for the reputation audit trail."""

    event_id: str | None = None
    kind: str  # contacted | quoted | booked
    note: str | None = None


class VendorReputation(BaseModel):
    """A vendor's accumulated reputation. Snake_case and internal — never leaves the backend."""

    model_config = ConfigDict(from_attributes=True)

    vendor_key: str
    name: str
    category: str | None = None
    url: str | None = None
    times_contacted: int = 0
    times_quoted: int = 0
    times_booked: int = 0
    reliability_rating: int | None = None
    quality_rating: int | None = None
    history: list[VendorEngagement] = []
    notes: str | None = None

    @property
    def reputation_score(self) -> float:
        """A 0–1 ranking signal: neutral until proven, lifted by ratings and repeat bookings.

        An unseen vendor scores 0.5. Ratings (1–5) pull the average toward their value;
        each of the first few bookings adds a small, saturating bonus.
        """
        signals = [0.5]
        if self.reliability_rating is not None:
            signals.append(self.reliability_rating / 5)
        if self.quality_rating is not None:
            signals.append(self.quality_rating / 5)
        booked_bonus = min(self.times_booked, 3) * 0.1
        return min(1.0, sum(signals) / len(signals) + booked_bonus)


class VendorMemory:
    """Records vendor engagements and recalls their reputation for ranking."""

    def __init__(self, repo: MemoryRepository) -> None:
        self._repo = repo

    def reputation_for(self, candidate: VendorCandidate) -> VendorReputation:
        """This candidate's stored reputation, or a neutral default if we've never used them."""
        key = vendor_key_for(candidate.name, candidate.url)
        return self._repo.get_vendor_reputation(key) or VendorReputation(
            vendor_key=key, name=candidate.name, category=candidate.category, url=candidate.url
        )

    def top_by_category(self, category: str, *, limit: int = 3) -> list[VendorReputation]:
        """Vendors we've booked most in this category — the ones worth surfacing to a ranker."""
        return self._repo.top_vendors(category=category, limit=limit)

    def record_contacted(self, candidate: VendorCandidate, *, event_id: str | None = None) -> VendorReputation:
        return self._record(candidate, kind="contacted", event_id=event_id, note=None)

    def record_quoted(
        self, candidate: VendorCandidate, *, total_usd: float | None = None, event_id: str | None = None
    ) -> VendorReputation:
        note = f"quoted ${total_usd:.0f}" if total_usd is not None else None
        return self._record(candidate, kind="quoted", event_id=event_id, note=note)

    def record_booked(self, candidate: VendorCandidate, *, event_id: str | None = None) -> VendorReputation:
        return self._record(candidate, kind="booked", event_id=event_id, note=None)

    def _record(
        self, candidate: VendorCandidate, *, kind: str, event_id: str | None, note: str | None
    ) -> VendorReputation:
        return self._repo.record_engagement(
            vendor_key=vendor_key_for(candidate.name, candidate.url),
            name=candidate.name,
            category=candidate.category,
            url=candidate.url,
            kind=kind,
            event_id=event_id,
            note=note,
        )
