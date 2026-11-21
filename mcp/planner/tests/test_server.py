"""Tool layer: arguments reach the planner and expected failures become tool errors."""

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import planner.server as srv
from planner.service import Planner

from .conftest import FakeCalendar, FakeTasks, kst, timed


@pytest.fixture
def fake_planner(cfg, monkeypatch):
    events = [timed("수업", kst(2026, 11, 23, 9), kst(2026, 11, 23, 10, 30))]
    p = Planner(cfg, FakeTasks(), FakeCalendar(events), clock=lambda: kst(2026, 11, 23, 8, 0))
    monkeypatch.setattr(srv, "_planner", p)
    return p


def call(name, args):
    return asyncio.run(srv.server.call_tool(name, args))


def test_get_day_through_tool_layer(fake_planner):
    result = call("get_day", {"date": "2026-11-23"})
    assert not result.is_error
    assert result.structured_content["items"][0]["title"] == "수업"


def test_update_task_clear_reaches_store(fake_planner):
    t = call("add_task", {"title": "ERD 정리", "estimate_h": 2}).structured_content
    call("update_task", {"task_id": t["id"], "remaining_h": 1, "clear": ["due"]})
    _, fields = fake_planner.tasks.writes[-1]
    assert fields.remaining_h == 1 and fields.due is None


def test_value_error_becomes_tool_error(fake_planner):
    with pytest.raises(ToolError, match="YYYY-MM-DD"):
        call("find_free_slots", {"start": "다음 주"})


def test_invalid_priority_rejected_by_schema(fake_planner):
    with pytest.raises(ToolError):
        call("add_task", {"title": "x", "priority": "P9"})


def test_config_error_becomes_tool_error(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "_planner", None)
    monkeypatch.setenv("PLANNER_CONFIG", str(tmp_path / "missing.yaml"))
    with pytest.raises(ToolError, match="not found"):
        call("list_tasks", {})


def test_notion_tools_work_without_google_token(cfg, monkeypatch, tmp_path):
    """_build must not touch the Google token until a calendar tool runs."""
    import yaml
    from .conftest import EXAMPLE
    conf = tmp_path / "planner.yaml"
    conf.write_text(yaml.safe_dump(EXAMPLE, allow_unicode=True))
    monkeypatch.setattr(srv, "_planner", None)
    monkeypatch.setenv("PLANNER_CONFIG", str(conf))
    monkeypatch.setenv("NOTION_TOKEN", "secret")
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "missing.json"))
    p = srv._build()  # no error although the token file is missing
    with pytest.raises(Exception, match="Google token file not found"):
        p.calendar.list_events("fixed", kst(2026, 11, 23), kst(2026, 11, 24))
