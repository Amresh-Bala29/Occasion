"""Base agent — shared interface and lifecycle for all domain agents."""

from __future__ import annotations

from typing import Any


class BaseAgent:
    """Common surface every domain agent implements."""

    name: str = "base"

    def __init__(self, context: Any | None = None) -> None:
        self.context = context

    async def run(self, task: Any) -> Any:
        raise NotImplementedError
