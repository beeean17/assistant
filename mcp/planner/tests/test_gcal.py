import json
from datetime import date

import httpx
import pytest

from planner.gcal import CalendarError, GoogleCalendar, TokenSource, parse_event

from .conftest import KST, kst


def test_parse_timed_event_with_private_props():
    ev = parse_event({
        "id": "a1", "summary": "수업",
        "start": {"dateTime": "2026-11-23T09:00:00+09:00"}, "end": {"dateTime": "2026-11-23T10:30:00+09:00"},
        "extendedProperties": {"private": {"task_id": "t1", "kind": "task"}},
    }, "plan", KST)
    assert ev.start == kst(2026, 11, 23, 9) and ev.end == kst(2026, 11, 23, 10, 30)
    assert not ev.all_day and not ev.transparent
    assert ev.private == {"task_id": "t1", "kind": "task"}


def test_parse_utc_event_converted_to_local():
    ev = parse_event({"id": "a", "start": {"dateTime": "2026-11-23T00:00:00Z"}, "end": {"dateTime": "2026-11-23T01:00:00Z"}}, "fixed", KST)
    assert ev.start == kst(2026, 11, 23, 9)
    assert ev.title == "(제목 없음)"


def test_parse_all_day_and_transparency():
    ev = parse_event({"id": "b", "summary": "여행", "transparency": "transparent",
                      "start": {"date": "2026-11-23"}, "end": {"date": "2026-11-25"}}, "fixed", KST)
    assert ev.all_day and ev.transparent
    assert (ev.all_day_start, ev.all_day_end) == (date(2026, 11, 23), date(2026, 11, 25))


def test_cancelled_is_skipped():
    assert parse_event({"id": "c", "status": "cancelled"}, "fixed", KST) is None


def _token_file(tmp_path, **override):
    data = {"refresh_token": "r", "client_id": "cid", "client_secret": "sec", "token_uri": "https://oauth2.googleapis.com/token"}
    data.update(override)
    p = tmp_path / "google_token.json"
    p.write_text(json.dumps(data))
    return p


def test_token_refresh_and_cache(tmp_path):
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        return httpx.Response(200, json={"access_token": "at-1", "expires_in": 3600})

    ts = TokenSource(_token_file(tmp_path), httpx.Client(transport=httpx.MockTransport(handler)))
    assert ts.access_token() == "at-1"
    assert ts.access_token() == "at-1"
    assert len(calls) == 1
    assert b"grant_type=refresh_token" in calls[0].content


def test_invalid_grant_message(tmp_path):
    def handler(req):
        return httpx.Response(400, json={"error": "invalid_grant"})

    ts = TokenSource(_token_file(tmp_path), httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(CalendarError, match="redo the one-time login"):
        ts.access_token()


def test_missing_token_file(tmp_path):
    with pytest.raises(CalendarError, match="not found"):
        TokenSource(tmp_path / "missing.json", httpx.Client())


def test_token_file_without_refresh_token(tmp_path):
    with pytest.raises(CalendarError, match="refresh_token"):
        TokenSource(_token_file(tmp_path, refresh_token=None), httpx.Client())


def test_list_events_paginates_and_quotes_id(tmp_path):
    seen = []

    def handler(req: httpx.Request):
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        seen.append(req)
        assert req.headers["Authorization"] == "Bearer at"
        assert req.url.params["singleEvents"] == "true"
        item = lambda i: {"id": f"e{i}", "summary": f"E{i}", "start": {"dateTime": "2026-11-23T09:00:00+09:00"},
                          "end": {"dateTime": "2026-11-23T10:00:00+09:00"}}
        if "pageToken" not in req.url.params:
            return httpx.Response(200, json={"items": [item(1)], "nextPageToken": "p2"})
        return httpx.Response(200, json={"items": [item(2), {"id": "x", "status": "cancelled"}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    cal = GoogleCalendar({"fixed": "abc#holiday@group.calendar.google.com"}, TokenSource(_token_file(tmp_path), http), http, KST)
    events = cal.list_events("fixed", kst(2026, 11, 23, 8, 30), kst(2026, 11, 24, 1))
    assert [e.id for e in events] == ["e1", "e2"]
    assert "abc%23holiday%40group.calendar.google.com" in str(seen[0].url)


def test_calendar_404_explains(tmp_path):
    def handler(req):
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        return httpx.Response(404, json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    cal = GoogleCalendar({"plan": "p@g"}, TokenSource(_token_file(tmp_path), http), http, KST)
    with pytest.raises(CalendarError, match="planner.yaml"):
        cal.list_events("plan", kst(2026, 11, 23), kst(2026, 11, 24))
