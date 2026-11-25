from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from planner.config import PlannerConfig, parse_config
from planner.gcal import CalEvent
from planner.notion import StatusSchema, Task, TaskFields

KST = ZoneInfo("Asia/Seoul")

EXAMPLE = {
    "timezone": "Asia/Seoul",
    "calendars": {"fixed": "fixed@cal", "plan": "plan@cal", "project": "project@cal", "deadline": "deadline@cal"},
    "notion": {"tasks": "ds-tasks", "projects": "ds-projects", "milestones": "ds-milestones", "jobs": "ds-jobs"},
    "day": {"start": "08:30", "end": "01:00"},
    "blocked": [{"name": "점심", "time": "12:00-13:00"}, {"name": "저녁", "time": "18:30-19:30"}],
    "focus_hours": ["09:30-12:00", "20:00-23:00"],
    "block": {"min": "30m", "max": "120m", "buffer": "15m"},
    "slack_ratio": 0.2,
    "routines": [
        {"name": "Java 공부", "duration": "60m", "frequency": "daily", "prefer": "evening"},
        {"name": "운동", "duration": "90m", "frequency": "3/week"},
    ],
    "auto_apply": {"max_changed_blocks": 2, "same_day_only": True},
}


def kst(*args: int) -> datetime:
    return datetime(*args, tzinfo=KST)


@pytest.fixture
def cfg() -> PlannerConfig:
    return parse_config(EXAMPLE)


def timed(title: str, start: datetime, end: datetime, calendar: str = "fixed", **kw) -> CalEvent:
    return CalEvent(id=f"ev-{title}", calendar=calendar, title=title, start=start, end=end,
                    all_day_start=None, all_day_end=None, transparent=kw.get("transparent", False),
                    private=kw.get("private", {}))


def all_day(title: str, first, end_exclusive, calendar: str = "fixed", transparent: bool = False) -> CalEvent:
    return CalEvent(id=f"ev-{title}", calendar=calendar, title=title, start=None, end=None,
                    all_day_start=first, all_day_end=end_exclusive, transparent=transparent)


class FakeCalendar:
    def __init__(self, events: list[CalEvent]) -> None:
        self.events = events
        self.calls: list[tuple[str, datetime, datetime]] = []

    def list_events(self, calendar, time_min, time_max):
        self.calls.append((calendar, time_min, time_max))
        out = []
        for e in self.events:
            if e.calendar != calendar:
                continue
            if e.all_day:
                s = datetime.combine(e.all_day_start, datetime.min.time(), tzinfo=KST)
                t = datetime.combine(e.all_day_end, datetime.min.time(), tzinfo=KST)
            else:
                s, t = e.start, e.end
            if s < time_max and t > time_min:
                out.append(e)
        return out


SCHEMA = StatusSchema({"할 일": "to_do", "진행": "in_progress", "완료": "complete"})


class FakeTasks:
    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}
        self.writes: list[tuple[str, TaskFields]] = []

    def status_schema(self):
        return SCHEMA

    def list_tasks(self, include_done=False, limit=50):
        ts = [t for t in self.tasks.values() if include_done or t.status_group != "complete"]
        return ts[:limit]

    def get_task(self, task_id):
        return self.tasks[task_id]

    def create_task(self, fields):
        self.writes.append(("create", fields))
        t = Task(id=f"t{len(self.tasks) + 1}", title=fields.title, status="할 일", status_group="to_do",
                 priority=None, estimate_h=None, remaining_h=None, due=None)
        self.tasks[t.id] = t
        return t

    def update_task(self, task_id, fields):
        self.writes.append((task_id, fields))
        return self.tasks[task_id]
