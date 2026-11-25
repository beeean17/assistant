"""Google Calendar access: OAuth token refresh and event listing.

Only the `calendar.events` scope is used. The token file is the JSON written by
`python -m planner.google_auth` (google-auth-oauthlib's Credentials.to_json()).
Access tokens are refreshed in memory; the file itself is never rewritten.
"""

from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

API = "https://www.googleapis.com/calendar/v3"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class CalendarError(RuntimeError):
    pass


@dataclass(frozen=True)
class CalEvent:
    id: str
    calendar: str               # role from planner.yaml: fixed / plan / project / deadline
    title: str
    start: datetime | None      # timed events (timezone-aware)
    end: datetime | None
    all_day_start: date | None  # all-day events: [start, end) dates
    all_day_end: date | None
    transparent: bool           # "show as available"
    private: dict[str, str] = field(default_factory=dict)  # extendedProperties.private

    @property
    def all_day(self) -> bool:
        return self.all_day_start is not None


def parse_event(item: dict[str, Any], calendar: str, tz: ZoneInfo) -> CalEvent | None:
    """Convert a Calendar API event resource. Returns None for cancelled events."""
    if item.get("status") == "cancelled":
        return None
    start, end = item.get("start") or {}, item.get("end") or {}
    private = ((item.get("extendedProperties") or {}).get("private")) or {}
    common = dict(
        id=item["id"],
        calendar=calendar,
        title=item.get("summary") or "(제목 없음)",
        transparent=item.get("transparency") == "transparent",
        private=dict(private),
    )
    if "dateTime" in start:
        return CalEvent(
            start=datetime.fromisoformat(start["dateTime"]).astimezone(tz),
            end=datetime.fromisoformat(end["dateTime"]).astimezone(tz),
            all_day_start=None, all_day_end=None, **common,
        )
    if "date" in start:
        return CalEvent(
            start=None, end=None,
            all_day_start=date.fromisoformat(start["date"]),
            all_day_end=date.fromisoformat(end.get("date", start["date"])),
            **common,
        )
    return None


class CalendarClient(Protocol):
    def list_events(self, calendar: str, time_min: datetime, time_max: datetime) -> list[CalEvent]: ...


class TokenSource:
    """Refreshes Google access tokens from a stored refresh token."""

    def __init__(self, token_file: str | Path, http: httpx.Client) -> None:
        path = Path(token_file)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as e:
            raise CalendarError(
                f"Google token file not found at {path}. Run the one-time login (docs/setup/03-planner.md)."
            ) from e
        missing = [k for k in ("refresh_token", "client_id", "client_secret") if not data.get(k)]
        if missing:
            raise CalendarError(f"Google token file is missing {', '.join(missing)}; redo the login.")
        self._data = data
        self._http = http
        self._access: str | None = None
        self._expires_at = 0.0

    def access_token(self) -> str:
        if self._access and _time.time() < self._expires_at - 60:
            return self._access
        resp = self._http.post(
            self._data.get("token_uri") or DEFAULT_TOKEN_URI,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._data["refresh_token"],
                "client_id": self._data["client_id"],
                "client_secret": self._data["client_secret"],
            },
        )
        if resp.status_code != 200:
            err = resp.json().get("error", "") if resp.headers.get("content-type", "").startswith("application/json") else ""
            if err == "invalid_grant":
                raise CalendarError("Google refresh token was revoked or expired; redo the one-time login.")
            raise CalendarError(f"Google token refresh failed: HTTP {resp.status_code} {err}".strip())
        body = resp.json()
        self._access = body["access_token"]
        self._expires_at = _time.time() + float(body.get("expires_in", 3600))
        return self._access


class GoogleCalendar:
    def __init__(self, calendar_ids: dict[str, str], tokens: TokenSource, http: httpx.Client, tz: ZoneInfo) -> None:
        self._ids = calendar_ids
        self._tokens = tokens
        self._http = http
        self._tz = tz

    def list_events(self, calendar: str, time_min: datetime, time_max: datetime) -> list[CalEvent]:
        cal_id = self._ids[calendar]
        url = f"{API}/calendars/{quote(cal_id, safe='')}/events"
        params: dict[str, Any] = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",   # expand recurring events (RRULE) into instances
            "orderBy": "startTime",
            "maxResults": 250,
            "showDeleted": "false",
        }
        events: list[CalEvent] = []
        while True:
            resp = self._http.get(url, params=params, headers={"Authorization": f"Bearer {self._tokens.access_token()}"})
            if resp.status_code == 404:
                raise CalendarError(f"Calendar '{calendar}' not found or not shared with this account (check planner.yaml).")
            if resp.status_code != 200:
                raise CalendarError(f"Calendar API error for '{calendar}': HTTP {resp.status_code}")
            body = resp.json()
            for item in body.get("items", []):
                if (ev := parse_event(item, calendar, self._tz)) is not None:
                    events.append(ev)
            token = body.get("nextPageToken")
            if not token:
                return events
            params["pageToken"] = token

