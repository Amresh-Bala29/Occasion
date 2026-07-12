"""Marketing agent — creates marketing assets and campaigns."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class ChannelCopy(BaseModel):
    """Ready-to-publish copy for one channel."""

    channel: str = Field(description="Where this runs: event page, email, social platform, ...")
    audience: str
    tone: str
    headline: str
    body: str
    call_to_action: str


class MarketingCollateral(BaseModel):
    """The marketing agent's structured answer: per-channel copy plus visual direction."""

    assets: list[ChannelCopy]
    image_suggestions: list[str] = Field(default=[], description="Visual directions for a designer or image tool.")
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's marketing specialist. You produce the collateral that promotes the
event — listing descriptions, announcement emails, social posts — and research what the
event's audience actually responds to.

Working method:
- Write for the audience, tone, and channels the task specifies; every asset states
  which channel it's for.
- Ground claims in the event's real facts (date, venue, program, speakers) from the
  task; invent nothing.
- Research comparable events' pages when the task asks for positioning, and cite the
  pages you drew from.
- Deliver complete, ready-to-publish copy — headline, body, call to action — not
  outlines. Publishing itself is the distribution agent's job.

You create assets; you do not post, send, or purchase ads."""


class MarketingAgent(BaseAgent):
    """Marketing agent — creates marketing assets and campaigns."""

    name = "marketing"
    description = "Writes ready-to-publish event marketing copy per channel; hands publishing to distribution."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Collateral generation leans on the deep model's 32K output ceiling.
    max_time_s = 1200
    max_steps = 50
    answer_schema = MarketingCollateral
