import copy
from datetime import time, timedelta
from pathlib import Path

import pytest

from planner.config import ConfigError, load_config, parse_clock_range, parse_config, parse_duration

from .conftest import EXAMPLE


@pytest.mark.parametrize("raw,minutes", [("30m", 30), ("2h", 120), ("1h30m", 90), (45, 45)])
def test_parse_duration(raw, minutes):
    assert parse_duration(raw) == timedelta(minutes=minutes)


@pytest.mark.parametrize("raw", ["", "abc", "0m", -5, "30", True])
def test_parse_duration_rejects(raw):
    with pytest.raises(ConfigError):
        parse_duration(raw)


def test_clock_range_may_cross_midnight():
    r = parse_clock_range("23:00-01:00")
    assert (r.start, r.end) == (time(23), time(1))


def test_example_parses(cfg):
    assert cfg.day.start == time(8, 30) and cfg.day.end == time(1, 0)
    assert [b.name for b in cfg.blocked] == ["점심", "저녁"]
    assert cfg.block.buffer == timedelta(minutes=15)
    assert cfg.notion.tasks == "ds-tasks"
    assert cfg.calendars.fixed == "fixed@cal"
    assert [r.per_week for r in cfg.routines] == [7, 3]
    assert cfg.extra["auto_apply"]["max_changed_blocks"] == 2


def test_missing_calendar_is_an_error():
    raw = copy.deepcopy(EXAMPLE)
    del raw["calendars"]["plan"]
    with pytest.raises(ConfigError, match="calendars.plan"):
        parse_config(raw)


def test_bad_frequency():
    raw = copy.deepcopy(EXAMPLE)
    raw["routines"][1]["frequency"] = "often"
    with pytest.raises(ConfigError, match="frequency"):
        parse_config(raw)


def test_zero_buffer_allowed():
    raw = copy.deepcopy(EXAMPLE)
    raw["block"]["buffer"] = "0m"
    assert parse_config(raw).block.buffer == timedelta(0)


def test_slack_ratio_range():
    raw = copy.deepcopy(EXAMPLE)
    raw["slack_ratio"] = 1.0
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_load_config_missing_file(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_example_file_in_repo_parses():
    example = Path(__file__).resolve().parents[3] / "deploy" / "planner.yaml.example"
    cfg = load_config(example)
    assert cfg.day.start == time(8, 30)
