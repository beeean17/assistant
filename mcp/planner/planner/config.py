"""planner.yaml loading and validation.

The rules file holds everything the scheduler needs that is not in Notion or
Google Calendar: the day window, blocked times, block sizes, routines and the
IDs of the calendars and Notion data sources. See
docs/homeserver-hermes-architecture.md ("플래너 규칙 파일").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


class ConfigError(ValueError):
    """planner.yaml is missing, malformed or inconsistent."""


@dataclass(frozen=True)
class ClockRange:
    """A wall-clock range such as 12:00-13:00. May cross midnight (23:00-01:00)."""

    start: time
    end: time


@dataclass(frozen=True)
class Blocked:
    name: str
    range: ClockRange


@dataclass(frozen=True)
class BlockRules:
    min: timedelta
    max: timedelta
    buffer: timedelta


@dataclass(frozen=True)
class Routine:
    name: str
    duration: timedelta
    frequency: str  # "daily" or "N/week"
    prefer: str | None = None

    @property
    def per_week(self) -> int:
        if self.frequency == "daily":
            return 7
        return int(self.frequency.split("/", 1)[0])


@dataclass(frozen=True)
class Calendars:
    fixed: str
    plan: str
    project: str
    deadline: str

    def items(self) -> list[tuple[str, str]]:
        return [("fixed", self.fixed), ("plan", self.plan), ("project", self.project), ("deadline", self.deadline)]


@dataclass(frozen=True)
class NotionSources:
    """Notion data source IDs (not database IDs)."""

    tasks: str
    projects: str
    milestones: str
    jobs: str


@dataclass(frozen=True)
class PlannerConfig:
    timezone: ZoneInfo
    calendars: Calendars
    notion: NotionSources
    day: ClockRange
    blocked: tuple[Blocked, ...]
    focus_hours: tuple[ClockRange, ...]
    block: BlockRules
    slack_ratio: float
    routines: tuple[Routine, ...]
    extra: dict[str, Any] = field(default_factory=dict)  # auto_apply, project, ... (later stages)


_DURATION_RE = re.compile(r"^(?:(\d+)h)?\s*(?:(\d+)m)?$")
_CLOCK_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_FREQ_RE = re.compile(r"^(daily|[1-7]/week)$")


def parse_duration(value: Any, what: str = "duration") -> timedelta:
    """Parse "30m", "2h", "1h30m" or a number of minutes."""
    if isinstance(value, bool):
        raise ConfigError(f"{what}: expected a duration like 30m, got {value!r}")
    if isinstance(value, int):
        minutes = value
    else:
        m = _DURATION_RE.match(str(value).strip())
        if not m or not any(m.groups()):
            raise ConfigError(f"{what}: expected a duration like 30m or 1h30m, got {value!r}")
        minutes = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    if minutes <= 0:
        raise ConfigError(f"{what}: must be positive, got {value!r}")
    return timedelta(minutes=minutes)


def parse_clock(value: Any, what: str = "time") -> time:
    m = _CLOCK_RE.match(str(value).strip())
    if not m:
        raise ConfigError(f"{what}: expected HH:MM, got {value!r}")
    return time(int(m.group(1)), int(m.group(2)))


def parse_clock_range(value: Any, what: str = "range") -> ClockRange:
    parts = str(value).split("-")
    if len(parts) != 2:
        raise ConfigError(f"{what}: expected HH:MM-HH:MM, got {value!r}")
    start, end = parse_clock(parts[0], what), parse_clock(parts[1], what)
    if start == end:
        raise ConfigError(f"{what}: start and end are equal ({value!r})")
    return ClockRange(start, end)


def _require(d: dict[str, Any], key: str, where: str) -> Any:
    if key not in d or d[key] in (None, ""):
        raise ConfigError(f"{where}.{key} is required")
    return d[key]


def parse_config(raw: dict[str, Any]) -> PlannerConfig:
    if not isinstance(raw, dict):
        raise ConfigError("planner.yaml must be a mapping")

    tz_name = raw.get("timezone", "Asia/Seoul")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ConfigError(f"timezone: unknown zone {tz_name!r}") from e

    cal = _require(raw, "calendars", "planner")
    calendars = Calendars(**{k: str(_require(cal, k, "calendars")) for k in ("fixed", "plan", "project", "deadline")})

    notion = _require(raw, "notion", "planner")
    sources = NotionSources(**{k: str(_require(notion, k, "notion")) for k in ("tasks", "projects", "milestones", "jobs")})

    day_raw = _require(raw, "day", "planner")
    day = ClockRange(parse_clock(_require(day_raw, "start", "day"), "day.start"),
                     parse_clock(_require(day_raw, "end", "day"), "day.end"))
    if day.start == day.end:
        raise ConfigError("day: start and end are equal")

    blocked = tuple(
        Blocked(str(_require(b, "name", "blocked[]")), parse_clock_range(_require(b, "time", "blocked[]"), f"blocked {b.get('name')}"))
        for b in raw.get("blocked") or []
    )
    focus = tuple(parse_clock_range(r, "focus_hours") for r in raw.get("focus_hours") or [])

    block_raw = raw.get("block") or {}
    block = BlockRules(
        min=parse_duration(block_raw.get("min", "30m"), "block.min"),
        max=parse_duration(block_raw.get("max", "120m"), "block.max"),
        buffer=timedelta(0) if block_raw.get("buffer") in (0, "0", "0m") else parse_duration(block_raw.get("buffer", "15m"), "block.buffer"),
    )
    if block.min > block.max:
        raise ConfigError("block.min is larger than block.max")

    slack = float(raw.get("slack_ratio", 0.2))
    if not 0 <= slack < 1:
        raise ConfigError(f"slack_ratio must be in [0, 1), got {slack}")

    routines = []
    for r in raw.get("routines") or []:
        freq = str(r.get("frequency", "daily"))
        if not _FREQ_RE.match(freq):
            raise ConfigError(f"routine {r.get('name')!r}: frequency must be 'daily' or 'N/week', got {freq!r}")
        routines.append(Routine(
            name=str(_require(r, "name", "routines[]")),
            duration=parse_duration(_require(r, "duration", "routines[]"), f"routine {r.get('name')} duration"),
            frequency=freq,
            prefer=r.get("prefer"),
        ))

    known = {"timezone", "calendars", "notion", "day", "blocked", "focus_hours", "block", "slack_ratio", "routines"}
    extra = {k: v for k, v in raw.items() if k not in known}

    return PlannerConfig(tz, calendars, sources, day, blocked, focus, block, slack, tuple(routines), extra)


def load_config(path: str | Path) -> PlannerConfig:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"planner config not found: {p}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"planner config is not valid YAML: {e}") from e
    return parse_config(raw)
