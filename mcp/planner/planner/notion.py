"""Notion Tasks access (API version 2026-03-11, data source endpoints).

Property names follow docs/homeserver-hermes-architecture.md ("Notion 스키마").
Status is judged by its group (to_do / in_progress / complete), read from the
data source schema, never by option name alone.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx

NOTION_VERSION = "2026-03-11"
API = "https://api.notion.com/v1"

# Tasks properties
P_TITLE = "제목"
P_PROJECT = "프로젝트"
P_MILESTONE = "단계"
P_STATUS = "상태"
P_PRIORITY = "우선순위"
P_ESTIMATE = "예상 시간"
P_REMAINING = "남은 시간"
P_DUE = "마감"
P_BLOCKS = "블록"

PRIORITIES = ("P1", "P2", "P3")
GROUPS = ("to_do", "in_progress", "complete")


class NotionError(RuntimeError):
    pass


@dataclass(frozen=True)
class StatusSchema:
    """Status option name -> group, in option order."""

    groups: dict[str, str]

    def names_in(self, *groups: str) -> list[str]:
        return [n for n, g in self.groups.items() if g in groups]

    def first_in(self, group: str) -> str:
        names = self.names_in(group)
        if not names:
            raise NotionError(f"Tasks status has no option in group {group!r}")
        return names[0]


def parse_status_schema(data_source: dict[str, Any]) -> StatusSchema:
    prop = (data_source.get("properties") or {}).get(P_STATUS)
    if not prop or prop.get("type") != "status":
        raise NotionError(f"Tasks data source has no status property named {P_STATUS!r}")
    options = {o["id"]: o["name"] for o in prop["status"]["options"]}
    group_of: dict[str, str] = {}
    groups = prop["status"]["groups"]
    for i, g in enumerate(groups):
        key = _group_key(g) or (GROUPS[i] if len(groups) == len(GROUPS) else "to_do")
        for oid in g.get("option_ids", []):
            if oid in options:
                group_of[options[oid]] = key
    ordered = {name: group_of.get(name, "to_do") for name in options.values()}
    return StatusSchema(ordered)


def _group_key(group: dict[str, Any]) -> str | None:
    """Map a status group to to_do / in_progress / complete by its name.

    The API returns display names ("To-do", "In progress", "Complete"). Returns
    None for an unrecognized name so the caller can fall back to group order.
    """
    name = (group.get("name") or "").lower().replace("-", "").replace(" ", "").replace("_", "")
    if name in ("todo", "notstarted"):
        return "to_do"
    if name in ("inprogress", "doing", "current"):
        return "in_progress"
    if name in ("complete", "completed", "done"):
        return "complete"
    return None


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    status: str | None
    status_group: str | None
    priority: str | None
    estimate_h: float | None
    remaining_h: float | None
    due: str | None              # ISO date or datetime as stored in Notion
    project_ids: tuple[str, ...] = ()
    milestone_ids: tuple[str, ...] = ()
    blocks: str = ""
    url: str | None = None

    @property
    def needed_h(self) -> float | None:
        """Hours still to schedule: remaining, else estimate."""
        return self.remaining_h if self.remaining_h is not None else self.estimate_h

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "status_group": self.status_group,
            "priority": self.priority,
            "estimate_h": self.estimate_h,
            "remaining_h": self.remaining_h,
            "needed_h": self.needed_h,
            "due": self.due,
            "project_ids": list(self.project_ids),
            "milestone_ids": list(self.milestone_ids),
            "url": self.url,
        }


def _plain(rich: list[dict[str, Any]] | None) -> str:
    return "".join(r.get("plain_text") or (r.get("text") or {}).get("content", "") for r in rich or [])


def page_to_task(page: dict[str, Any], schema: StatusSchema) -> Task:
    props = page.get("properties") or {}

    def prop(name: str) -> dict[str, Any]:
        return props.get(name) or {}

    status = (prop(P_STATUS).get("status") or {}).get("name")
    due = prop(P_DUE).get("date") or {}
    return Task(
        id=page["id"],
        title=_plain(prop(P_TITLE).get("title")),
        status=status,
        status_group=schema.groups.get(status) if status else None,
        priority=(prop(P_PRIORITY).get("select") or {}).get("name"),
        estimate_h=prop(P_ESTIMATE).get("number"),
        remaining_h=prop(P_REMAINING).get("number"),
        due=due.get("start"),
        project_ids=tuple(r["id"] for r in prop(P_PROJECT).get("relation") or []),
        milestone_ids=tuple(r["id"] for r in prop(P_MILESTONE).get("relation") or []),
        blocks=_plain(prop(P_BLOCKS).get("rich_text")),
        url=page.get("url"),
    )


_UNSET: Any = object()


@dataclass
class TaskFields:
    """Fields to write. Leave a field as _UNSET to keep it; None clears it."""

    title: str = _UNSET
    status: str = _UNSET
    priority: str | None = _UNSET
    estimate_h: float | None = _UNSET
    remaining_h: float | None = _UNSET
    due: str | None = _UNSET          # "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM" (local time)
    project_ids: list[str] = field(default=_UNSET)


def normalize_due(value: str, tz: ZoneInfo) -> str:
    """Validate a due date and return the Notion date string.

    Accepts YYYY-MM-DD (all-day) or YYYY-MM-DDTHH:MM[:SS] with or without an
    offset; naive times are taken as local time in `tz`.
    """
    v = value.strip()
    try:
        if len(v) == 10:
            return date.fromisoformat(v).isoformat()
        dt = datetime.fromisoformat(v)
    except ValueError as e:
        raise ValueError(f"due must be YYYY-MM-DD or YYYY-MM-DDTHH:MM, got {value!r}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.isoformat(timespec="minutes")


def fields_to_properties(f: TaskFields, schema: StatusSchema, tz: ZoneInfo) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if f.title is not _UNSET:
        if not f.title or not f.title.strip():
            raise ValueError("title must not be empty")
        props[P_TITLE] = {"title": [{"type": "text", "text": {"content": f.title.strip()}}]}
    if f.status is not _UNSET:
        if f.status not in schema.groups:
            raise ValueError(f"status must be one of {list(schema.groups)}, got {f.status!r}")
        props[P_STATUS] = {"status": {"name": f.status}}
    if f.priority is not _UNSET:
        if f.priority is not None and f.priority not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}, got {f.priority!r}")
        props[P_PRIORITY] = {"select": {"name": f.priority} if f.priority else None}
    for name, key in ((P_ESTIMATE, "estimate_h"), (P_REMAINING, "remaining_h")):
        val = getattr(f, key)
        if val is not _UNSET:
            if val is not None and val < 0:
                raise ValueError(f"{key} must not be negative")
            props[name] = {"number": val}
    if f.due is not _UNSET:
        props[P_DUE] = {"date": {"start": normalize_due(f.due, tz)} if f.due else None}
    if f.project_ids is not _UNSET:
        props[P_PROJECT] = {"relation": [{"id": i} for i in f.project_ids]}
    return props


def open_tasks_filter(schema: StatusSchema) -> dict[str, Any]:
    names = schema.names_in("to_do", "in_progress")
    return {"or": [{"property": P_STATUS, "status": {"equals": n}} for n in names]}


class TaskStore(Protocol):
    def list_tasks(self, include_done: bool = False, limit: int = 50) -> list[Task]: ...
    def get_task(self, task_id: str) -> Task: ...
    def create_task(self, fields: TaskFields) -> Task: ...
    def update_task(self, task_id: str, fields: TaskFields) -> Task: ...
    def status_schema(self) -> StatusSchema: ...


class NotionTasks:
    def __init__(self, token: str, data_source_id: str, http: httpx.Client, tz: ZoneInfo) -> None:
        if not token:
            raise NotionError("NOTION_TOKEN is not set for the planner MCP server")
        self._ds = data_source_id
        self._http = http
        self._tz = tz
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        self._schema: StatusSchema | None = None

    def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(3):
            resp = self._http.request(method, f"{API}{path}", headers=self._headers, json=json)
            if resp.status_code == 429 and attempt < 2:
                _time.sleep(min(float(resp.headers.get("Retry-After", "1")), 10))
                continue
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                    msg = f"{body.get('code', '')}: {body.get('message', '')}"
                except ValueError:
                    msg = resp.text[:200]
                if resp.status_code in (401, 403):
                    raise NotionError(f"Notion rejected the token ({resp.status_code}). Check NOTION_TOKEN and that the integration is connected to the '비서' page.")
                if resp.status_code == 404:
                    raise NotionError(f"Notion object not found or not shared with the integration: {msg}")
                raise NotionError(f"Notion API error {resp.status_code}: {msg}")
            return resp.json()
        raise NotionError("Notion API rate limit: retried 3 times")

    def status_schema(self) -> StatusSchema:
        if self._schema is None:
            self._schema = parse_status_schema(self._request("GET", f"/data_sources/{self._ds}"))
        return self._schema

    def list_tasks(self, include_done: bool = False, limit: int = 50) -> list[Task]:
        schema = self.status_schema()
        body: dict[str, Any] = {
            "page_size": min(limit, 100),
            "sorts": [{"property": P_DUE, "direction": "ascending"}],
        }
        if not include_done:
            body["filter"] = open_tasks_filter(schema)
        tasks: list[Task] = []
        while True:
            data = self._request("POST", f"/data_sources/{self._ds}/query", body)
            tasks += [page_to_task(p, schema) for p in data.get("results", [])]
            if not data.get("has_more") or len(tasks) >= limit:
                return tasks[:limit]
            body["start_cursor"] = data["next_cursor"]

    def get_task(self, task_id: str) -> Task:
        page = self._request("GET", f"/pages/{task_id}")
        parent = page.get("parent") or {}
        if parent.get("data_source_id", "").replace("-", "") != self._ds.replace("-", ""):
            raise NotionError("That page is not in the Tasks data source")
        return page_to_task(page, self.status_schema())

    def create_task(self, fields: TaskFields) -> Task:
        schema = self.status_schema()
        if fields.status is _UNSET:
            fields.status = schema.first_in("to_do")
        props = fields_to_properties(fields, schema, self._tz)
        page = self._request("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": self._ds}, "properties": props})
        return page_to_task(page, schema)

    def update_task(self, task_id: str, fields: TaskFields) -> Task:
        self.get_task(task_id)  # make sure it is a Task before writing
        props = fields_to_properties(fields, self.status_schema(), self._tz)
        if not props:
            raise ValueError("nothing to update")
        page = self._request("PATCH", f"/pages/{task_id}", {"properties": props})
        return page_to_task(page, self.status_schema())
