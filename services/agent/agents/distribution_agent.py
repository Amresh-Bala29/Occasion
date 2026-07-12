"""Distribution agent — publishes the event across distribution channels."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_FAST


class ListingResult(BaseModel):
    """The outcome of publishing (or updating) the event on one platform."""

    platform: str
    listing_url: str | None = Field(None, description="Public URL of the live listing.")
    status: str = Field(description="published | updated | blocked | failed, with the reason in notes.")
    notes: str | None = None


class DistributionReport(BaseModel):
    """The distribution agent's structured answer: one result per platform."""

    listings: list[ListingResult]
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's distribution specialist. You publish and maintain the event's
listings on Luma, Partiful, Eventbrite, and Meetup, using the copy and details the task
provides.

Working method:
- Publish exactly the title, description, date/time, location, and ticket settings from
  the task; the copy is written by the marketing agent, not you.
- After publishing, open the public listing page and record its URL — a listing without
  its URL doesn't count as published.
- For updates, edit the existing listing rather than creating a second one.
- Report each platform separately; one platform being blocked must not stop the others.

Publishing a free listing is expected work; anything involving paid promotion or ticket
fees follows the approval rules below."""

# Per-platform posting procedures, loaded on demand when the agent lands on that site.
_LUMA_SKILL = {
    "name": "luma-event-posting",
    "description": "Use when publishing or updating an event on Luma (lu.ma).",
    "body": (
        "1. Confirm you are signed in (avatar in the top bar); if signed out, stop and report blocked.\n"
        "2. Use the Create Event button; fill name, date and time with timezone, location, and description.\n"
        "3. Add the cover image only if the task supplies one.\n"
        "4. Set registration type and capacity to match the task; leave payment settings untouched for free events.\n"
        "5. Publish, open the public event page, and copy its URL as evidence."
    ),
    "url_pattern": "lu.ma",
}

_PARTIFUL_SKILL = {
    "name": "partiful-event-posting",
    "description": "Use when publishing or updating an event on Partiful (partiful.com).",
    "body": (
        "1. Confirm you are signed in; if signed out, stop and report blocked.\n"
        "2. Create the event; set title, date/time, location, and description from the task.\n"
        "3. Pick a plain theme unless the task names one; skip RSVP extras the task doesn't mention.\n"
        "4. Publish and copy the shareable event link as evidence."
    ),
    "url_pattern": "partiful.com",
}

_EVENTBRITE_SKILL = {
    "name": "eventbrite-event-posting",
    "description": "Use when publishing or updating an event on Eventbrite (eventbrite.com).",
    "body": (
        "1. Confirm you are signed in; if signed out, stop and report blocked.\n"
        "2. Create the event; complete every required builder step: basics, date/time, location, details.\n"
        "3. Configure tickets exactly as the task states; free tickets unless it says otherwise.\n"
        "4. Skip paid promotion upsells entirely.\n"
        "5. Publish, open the live listing, and copy its URL as evidence."
    ),
    "url_pattern": "eventbrite.com",
}

_MEETUP_SKILL = {
    "name": "meetup-event-posting",
    "description": "Use when publishing or updating an event on Meetup (meetup.com).",
    "body": (
        "1. Confirm you are signed in and the task's group exists; without a group to post into, stop and report blocked.\n"
        "2. Create the event in that group; set title, date/time, location, and description from the task.\n"
        "3. Set attendee limit if the task gives a capacity.\n"
        "4. Publish and copy the event page URL as evidence."
    ),
    "url_pattern": "meetup.com",
}


class DistributionAgent(BaseAgent):
    """Distribution agent — publishes the event across distribution channels."""

    name = "distribution"
    description = "Publishes and updates event listings on Luma, Partiful, Eventbrite, and Meetup."
    model = MODEL_FAST
    instructions = INSTRUCTIONS
    # Procedural form-filling: platform know-how lives in the skills, not model depth.
    start_url = "https://lu.ma"
    max_time_s = 1200
    max_steps = 50
    answer_schema = DistributionReport
    skills = [_LUMA_SKILL, _PARTIFUL_SKILL, _EVENTBRITE_SKILL, _MEETUP_SKILL]
