"""Supervisor — monitors all running agents and their health.

Read-only oversight of the H sessions behind an event's agents — who is running, how
far along (steps), what the browser currently shows (frames), what failed — plus the
account's session-slot quota and a cancel passthrough. Monitoring is polling-based:
H exposes no session webhooks, so callers poll this surface. Every snapshot carries
the session's `agent_view_url`, the live-view/replay page on the H platform.

Mirrors the service's failure-as-value philosophy: every method returns an honest
report; nothing raises.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)

# Every non-terminal lifecycle state. `idle` still pins a quota slot (one-shot runs
# settle there, carrying their outcome), so hiding it would make the listing disagree
# with the quota numbers and bury runs that need attention.
_ACTIVE_STATUSES: tuple[str, ...] = ("queued", "pending", "running", "paused", "idle", "awaiting_tool_results")

# Terminal states in which a session ended without delivering.
_FAILED_STATUSES: frozenset[str] = frozenset({"failed", "timed_out", "interrupted"})

# Every terminal state. Listed alongside the active ones so finished sessions keep a
# card — H's live view is blank mid-run, so the replay link is the one page that shows
# what a browser actually did.
_TERMINAL_STATUSES: tuple[str, ...] = ("completed", "failed", "timed_out", "interrupted")

# Finished sessions worth keeping in the listing; older history would crowd out live work.
_RECENT_TERMINAL_LIMIT = 5

_KEY_MISSING = "HAI_API_KEY is not configured; set it in services/agent/.env"

_PAGE_SIZE = 50  # headroom above any slot limit (3 free / 10 developer) plus queue and history

# ~2-4 events per agent step (policy, tool result, observation), so the newest 20
# span several steps — an observation is present once the agent has acted at all.
_FRAME_EVENT_PAGE_SIZE = 20

_FRAME_FETCH_TIMEOUT_S = 10.0

# Just under the grid's 4s tile poll, so a lone viewer never hits a stale entry twice
# in a row, while a second tab (or StrictMode's double mount) still reuses the fetch.
_FRAME_TTL_S = 3.5

# --- Obstacle detection -----------------------------------------------------------
# The messy-web obstacles a session clears (cookie walls, popups, endless lists) are
# read out of the same event page the frame poll already fetches: the agent narrates
# what it is doing in policy events, so keyword pairs (a noun AND a verb must both
# hit) classify each event without extra H calls. Purely heuristic and read-only —
# a missed obstacle costs a feed line, never correctness.

# An episode of this kind must show real scrolling before it earns a feed line;
# one incidental scroll is navigation, not draining an infinite list.
_SCROLL_MIN_ACTIONS = 3

# Ledger entries for sessions nobody polled in this long are stale demo state.
_OBSTACLE_TTL_S = 3600.0

_COOKIE_NOUNS = ("cookie", "consent", "gdpr")
_COOKIE_VERBS = ("accept", "reject", "dismiss", "decline", "agree", "necessary", "close", "closing")
_POPUP_NOUNS = ("popup", "pop-up", "modal", "overlay", "newsletter", "interstitial", "dialog", "banner")
_POPUP_VERBS = ("close", "closed", "closing", "dismiss", "no thanks", "not now", "maybe later", "skip", "escape")
_SCROLL_HINTS = ("load more", "show more", "more result", "lazy", "reached the end", "no new", "bottom of")
_BLOCKER_NOUNS = (
    "captcha",
    "recaptcha",
    "two-factor",
    "2fa",
    "verification code",
    "login required",
    "sign in required",
    "sign-in required",
    "credentials",
)
_BLOCKER_CUES = ("blocked", "cannot", "can't", "unable", "stop", "report", "requires", "required")

# "24 results", "18 venues" — the agent stating how much the scroll surfaced.
_RESULT_COUNT_RE = re.compile(r"(\d+)\s+(?:results|items|listings|options|venues|vendors|candidates)")


class SessionSnapshot(BaseModel):
    """One live session as the dashboard needs it: who, what, and where to watch."""

    id: str
    agent: str | None = None
    status: str
    task: str | None = None  # the session's opening user message, verbatim
    agent_view_url: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class QuotaSnapshot(BaseModel):
    """The account's concurrent-session slots."""

    limit: int
    active: int
    available: int


class ObstacleLine(BaseModel):
    """One web obstacle a session cleared — a rail-strip line."""

    session_id: str
    agent: str | None = None  # H agent name ("occasion-venue"); stamped by event_sessions
    kind: str  # "cookie" | "popup" | "scroll" | "recovery"
    label: str  # e.g. "dismissed cookie wall on eventbrite.com"
    at: datetime | None = None  # timestamp of the event that evidenced the clear


class ObstaclesSummary(BaseModel):
    """Event-wide tally of cleared obstacles (module ledger; resets with the process)."""

    cleared_total: int = 0
    lines: list[ObstacleLine] = []  # newest first, capped


class EventSessionsReport(BaseModel):
    """An event's live sessions plus quota; `succeeded` means the whole report is trustworthy."""

    succeeded: bool
    event_id: str
    sessions: list[SessionSnapshot] = []
    quota: QuotaSnapshot | None = None
    obstacles: ObstaclesSummary | None = None  # absent until any session cleared one
    error: str | None = None


class SessionHealth(BaseModel):
    """One session's live status; `succeeded` folds "check reached H" and "session not failed"."""

    succeeded: bool
    session_id: str
    status: str  # lifecycle state, or "error" when the check itself failed
    outcome: str | None = None
    steps: int | None = None
    error: str | None = None
    subagent_session_ids: list[str] = []


class SessionFrame(BaseModel):
    """The newest browser screenshot of one session — a single live-grid tile."""

    succeeded: bool
    session_id: str
    at: datetime | None = None  # when the observation was taken
    page_title: str | None = None
    page_url: str | None = None
    media_type: str | None = None  # e.g. "image/png"
    image_base64: str | None = None  # absent while the session has no screenshot yet
    handling: str | None = None  # obstacle underway now, e.g. "cookie wall" | "recovering"
    obstacles_cleared: list[str] = []  # this session's cleared labels, oldest first
    error: str | None = None


# Keyed by session id, valued (monotonic fetch time, frame). Module scope because a
# Supervisor is built per request; a lost check-then-set race costs one extra fetch.
_frame_cache: dict[str, tuple[float, SessionFrame]] = {}


class _ObstacleLog:
    """One session's obstacle state across frame polls (module scope, like _frame_cache).

    `watermark` marks how far into the event stream detection has resolved: closed
    episodes and unrelated events sit behind it, an episode still underway stays ahead
    of it so the next poll can finish classifying it.
    """

    __slots__ = (
        "watermark",
        "agent",
        "cleared",
        "cleared_count",
        "pending_feed",
        "seen_feed_kinds",
        "handling",
        "touched",
    )

    def __init__(self) -> None:
        self.watermark: datetime | None = None
        self.agent: str | None = None
        self.cleared: list[ObstacleLine] = []  # oldest first, capped for display
        self.cleared_count: int = 0  # true tally; unlike `cleared`, never truncated
        self.pending_feed: list[ObstacleLine] = []  # drained by the frame route
        self.seen_feed_kinds: set[str] = set()  # one activity line per kind per session
        self.handling: str | None = None
        self.touched: float = time.monotonic()


# Obstacles cleared per session id. Module scope for the same reason as _frame_cache;
# process-lived on purpose — the durable trace is the activity feed, not this ledger.
_obstacle_ledger: dict[str, _ObstacleLog] = {}

# Newest cleared lines worth showing in the rail strip.
_OBSTACLE_SUMMARY_LIMIT = 6

# Per-session cleared history; older lines age out, the tally lives in the feed.
_OBSTACLE_HISTORY_LIMIT = 12


class CancelResult(BaseModel):
    succeeded: bool
    session_id: str
    error: str | None = None


class Supervisor:
    """Watches the fleet's H sessions for one deployment of the service.

    `sdk_client` is a hai_agents.Client, or any object exposing `sessions`; tests
    inject fakes through the same seam HClient uses.
    """

    def __init__(self, sdk_client: object, http_client: httpx.Client | None = None) -> None:
        self._sdk = sdk_client
        self._http = http_client  # injection seam for tests; None opens one per screenshot fetch

    @classmethod
    def from_settings(cls) -> "Supervisor":
        """Build a client for the session (AGP) host, mirroring HClient.from_settings."""
        from hai_agents import Client

        kwargs: dict[str, str] = {"api_key": settings.hai_api_key}
        if settings.hai_session_base_url:
            kwargs["base_url"] = settings.hai_session_base_url
        return cls(Client(**kwargs))

    def event_sessions(self, event_id: str) -> EventSessionsReport:
        """This event's active sessions plus its most recent finished ones, and quota.

        Partial failures keep whatever was fetched: `succeeded` is True only when both
        H calls worked, and `error` names the one that did not.
        """
        if not settings.hai_api_key:
            return EventSessionsReport(succeeded=False, event_id=event_id, error=_KEY_MISSING)
        sessions: list[SessionSnapshot] = []
        quota: QuotaSnapshot | None = None
        errors: list[str] = []
        try:
            page = self._sdk.sessions.list_sessions(
                group_id=event_id,
                status=list(_ACTIVE_STATUSES) + list(_TERMINAL_STATUSES),
                size=_PAGE_SIZE,
                sort=["-created_at"],
            )
            sessions = _with_recent_history([_snapshot(item) for item in page.items or []])
        except Exception as exc:
            errors.append(f"session listing failed: {_error_message(exc)}")
        try:
            status = self._sdk.sessions.get_session_quota()
            quota = QuotaSnapshot(limit=status.limit, active=status.active, available=status.available)
        except Exception as exc:
            errors.append(f"quota check failed: {_error_message(exc)}")
        if errors:
            logger.warning("event %s: %s", event_id, "; ".join(errors))
        return EventSessionsReport(
            succeeded=not errors,
            event_id=event_id,
            sessions=sessions,
            quota=quota,
            obstacles=_obstacle_summary(sessions),
            error="; ".join(errors) or None,
        )

    def session_health(self, session_id: str) -> SessionHealth:
        """One session's live status: lifecycle state, progress (steps), and errors."""
        if not settings.hai_api_key:
            return SessionHealth(succeeded=False, session_id=session_id, status="error", error=_KEY_MISSING)
        try:
            status = self._sdk.sessions.get_session_status(session_id)
        except Exception as exc:
            logger.warning("session %s: health check failed: %s", session_id, _error_message(exc))
            return SessionHealth(succeeded=False, session_id=session_id, status="error", error=_error_message(exc))
        lifecycle = _unwrap_str(status.status) or "unknown"
        return SessionHealth(
            succeeded=lifecycle not in _FAILED_STATUSES,
            session_id=session_id,
            status=lifecycle,
            outcome=_unwrap_str(getattr(status, "outcome", None)),
            steps=getattr(status, "steps", None),
            error=_error_text(getattr(status, "error", None), getattr(status, "error_code", None)),
            subagent_session_ids=list(getattr(status, "subagent_session_ids", None) or []),
        )

    def session_frame(self, session_id: str) -> SessionFrame:
        """The newest browser screenshot from a session's event stream — one live-grid tile.

        Stateless per call: the newest events page is fetched fresh (the same surface
        H's own Agent View polls), behind a short shared cache so concurrent viewers
        of one session don't multiply H calls.
        """
        if not settings.hai_api_key:
            return SessionFrame(succeeded=False, session_id=session_id, error=_KEY_MISSING)
        cached = _cached_frame(session_id)
        if cached is not None:
            return cached
        try:
            page = self._sdk.sessions.list_session_events(
                session_id, size=_FRAME_EVENT_PAGE_SIZE, sort=["-timestamp"], type="AgentEvent"
            )
        except Exception as exc:
            logger.warning("session %s: frame fetch failed: %s", session_id, _error_message(exc))
            return _remember(
                SessionFrame(
                    succeeded=False, session_id=session_id, error=f"frame fetch failed: {_error_message(exc)}"
                )
            )
        items = list(getattr(page, "items", None) or [])
        # Same fetch, second read: mine the events for obstacle handling before picking
        # the screenshot, so tiles can caption what the agent is working through.
        # Detection is best-effort; a heuristic failure must never cost the tile its frame.
        try:
            log = _observe_window(session_id, items)
            handling, cleared = log.handling, [line.label for line in log.cleared]
        except Exception:
            logger.exception("session %s: obstacle detection failed", session_id)
            handling, cleared = None, []
        event = _latest_observation(items)
        if event is None:
            # Queued/pending sessions (or a page of pure policy/tool events) have no
            # screenshot yet; an honest empty frame lets the tile keep its placeholder.
            return _remember(
                SessionFrame(succeeded=True, session_id=session_id, handling=handling, obstacles_cleared=cleared)
            )
        return _remember(self._frame_from(session_id, event, handling=handling, obstacles_cleared=cleared))

    def drain_obstacle_feed(self, session_id: str) -> list[ObstacleLine]:
        """Cleared obstacles not yet written to the activity feed; empties on read.

        Drain-once keeps the feed write idempotent across concurrent viewers: whoever
        polls the frame first carries the lines to the feed, everyone else gets [].
        """
        log = _obstacle_ledger.get(session_id)
        if log is None:
            return []
        pending, log.pending_feed = log.pending_feed, []
        return pending

    def _frame_from(
        self,
        session_id: str,
        event: object,
        *,
        handling: str | None = None,
        obstacles_cleared: list[str] | None = None,
    ) -> SessionFrame:
        data = getattr(event, "data", None)
        image_base64, media_type, error = self._image_payload(getattr(data, "image", None))
        metadata = getattr(data, "metadata", None) or {}
        return SessionFrame(
            succeeded=error is None,
            session_id=session_id,
            at=getattr(event, "timestamp", None),
            page_title=_unwrap_str(metadata.get("title")),
            page_url=_unwrap_str(metadata.get("url")),
            media_type=media_type,
            image_base64=image_base64,
            handling=handling,
            obstacles_cleared=obstacles_cleared or [],
            error=error,
        )

    def _image_payload(self, image: object) -> tuple[str | None, str | None, str | None]:
        """(image_base64, media_type, error). Inline base64 passes straight through; url
        images live on the AGP host behind the API key (404 unauthenticated), so the
        bytes are fetched here — the browser could never load them directly.
        """
        media_type = _unwrap_str(getattr(image, "media_type", None)) or "image/png"
        kind = _unwrap_str(getattr(image, "type", None))
        source = getattr(image, "source", None) or ""
        if kind == "base64":
            return source, media_type, None
        if kind != "url":
            return None, None, f"unsupported image type: {kind or 'unknown'}"
        headers = {"Authorization": f"Bearer {settings.hai_api_key}"}
        # AGP 302s to a presigned S3 URL; httpx drops Authorization on that cross-origin
        # hop, which S3 requires (query auth plus an auth header is rejected).
        try:
            if self._http is not None:
                response = self._http.get(source, headers=headers, follow_redirects=True)
            else:
                with httpx.Client(timeout=_FRAME_FETCH_TIMEOUT_S) as client:
                    response = client.get(source, headers=headers, follow_redirects=True)
            response.raise_for_status()
        except Exception as exc:
            return None, None, f"screenshot fetch failed: {_error_message(exc)}"
        return base64.b64encode(response.content).decode("ascii"), media_type, None

    def cancel_session(self, session_id: str) -> CancelResult:
        """Stop a runaway or unwanted session (H's DELETE /sessions/{id})."""
        if not settings.hai_api_key:
            return CancelResult(succeeded=False, session_id=session_id, error=_KEY_MISSING)
        try:
            self._sdk.sessions.cancel_session(session_id)
        except Exception as exc:
            logger.warning("session %s: cancel failed: %s", session_id, _error_message(exc))
            return CancelResult(succeeded=False, session_id=session_id, error=_error_message(exc))
        return CancelResult(succeeded=True, session_id=session_id)


def _snapshot(summary: object) -> SessionSnapshot:
    first = getattr(summary, "first_message", None)
    return SessionSnapshot(
        id=str(getattr(summary, "id", "")),
        agent=getattr(summary, "agent", None),
        status=_unwrap_str(getattr(summary, "status", None)) or "unknown",
        task=getattr(first, "message", None),
        agent_view_url=getattr(summary, "agent_view_url", None),
        created_at=getattr(summary, "created_at", None),
        started_at=getattr(summary, "started_at", None),
        finished_at=getattr(summary, "finished_at", None),
    )


def _with_recent_history(snapshots: list[SessionSnapshot]) -> list[SessionSnapshot]:
    """Every active session plus the newest few finished ones, order preserved.

    The input is newest-first, so keeping the first _RECENT_TERMINAL_LIMIT terminal
    snapshots keeps the most recent history without reordering anything.
    """
    kept: list[SessionSnapshot] = []
    finished = 0
    for snapshot in snapshots:
        if snapshot.status in _TERMINAL_STATUSES:
            if finished == _RECENT_TERMINAL_LIMIT:
                continue
            finished += 1
        kept.append(snapshot)
    return kept


def _latest_observation(items: list) -> object | None:
    # Items arrive newest-first; the first observation carrying an image is the frame.
    for item in items:
        data = getattr(item, "data", None)
        if getattr(data, "kind", None) == "observation_event" and getattr(data, "image", None) is not None:
            return item
    return None


def _observe_window(session_id: str, items: list) -> _ObstacleLog:
    """Advance the session's obstacle ledger over a freshly fetched event window.

    Walks the events newer than the watermark oldest-first, grouping consecutive
    same-kind matches into an episode. An episode closes — one cleared line — when
    the agent moves on to differently-classified work; an episode still open at the
    newest edge becomes the session's `handling` and is re-examined next poll.
    """
    _prune_ledger()
    log = _obstacle_ledger.setdefault(session_id, _ObstacleLog())
    log.touched = time.monotonic()
    host = _newest_page_host(items)
    watermark = log.watermark
    current_kind: str | None = None
    episode: list = []
    for event in reversed(items):  # oldest first
        stamp = getattr(event, "timestamp", None)
        if stamp is None or (log.watermark is not None and stamp <= log.watermark):
            continue
        data = getattr(event, "data", None)
        kind = _classify(data)
        if kind is not None and kind == current_kind:
            episode.append(event)
            continue
        if kind is None and not _is_agent_action(data):
            # Observations and chatter are the flow between decisions: they neither
            # extend nor close an episode.
            if current_kind is None:
                watermark = stamp
            continue
        # The agent changed activity: whatever was underway is finished.
        if current_kind is not None:
            _record_cleared(log, session_id, current_kind, episode, host)
            watermark = episode[-1].timestamp
        if kind is None:  # unrelated agent work; resolved for good
            current_kind, episode = None, []
            watermark = stamp
        else:  # a new obstacle episode starts here
            current_kind, episode = kind, [event]
    log.handling = _handling_label(current_kind, episode) if current_kind is not None else None
    log.watermark = watermark
    return log


def _record_cleared(log: _ObstacleLog, session_id: str, kind: str, episode: list, host: str | None) -> None:
    label = _cleared_label(kind, episode, host)
    if label is None:  # blockers stay blockers; a stray scroll is not a drained list
        return
    line = ObstacleLine(
        session_id=session_id,
        agent=log.agent,
        kind=kind,
        label=label,
        at=getattr(episode[-1], "timestamp", None),
    )
    log.cleared.append(line)
    del log.cleared[: -_OBSTACLE_HISTORY_LIMIT]  # keep the newest few
    log.cleared_count += 1
    if kind not in log.seen_feed_kinds:
        # One activity line per kind per session, so a consent-heavy run cannot
        # drown bookings and approvals out of the feed.
        log.seen_feed_kinds.add(kind)
        log.pending_feed.append(line)


def _classify(data: object) -> str | None:
    """The obstacle kind this event evidences, or None for anything else."""
    kind = getattr(data, "kind", None)
    if kind == "error_event":
        return "recovery"  # H retries and replans after errors; surviving one is worth showing
    if kind == "tool_result":
        return "scroll" if _scroll_actions(data) else None
    if kind != "policy_event":
        return None
    text = _event_text(data)
    if any(noun in text for noun in _BLOCKER_NOUNS) and any(cue in text for cue in _BLOCKER_CUES):
        return "blocker"
    if any(noun in text for noun in _COOKIE_NOUNS) and any(verb in text for verb in _COOKIE_VERBS):
        return "cookie"
    if any(noun in text for noun in _POPUP_NOUNS) and any(verb in text for verb in _POPUP_VERBS):
        return "popup"
    if ("scroll" in text and any(hint in text for hint in _SCROLL_HINTS)) or _scroll_actions(data):
        return "scroll"
    return None


def _is_agent_action(data: object) -> bool:
    # Policy decisions, tool calls, and the final answer are the agent changing
    # activity; anything else (observations, chat, flow control) is just the flow.
    return getattr(data, "kind", None) in ("policy_event", "tool_result", "answer_event")


def _event_text(data: object) -> str:
    """Lowercased narration of one event: what the agent said plus what it did."""
    parts: list[str] = []
    for field in ("content", "reasoning_content"):
        value = getattr(data, field, None)
        if isinstance(value, str) and value:
            parts.append(value)
    for req in _tool_requests(data):
        name = getattr(req, "tool_name", None)
        if isinstance(name, str):
            parts.append(name)
        args = getattr(req, "args", None)
        if args:
            parts.append(str(args))
    return " ".join(parts).lower()


def _tool_requests(data: object) -> list:
    # policy_event carries tool_reqs (a list); tool_result carries a single tool_req.
    requests = list(getattr(data, "tool_reqs", None) or [])
    single = getattr(data, "tool_req", None)
    if single is not None:
        requests.append(single)
    return requests


def _scroll_actions(data: object) -> int:
    return sum(1 for req in _tool_requests(data) if "scroll" in str(getattr(req, "tool_name", "")).lower())


def _handling_label(kind: str, episode: list) -> str:
    if kind == "cookie":
        return "cookie wall"
    if kind == "popup":
        return "popup"
    if kind == "scroll":
        return "scrolling results"
    if kind == "recovery":
        return "recovering"
    # blocker: name the specific check, so the pill says what a human must solve
    text = " ".join(_event_text(getattr(event, "data", None)) for event in episode)
    if "captcha" in text:
        return "blocked: CAPTCHA"
    if "two-factor" in text or "2fa" in text or "verification code" in text:
        return "blocked: 2FA"
    return "blocked: login"


def _cleared_label(kind: str, episode: list, host: str | None) -> str | None:
    if kind == "cookie":
        return f"dismissed cookie wall on {host}" if host else "dismissed cookie wall"
    if kind == "popup":
        return f"closed popup on {host}" if host else "closed popup"
    if kind == "recovery":
        return "recovered after error"
    if kind == "scroll":
        return _scroll_label(episode)
    return None  # blocker — never a ✓ line; the run's own finish line is the handoff


def _scroll_label(episode: list) -> str | None:
    """An honest scroll summary: the agent's own count, or the actions taken."""
    stated: str | None = None
    actions = 0
    hinted = False
    for event in episode:
        data = getattr(event, "data", None)
        text = _event_text(data)
        for match in _RESULT_COUNT_RE.finditer(text):
            stated = match.group(1)  # keep the newest count the agent stated
        if "scroll" in text and any(hint in text for hint in _SCROLL_HINTS):
            hinted = True
        actions += _scroll_actions(data)
    if stated is not None:
        return f"scrolled {stated} results"
    if actions >= _SCROLL_MIN_ACTIONS:
        return f"scrolled ×{actions} to load more"
    if hinted:
        return "scrolled to load more results"
    return None  # too little evidence to call it a drained list


def _newest_page_host(items: list) -> str | None:
    # Items arrive newest-first; the first observation naming a URL places the episode.
    for item in items:
        data = getattr(item, "data", None)
        if getattr(data, "kind", None) != "observation_event":
            continue
        metadata = getattr(data, "metadata", None) or {}
        url = _unwrap_str(metadata.get("url"))
        if url:
            host = urlparse(url).netloc.removeprefix("www.")
            return host or None
    return None


def _obstacle_summary(sessions: list[SessionSnapshot]) -> ObstaclesSummary | None:
    """The rail's tally for these sessions; stamps agent names into the ledger on the way.

    Frames (where detection runs) never learn the agent's name — the session listing
    does, so this is the one place lines minted as anonymous pick their name up.
    """
    lines: list[ObstacleLine] = []
    total = 0
    for snapshot in sessions:
        log = _obstacle_ledger.get(snapshot.id)
        if log is None:
            continue
        if snapshot.agent and log.agent != snapshot.agent:
            log.agent = snapshot.agent
            for line in log.cleared + log.pending_feed:
                line.agent = snapshot.agent
        total += log.cleared_count
        lines.extend(log.cleared)
    if total == 0:
        return None
    # Newest first; lines without a timestamp sort last. The tuple key keeps naive
    # datetime.min from ever being compared against H's timezone-aware timestamps.
    lines.sort(key=lambda line: (line.at is not None, line.at or datetime.min), reverse=True)
    return ObstaclesSummary(cleared_total=total, lines=lines[:_OBSTACLE_SUMMARY_LIMIT])


def _prune_ledger() -> None:
    now = time.monotonic()
    stale = [key for key, log in _obstacle_ledger.items() if now - log.touched >= _OBSTACLE_TTL_S]
    for key in stale:
        del _obstacle_ledger[key]


def _cached_frame(session_id: str) -> SessionFrame | None:
    now = time.monotonic()
    expired = [key for key, (fetched_at, _) in _frame_cache.items() if now - fetched_at >= _FRAME_TTL_S]
    for key in expired:  # prune so the cache stays bounded by actively watched sessions
        del _frame_cache[key]
    entry = _frame_cache.get(session_id)
    return entry[1] if entry is not None else None


def _remember(frame: SessionFrame) -> SessionFrame:
    _frame_cache[frame.session_id] = (time.monotonic(), frame)
    return frame


def _error_message(exc: Exception) -> str:
    # Mirrors client._result_from_error: keep the HTTP status visible when present.
    message = str(exc).strip() or exc.__class__.__name__
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return f"HTTP {status_code}: {message}"
    return message


def _error_text(error: object, error_code: object) -> str | None:
    # Mirrors client._error_text: one string carrying both the message and the code.
    message = _unwrap_str(error)
    code = _unwrap_str(error_code)
    if message and code:
        return f"{message} ({code})"
    return message or code


def _unwrap_str(value: object) -> str | None:
    # Enums expose their wire value at `.value`; plain strings pass straight through.
    value = getattr(value, "value", value)
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)
