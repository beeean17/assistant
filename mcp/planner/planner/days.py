"""Logical days, intervals and free-slot computation (pure functions).

A logical day runs from `day.start` to `day.end` in the configured timezone and
may cross midnight: with 08:30-01:00 the day 2026-11-23 is
[2026-11-23 08:30, 2026-11-24 01:00). Any wall-clock time earlier than
`day.start` belongs to the next calendar date of that logical day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .config import ClockRange, PlannerConfig


@dataclass(frozen=True, order=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Interval needs timezone-aware datetimes")

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)

    def clip(self, window: Interval) -> Interval | None:
        s, e = max(self.start, window.start), min(self.end, window.end)
        return Interval(s, e) if s < e else None


def clock_on_day(day: date, t: time, cfg: PlannerConfig) -> datetime:
    """Datetime of wall-clock `t` within logical day `day`."""
    d = day if t >= cfg.day.start else day + timedelta(days=1)
    return datetime.combine(d, t, tzinfo=cfg.timezone)


def day_window(day: date, cfg: PlannerConfig) -> Interval:
    return Interval(clock_on_day(day, cfg.day.start, cfg), clock_on_day(day, cfg.day.end, cfg))


def range_on_day(day: date, r: ClockRange, cfg: PlannerConfig) -> Interval:
    """Place a wall-clock range in a logical day; its start decides the calendar date."""
    start = clock_on_day(day, r.start, cfg)
    length = (datetime.combine(date.min, r.end) - datetime.combine(date.min, r.start)) % timedelta(days=1)
    # Add wall-clock duration in local time so DST-free zones and others behave alike.
    end = (start.replace(tzinfo=None) + length).replace(tzinfo=cfg.timezone)
    return Interval(start, end)


def logical_day_of(moment: datetime, cfg: PlannerConfig) -> date:
    """The logical day a moment belongs to.

    Only the after-midnight tail of a day that crosses midnight (00:00 up to
    day.end) belongs to the previous date. The night between day.end and
    day.start belongs to the coming day, so "today" at 07:00 is that date.
    """
    local = moment.astimezone(cfg.timezone)
    crosses_midnight = cfg.day.end < cfg.day.start
    if crosses_midnight and local.time() < cfg.day.end:
        return local.date() - timedelta(days=1)
    return local.date()


def week_start(day: date) -> date:
    """Monday of the week containing `day` (weeks start on Monday)."""
    return day - timedelta(days=day.weekday())


def merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for iv in sorted(intervals):
        if out and iv.start <= out[-1].end:
            if iv.end > out[-1].end:
                out[-1] = Interval(out[-1].start, iv.end)
        else:
            out.append(iv)
    return out


def subtract(window: Interval, busy: list[Interval]) -> list[Interval]:
    free: list[Interval] = []
    cursor = window.start
    for b in merge([c for iv in busy if (c := iv.clip(window))]):
        if b.start > cursor:
            free.append(Interval(cursor, b.start))
        cursor = max(cursor, b.end)
    if cursor < window.end:
        free.append(Interval(cursor, window.end))
    return free


@dataclass(frozen=True)
class DayFree:
    day: date
    window: Interval
    slots: list[Interval]       # usable free slots (each >= block.min)
    free_minutes: int           # total of `slots`
    plannable_minutes: int      # free_minutes minus the slack_ratio reserve


def blocked_intervals(day: date, cfg: PlannerConfig) -> list[tuple[str, Interval]]:
    return [(b.name, range_on_day(day, b.range, cfg)) for b in cfg.blocked]


def free_on_day(day: date, cfg: PlannerConfig, events: list[Interval], now: datetime | None = None) -> DayFree:
    """Free time on a logical day.

    free = day window - blocked rules - (events widened by block.buffer on each side),
    restricted to the future when `now` falls inside the day, keeping only slots of
    at least block.min. slack_ratio is a capacity reserve, not a time window: it
    lowers plannable_minutes but leaves the slots themselves intact.
    """
    window = day_window(day, cfg)
    if now is not None:
        if now >= window.end:
            return DayFree(day, window, [], 0, 0)
        if now > window.start:
            window = Interval(now, window.end)

    buf = cfg.block.buffer
    busy = [iv for _, iv in blocked_intervals(day, cfg)]
    busy += [Interval(e.start - buf, e.end + buf) for e in events]

    slots = [s for s in subtract(window, busy) if s.end - s.start >= cfg.block.min]
    total = sum(s.minutes for s in slots)
    plannable = int(total * (1 - cfg.slack_ratio))
    return DayFree(day, window, slots, total, plannable)
