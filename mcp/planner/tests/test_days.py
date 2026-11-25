from datetime import date, time, timedelta

import pytest

from planner.days import (
    Interval,
    clock_on_day,
    day_window,
    free_on_day,
    logical_day_of,
    merge,
    subtract,
    week_start,
)

from .conftest import kst

DAY = date(2026, 11, 23)  # Monday


def test_day_window_crosses_midnight(cfg):
    w = day_window(DAY, cfg)
    assert w.start == kst(2026, 11, 23, 8, 30)
    assert w.end == kst(2026, 11, 24, 1, 0)
    assert w.minutes == 990


def test_times_before_day_start_belong_to_next_date(cfg):
    assert clock_on_day(DAY, time(0, 30), cfg) == kst(2026, 11, 24, 0, 30)
    assert clock_on_day(DAY, time(23, 0), cfg) == kst(2026, 11, 23, 23, 0)


@pytest.mark.parametrize("moment,expected", [
    (kst(2026, 11, 24, 0, 30), date(2026, 11, 23)),   # after midnight, still Monday's day
    (kst(2026, 11, 24, 0, 59), date(2026, 11, 23)),
    (kst(2026, 11, 24, 1, 0), date(2026, 11, 24)),    # Monday's day has ended
    (kst(2026, 11, 24, 7, 0), date(2026, 11, 24)),    # early morning belongs to the coming day
    (kst(2026, 11, 24, 8, 30), date(2026, 11, 24)),
])
def test_logical_day_of(cfg, moment, expected):
    assert logical_day_of(moment, cfg) == expected


@pytest.mark.parametrize("d,monday", [
    (date(2026, 11, 23), date(2026, 11, 23)),  # Monday
    (date(2026, 11, 29), date(2026, 11, 23)),  # Sunday
    (date(2026, 11, 30), date(2026, 11, 30)),
    (date(2027, 1, 1), date(2026, 12, 28)),    # across a year boundary
])
def test_week_starts_monday(d, monday):
    assert week_start(d) == monday


def test_merge_and_subtract():
    a = Interval(kst(2026, 11, 23, 9), kst(2026, 11, 23, 10))
    b = Interval(kst(2026, 11, 23, 9, 30), kst(2026, 11, 23, 11))
    c = Interval(kst(2026, 11, 23, 11), kst(2026, 11, 23, 12))  # touching merges
    assert merge([c, a, b]) == [Interval(kst(2026, 11, 23, 9), kst(2026, 11, 23, 12))]
    window = Interval(kst(2026, 11, 23, 8), kst(2026, 11, 23, 13))
    assert subtract(window, [b]) == [
        Interval(kst(2026, 11, 23, 8), kst(2026, 11, 23, 9, 30)),
        Interval(kst(2026, 11, 23, 11), kst(2026, 11, 23, 13)),
    ]


def test_free_day_without_events(cfg):
    f = free_on_day(DAY, cfg, [])
    assert [(s.start, s.end) for s in f.slots] == [
        (kst(2026, 11, 23, 8, 30), kst(2026, 11, 23, 12)),
        (kst(2026, 11, 23, 13), kst(2026, 11, 23, 18, 30)),
        (kst(2026, 11, 23, 19, 30), kst(2026, 11, 24, 1)),
    ]
    assert f.free_minutes == 210 + 330 + 330
    assert f.plannable_minutes == int(870 * 0.8)


def test_event_is_widened_by_buffer(cfg):
    ev = Interval(kst(2026, 11, 23, 10), kst(2026, 11, 23, 11))
    f = free_on_day(DAY, cfg, [ev])
    assert f.slots[0] == Interval(kst(2026, 11, 23, 8, 30), kst(2026, 11, 23, 9, 45))
    assert f.slots[1] == Interval(kst(2026, 11, 23, 11, 15), kst(2026, 11, 23, 12))
    assert f.free_minutes == 870 - 90


def test_slots_shorter_than_min_block_are_dropped(cfg):
    ev = Interval(kst(2026, 11, 23, 14), kst(2026, 11, 23, 18, 10))  # leaves 18:25-18:30
    f = free_on_day(DAY, cfg, [ev])
    starts = [s.start for s in f.slots]
    assert kst(2026, 11, 23, 18, 25) not in starts
    assert Interval(kst(2026, 11, 23, 13), kst(2026, 11, 23, 13, 45)) in f.slots


def test_event_after_midnight_counts_for_the_logical_day(cfg):
    ev = Interval(kst(2026, 11, 24, 0, 15), kst(2026, 11, 24, 0, 45))
    f = free_on_day(DAY, cfg, [ev])
    assert f.slots[-1] == Interval(kst(2026, 11, 23, 19, 30), kst(2026, 11, 24, 0, 0))


def test_now_trims_the_past(cfg):
    f = free_on_day(DAY, cfg, [], now=kst(2026, 11, 23, 15, 0))
    assert f.slots[0].start == kst(2026, 11, 23, 15, 0)
    assert f.free_minutes == 210 + 330


def test_now_after_window_means_no_free_time(cfg):
    f = free_on_day(DAY, cfg, [], now=kst(2026, 11, 24, 2, 0))
    assert f.slots == [] and f.free_minutes == 0


def test_naive_datetimes_rejected():
    from datetime import datetime
    with pytest.raises(ValueError):
        Interval(datetime(2026, 11, 23, 9), datetime(2026, 11, 23, 10))


def test_buffer_zero(cfg):
    from dataclasses import replace
    c = replace(cfg, block=replace(cfg.block, buffer=timedelta(0)))
    ev = Interval(kst(2026, 11, 23, 10), kst(2026, 11, 23, 11))
    assert free_on_day(DAY, c, [ev]).free_minutes == 870 - 60


def test_logical_day_when_day_does_not_cross_midnight(cfg):
    from dataclasses import replace
    from planner.config import ClockRange
    c = replace(cfg, day=ClockRange(time(7, 0), time(23, 0)))
    assert logical_day_of(kst(2026, 11, 24, 0, 30), c) == date(2026, 11, 24)
