"""Planner MCP server (stdio).

Environment:
  PLANNER_CONFIG     path to planner.yaml (default /opt/data/planner/planner.yaml)
  NOTION_TOKEN       Notion integration token connected to the "비서" page
  GOOGLE_TOKEN_FILE  path to the Google OAuth token JSON (default /opt/data/planner/google_token.json)

Run: uv run --frozen python -m planner.server
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, TypeVar

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .config import ConfigError, load_config
from .gcal import CalendarError, GoogleCalendar, TokenSource
from .notion import _UNSET, NotionError, NotionTasks
from .service import Planner

INSTRUCTIONS = """\
Planner for the user's schedule. Tasks live in Notion; time lives in Google Calendar.
- All time arithmetic (free time, day windows, durations) is done by these tools. Report
  their numbers as given; do not compute or adjust times yourself.
- A "day" runs from the configured start to end and may pass midnight (e.g. 08:30-01:00).
- Writes the user asked for directly ("ERD 끝", "add X due Friday") need no extra confirmation.
  If you had to estimate a duration yourself, ask the user to confirm it before saving.
"""

server = MCPServer("planner", instructions=INSTRUCTIONS)

_planner: Planner | None = None
T = TypeVar("T")


class _LazyCalendar:
    """Builds the Google client on first use, so Notion tools work before the Google login."""

    def __init__(self, factory: Callable[[], GoogleCalendar]) -> None:
        self._factory = factory
        self._client: GoogleCalendar | None = None

    def list_events(self, calendar: str, time_min: datetime, time_max: datetime):
        if self._client is None:
            self._client = self._factory()
        return self._client.list_events(calendar, time_min, time_max)


def _build() -> Planner:
    cfg = load_config(os.environ.get("PLANNER_CONFIG", "/opt/data/planner/planner.yaml"))
    http = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
    tasks = NotionTasks(os.environ.get("NOTION_TOKEN", ""), cfg.notion.tasks, http, cfg.timezone)

    def google() -> GoogleCalendar:
        tokens = TokenSource(os.environ.get("GOOGLE_TOKEN_FILE", "/opt/data/planner/google_token.json"), http)
        return GoogleCalendar(dict(cfg.calendars.items()), tokens, http, cfg.timezone)

    return Planner(cfg, tasks, _LazyCalendar(google), clock=lambda: datetime.now(cfg.timezone))


def _run(fn: Callable[[Planner], T]) -> T:
    """Build the planner on first use and turn expected failures into tool errors."""
    global _planner
    try:
        if _planner is None:
            _planner = _build()
        return fn(_planner)
    except (ConfigError, NotionError, CalendarError, ValueError) as e:
        raise ToolError(str(e)) from e
    except httpx.HTTPError as e:
        raise ToolError(f"network error talking to Notion/Google: {e.__class__.__name__}") from e


Priority = Literal["P1", "P2", "P3"]
Clearable = Literal["priority", "estimate_h", "remaining_h", "due"]


@server.tool()
def list_tasks(include_done: bool = False, limit: int = 50) -> dict[str, Any]:
    """List tasks from Notion, open ones (to-do / in progress) by default, sorted by due date.

    Each task has id, title, status, priority, estimate_h, remaining_h, needed_h
    (remaining if set, else estimate) and due (ISO date or datetime).
    """
    return _run(lambda p: p.list_tasks(include_done=include_done, limit=limit))


@server.tool()
def add_task(title: str, estimate_h: float | None = None, due: str | None = None, priority: Priority | None = None) -> dict[str, Any]:
    """Add a task to Notion with status to-do.

    due: "YYYY-MM-DD" for a date, or "YYYY-MM-DDTHH:MM" for a time (local time).
    estimate_h: hours. Leave it out if the user gave none; if you propose an
    estimate, confirm it with the user and set it with update_task.
    """
    return _run(lambda p: p.add_task(title, estimate_h, due, priority))


@server.tool()
def update_task(
    task_id: str,
    title: str | None = None,
    status: str | None = None,
    priority: Priority | None = None,
    estimate_h: float | None = None,
    remaining_h: float | None = None,
    due: str | None = None,
    clear: list[Clearable] | None = None,
) -> dict[str, Any]:
    """Change fields of a task. Omitted fields keep their value.

    status must be one of the Tasks status options (e.g. 할 일, 진행, 완료).
    remaining_h: hours left after partial progress ("절반 했어" -> half of needed_h).
    clear: field names to empty, e.g. ["due"].
    """
    changes: dict[str, Any] = {
        "title": title if title is not None else _UNSET,
        "status": status if status is not None else _UNSET,
        "priority": priority if priority is not None else _UNSET,
        "estimate_h": estimate_h if estimate_h is not None else _UNSET,
        "remaining_h": remaining_h if remaining_h is not None else _UNSET,
        "due": due if due is not None else _UNSET,
    }
    for name in clear or []:
        changes[name] = None
    return _run(lambda p: p.update_task(task_id, **changes))


@server.tool()
def complete_task(task_id: str) -> dict[str, Any]:
    """Mark a task done (first option of the complete group) and set remaining_h to 0."""
    return _run(lambda p: p.complete_task(task_id))


@server.tool()
def get_day(date: str = "today") -> dict[str, Any]:
    """Timeline of one day: fixed events, planned blocks, deadlines, blocked times (meals) and free slots.

    date: "YYYY-MM-DD", "today" or "tomorrow". The day window may end after
    midnight; items are ISO datetimes with offset, sorted by start.
    """
    return _run(lambda p: p.get_day(date))


@server.tool()
def find_free_slots(start: str = "today", end: str | None = None, include_planned: bool = False) -> dict[str, Any]:
    """Free time per day between start and end (inclusive, at most 14 days).

    Free time = day window minus meals/blocked rules minus fixed events (with the
    buffer around each), only from now on for today, keeping slots of at least
    the minimum block size. plannable_minutes keeps the slack reserve aside.
    include_planned: also treat already planned blocks as busy.
    """
    return _run(lambda p: p.find_free_slots(start, end, include_planned))


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
