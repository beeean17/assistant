from datetime import date

import pytest

from planner.notion import _UNSET
from planner.service import Planner, parse_day

from .conftest import FakeCalendar, FakeTasks, all_day, kst, timed

MON = date(2026, 11, 23)


MONDAY_7AM = kst(2026, 11, 23, 7, 0)


def make(cfg, events, now=MONDAY_7AM):
    tasks = FakeTasks()
    return Planner(cfg, tasks, FakeCalendar(events), clock=lambda: now), tasks


def test_parse_day_keywords():
    assert parse_day("today", MON) == MON
    assert parse_day("tomorrow", MON) == date(2026, 11, 24)
    assert parse_day("2026-12-01", MON) == date(2026, 12, 1)
    with pytest.raises(ValueError):
        parse_day("금요일", MON)


def test_today_uses_logical_day(cfg):
    p, _ = make(cfg, [], now=kst(2026, 11, 24, 0, 40))
    assert p.today() == MON


def test_get_day_merges_and_sorts(cfg):
    events = [
        timed("수업", kst(2026, 11, 23, 9), kst(2026, 11, 23, 10, 30)),
        timed("ERD", kst(2026, 11, 23, 14), kst(2026, 11, 23, 16), calendar="plan",
              private={"task_id": "t1", "kind": "task"}),
        timed("과제 마감", kst(2026, 11, 23, 23, 59), kst(2026, 11, 24, 0, 0), calendar="deadline"),
        all_day("생일", date(2026, 11, 23), date(2026, 11, 24), transparent=True),
        all_day("내일 행사", date(2026, 11, 24), date(2026, 11, 25)),  # overlaps 00:00-01:00 only
    ]
    p, _ = make(cfg, events)
    d = p.get_day("2026-11-23")
    kinds = [(i["kind"], i["title"]) for i in d["items"]]
    assert kinds == [("fixed", "수업"), ("blocked", "점심"), ("plan", "ERD"), ("blocked", "저녁"), ("deadline", "과제 마감")]
    plan_item = next(i for i in d["items"] if i["kind"] == "plan")
    assert plan_item["task_id"] == "t1" and plan_item["block_kind"] == "task"
    assert d["all_day"] == [{"title": "생일", "calendar": "fixed", "busy": False}]
    assert d["window"]["end"] == "2026-11-24T01:00+09:00"
    # Class 09:00-10:30 (+15m buffer) leaves 08:30-08:45, shorter than a block, so the
    # morning keeps only 10:45-12:00. The planned block (+buffer) takes 13:45-16:15.
    assert d["free_minutes"] == 75 + (45 + 135) + 330


def test_find_free_slots_ignores_plan_unless_asked(cfg):
    events = [timed("ERD", kst(2026, 11, 23, 14), kst(2026, 11, 23, 16), calendar="plan")]
    p, _ = make(cfg, events)
    assert p.find_free_slots("2026-11-23")["days"][0]["free_minutes"] == 870
    assert p.find_free_slots("2026-11-23", include_planned=True)["days"][0]["free_minutes"] == 870 - 150


def test_opaque_all_day_blocks_whole_logical_day(cfg):
    p, _ = make(cfg, [all_day("여행", date(2026, 11, 23), date(2026, 11, 24))])
    days = p.find_free_slots("2026-11-23", "2026-11-24")["days"]
    assert days[0]["free_minutes"] == 0          # including 00:00-01:00 after midnight
    assert days[1]["free_minutes"] == 870


def test_transparent_all_day_does_not_block(cfg):
    p, _ = make(cfg, [all_day("생일", date(2026, 11, 23), date(2026, 11, 24), transparent=True)])
    assert p.find_free_slots("2026-11-23")["days"][0]["free_minutes"] == 870


def test_range_limits(cfg):
    p, _ = make(cfg, [])
    with pytest.raises(ValueError, match="14 days"):
        p.find_free_slots("2026-11-23", "2026-12-07")
    with pytest.raises(ValueError, match="before"):
        p.find_free_slots("2026-11-24", "2026-11-23")
    days = p.find_free_slots("today", "2026-11-29")["days"]
    assert [d["weekday"] for d in days] == list("월화수목금토일")


def test_free_slots_today_starts_from_now(cfg):
    p, _ = make(cfg, [], now=kst(2026, 11, 23, 15, 0))
    day = p.find_free_slots("today")["days"][0]
    assert day["slots"][0]["start"] == "2026-11-23T15:00+09:00"


def test_complete_task_sets_complete_status_and_zero_remaining(cfg):
    p, tasks = make(cfg, [])
    t = p.add_task("ERD 정리", 2, None, "P1")
    p.complete_task(t["id"])
    _, fields = tasks.writes[-1]
    assert fields.status == "완료" and fields.remaining_h == 0


def test_update_task_passes_only_changed_fields(cfg):
    p, tasks = make(cfg, [])
    t = p.add_task("ERD 정리", None, None, None)
    p.update_task(t["id"], title=_UNSET, remaining_h=1.0, due=None)
    _, fields = tasks.writes[-1]
    assert fields.remaining_h == 1.0 and fields.due is None and fields.title is _UNSET
