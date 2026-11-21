"""Planner operations behind the MCP tools.

Everything here takes its collaborators (task store, calendar client, clock)
as arguments so tests can run against fakes without touching real accounts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from .config import PlannerConfig
from .days import DayFree, Interval, blocked_intervals, day_window, free_on_day, logical_day_of
from .gcal import CalendarClient, CalEvent
from .notion import _UNSET, Task, TaskFields, TaskStore

MAX_RANGE_DAYS = 14
WEEKDAYS_KO = "월화수목금토일"


def parse_day(value: str, today: date) -> date:
    v = value.strip().lower()
    if v in ("today", "오늘"):
        return today
    if v in ("tomorrow", "내일"):
        return today + timedelta(days=1)
    try:
        return date.fromisoformat(v)
    except ValueError as e:
        raise ValueError(f"date must be YYYY-MM-DD, 'today' or 'tomorrow', got {value!r}") from e


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def _slot(iv: Interval) -> dict[str, Any]:
    return {"start": _iso(iv.start), "end": _iso(iv.end), "minutes": iv.minutes}


def all_day_dates(ev: CalEvent) -> tuple[date, date]:
    """First and last date (inclusive) of an all-day event."""
    assert ev.all_day_start and ev.all_day_end
    last = ev.all_day_end - timedelta(days=1) if ev.all_day_end > ev.all_day_start else ev.all_day_start
    return ev.all_day_start, last


def busy_intervals(events: list[CalEvent], cfg: PlannerConfig) -> list[Interval]:
    """Intervals that make time unavailable.

    Transparent ("show as available") events never block. An opaque all-day
    event blocks the whole logical day of each of its dates, including the part
    after midnight (e.g. 00:00-01:00 of an 08:30-01:00 day).
    """
    out = []
    for ev in events:
        if ev.transparent:
            continue
        if ev.all_day:
            first, last = all_day_dates(ev)
            out.append(Interval(day_window(first, cfg).start, day_window(last, cfg).end))
        elif ev.start and ev.end and ev.end > ev.start:
            out.append(Interval(ev.start, ev.end))
    return out


@dataclass
class Planner:
    cfg: PlannerConfig
    tasks: TaskStore
    calendar: CalendarClient
    clock: Callable[[], datetime]

    # ----- time -----

    def now(self) -> datetime:
        return self.clock().astimezone(self.cfg.timezone)

    def today(self) -> date:
        return logical_day_of(self.now(), self.cfg)

    def _events(self, calendar: str, start: datetime, end: datetime) -> list[CalEvent]:
        return self.calendar.list_events(calendar, start, end)

    def _day_free(self, day: date, busy_events: list[CalEvent]) -> DayFree:
        return free_on_day(day, self.cfg, busy_intervals(busy_events, self.cfg), now=self.now())

    def find_free_slots(self, start: str, end: str | None = None, include_planned: bool = False) -> dict[str, Any]:
        first = parse_day(start, self.today())
        last = parse_day(end, self.today()) if end else first
        if last < first:
            raise ValueError("end is before start")
        if (last - first).days >= MAX_RANGE_DAYS:
            raise ValueError(f"range is limited to {MAX_RANGE_DAYS} days")

        span = Interval(day_window(first, self.cfg).start, day_window(last, self.cfg).end)
        events = self._events("fixed", span.start, span.end)
        if include_planned:
            events += self._events("plan", span.start, span.end)

        days = []
        d = first
        while d <= last:
            f = self._day_free(d, events)
            days.append({
                "date": d.isoformat(),
                "weekday": WEEKDAYS_KO[d.weekday()],
                "slots": [_slot(s) for s in f.slots],
                "free_minutes": f.free_minutes,
                "plannable_minutes": f.plannable_minutes,
            })
            d += timedelta(days=1)
        return {
            "days": days,
            "rules": {
                "day": f"{self.cfg.day.start:%H:%M}-{self.cfg.day.end:%H:%M}",
                "buffer_minutes": int(self.cfg.block.buffer.total_seconds() // 60),
                "min_slot_minutes": int(self.cfg.block.min.total_seconds() // 60),
                "slack_ratio": self.cfg.slack_ratio,
                "include_planned": include_planned,
            },
        }

    def get_day(self, day_str: str) -> dict[str, Any]:
        day = parse_day(day_str, self.today())
        window = day_window(day, self.cfg)
        fixed = self._events("fixed", window.start, window.end)
        plan = self._events("plan", window.start, window.end)
        deadlines = self._events("deadline", window.start, window.end)

        items: list[dict[str, Any]] = []
        all_day: list[dict[str, Any]] = []
        for ev in fixed + plan + deadlines:
            if ev.all_day:
                first, last = all_day_dates(ev)
                if first <= day <= last:  # the window also overlaps the next date's all-day events
                    all_day.append({"title": ev.title, "calendar": ev.calendar, "busy": not ev.transparent})
                continue
            assert ev.start and ev.end
            kind = {"fixed": "fixed", "plan": "plan", "deadline": "deadline"}[ev.calendar]
            item: dict[str, Any] = {"start": _iso(ev.start), "end": _iso(ev.end), "kind": kind, "title": ev.title, "event_id": ev.id}
            if ev.private.get("task_id"):
                item["task_id"] = ev.private["task_id"]
            if ev.private.get("kind"):
                item["block_kind"] = ev.private["kind"]
            items.append(item)
        for name, iv in blocked_intervals(day, self.cfg):
            items.append({"start": _iso(iv.start), "end": _iso(iv.end), "kind": "blocked", "title": name})
        items.sort(key=lambda i: (i["start"], i["end"]))

        free = self._day_free(day, fixed + plan)
        return {
            "date": day.isoformat(),
            "weekday": WEEKDAYS_KO[day.weekday()],
            "window": {"start": _iso(window.start), "end": _iso(window.end)},
            "all_day": all_day,
            "items": items,
            "free": [_slot(s) for s in free.slots],
            "free_minutes": free.free_minutes,
            "plannable_minutes": free.plannable_minutes,
        }

    # ----- tasks -----

    def list_tasks(self, include_done: bool = False, limit: int = 50) -> dict[str, Any]:
        tasks = self.tasks.list_tasks(include_done=include_done, limit=max(1, min(limit, 200)))
        return {"tasks": [t.to_dict() for t in tasks], "count": len(tasks)}

    def add_task(self, title: str, estimate_h: float | None, due: str | None, priority: str | None) -> dict[str, Any]:
        f = TaskFields(title=title)
        if estimate_h is not None:
            f.estimate_h = estimate_h
        if due:
            f.due = due
        if priority:
            f.priority = priority
        return self.tasks.create_task(f).to_dict()

    def update_task(self, task_id: str, **changes: Any) -> dict[str, Any]:
        f = TaskFields()
        for key, value in changes.items():
            if value is _UNSET:
                continue
            setattr(f, key, value)
        return self.tasks.update_task(task_id, f).to_dict()

    def complete_task(self, task_id: str) -> dict[str, Any]:
        schema = self.tasks.status_schema()
        t: Task = self.tasks.update_task(task_id, TaskFields(status=schema.first_in("complete"), remaining_h=0))
        return t.to_dict()
