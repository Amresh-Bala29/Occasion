"""Long-term user preference memory.

What we've learned about one user's tastes, accumulated across every event they plan, so
later runs start from what they already told us instead of asking again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from agents.requirements_agent import EventRequirements
    from database.repositories.memory_repository import MemoryRepository

# Auth is deferred and the app is single-user today, so preferences key on this until real
# user identity exists. A workflow may pass an explicit user_id to override it.
DEFAULT_USER_ID = "default"


class UserPreferences(BaseModel):
    """One user's accumulated preferences. Snake_case and internal — never leaves the backend."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str = DEFAULT_USER_ID
    dietary_restrictions: list[str] = []
    food_preferences: list[str] = []
    entertainment_preferences: list[str] = []
    accessibility_needs: list[str] = []
    priorities: list[str] = []
    preferred_vendors: list[str] = []
    blocked_vendors: list[str] = []
    branding_notes: str | None = None

    def merge(self, requirements: EventRequirements) -> UserPreferences:
        """A copy with this event's stated preferences folded in.

        List fields union (existing first, then new, de-duplicated case-insensitively) so
        preferences only grow; branding notes take the latest stated value.
        """
        return self.model_copy(
            update={
                "dietary_restrictions": _union(self.dietary_restrictions, requirements.dietary_restrictions),
                "food_preferences": _union(self.food_preferences, requirements.food_preferences),
                "entertainment_preferences": _union(
                    self.entertainment_preferences, requirements.entertainment_preferences
                ),
                "accessibility_needs": _union(self.accessibility_needs, requirements.accessibility_needs),
                "priorities": _union(self.priorities, requirements.priorities),
                "branding_notes": requirements.branding_notes or self.branding_notes,
            }
        )

    def as_prompt_note(self) -> str | None:
        """A short summary of what's known, for folding into a planning or sourcing prompt.

        None when nothing is known yet, so callers can skip the section entirely.
        """
        fields = [
            ("Dietary restrictions", self.dietary_restrictions),
            ("Food preferences", self.food_preferences),
            ("Entertainment preferences", self.entertainment_preferences),
            ("Accessibility needs", self.accessibility_needs),
            ("Stated priorities", self.priorities),
            ("Preferred vendors", self.preferred_vendors),
            ("Vendors to avoid", self.blocked_vendors),
        ]
        lines = [f"{label}: {', '.join(values)}" for label, values in fields if values]
        if not lines:
            return None
        return "Known preferences for this user (from earlier events):\n" + "\n".join(lines)


def _union(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    seen = {item.casefold() for item in existing}
    for item in incoming:
        if item.casefold() not in seen:
            merged.append(item)
            seen.add(item.casefold())
    return merged


class PreferencesMemory:
    """Reads and accumulates one user's long-term preferences."""

    def __init__(self, repo: MemoryRepository) -> None:
        self._repo = repo

    def get(self, user_id: str | None = None) -> UserPreferences:
        """The stored preferences for `user_id`, or an empty set if we've never seen them."""
        user_id = user_id or DEFAULT_USER_ID
        return self._repo.get_user_preferences(user_id) or UserPreferences(user_id=user_id)

    def accumulate(self, requirements: EventRequirements, *, user_id: str | None = None) -> UserPreferences:
        """Fold this event's requirements into the user's stored preferences and persist."""
        merged = self.get(user_id).merge(requirements)
        return self._repo.upsert_user_preferences(merged)
