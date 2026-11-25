import json

import httpx
import pytest

from planner.notion import (
    NOTION_VERSION,
    NotionError,
    NotionTasks,
    TaskFields,
    fields_to_properties,
    normalize_due,
    open_tasks_filter,
    page_to_task,
    parse_status_schema,
)

from .conftest import KST, SCHEMA

DATA_SOURCE = {
    "object": "data_source",
    "properties": {
        "상태": {
            "type": "status",
            "status": {
                "options": [{"id": "o1", "name": "할 일"}, {"id": "o2", "name": "진행"}, {"id": "o3", "name": "완료"}],
                "groups": [
                    {"id": "g1", "name": "To-do", "option_ids": ["o1"]},
                    {"id": "g2", "name": "In progress", "option_ids": ["o2"]},
                    {"id": "g3", "name": "Complete", "option_ids": ["o3"]},
                ],
            },
        }
    },
}


def page(**props):
    base = {
        "제목": {"type": "title", "title": [{"plain_text": "ERD 정리"}]},
        "상태": {"type": "status", "status": {"name": "진행"}},
        "우선순위": {"type": "select", "select": {"name": "P1"}},
        "예상 시간": {"type": "number", "number": 2},
        "남은 시간": {"type": "number", "number": None},
        "마감": {"type": "date", "date": {"start": "2026-11-27"}},
        "프로젝트": {"type": "relation", "relation": [{"id": "p1"}]},
        "단계": {"type": "relation", "relation": []},
        "블록": {"type": "rich_text", "rich_text": []},
    }
    base.update(props)
    return {"object": "page", "id": "task-1", "url": "https://app.notion.com/p/task1",
            "parent": {"type": "data_source_id", "data_source_id": "ds-tasks"}, "properties": base}


def test_status_schema_groups():
    s = parse_status_schema(DATA_SOURCE)
    assert s.groups == {"할 일": "to_do", "진행": "in_progress", "완료": "complete"}
    assert s.first_in("complete") == "완료"


def test_status_schema_falls_back_to_group_order():
    ds = json.loads(json.dumps(DATA_SOURCE))
    for g, n in zip(ds["properties"]["상태"]["status"]["groups"], ["대기", "작업", "끝"], strict=False):
        g["name"] = n
    assert parse_status_schema(ds).groups["완료"] == "complete"


def test_page_to_task():
    t = page_to_task(page(), SCHEMA)
    assert (t.title, t.status, t.status_group, t.priority) == ("ERD 정리", "진행", "in_progress", "P1")
    assert t.needed_h == 2
    assert t.project_ids == ("p1",)
    assert t.due == "2026-11-27"


def test_needed_hours_prefers_remaining():
    t = page_to_task(page(**{"남은 시간": {"type": "number", "number": 0.5}}), SCHEMA)
    assert t.needed_h == 0.5


@pytest.mark.parametrize("raw,expected", [
    ("2026-11-27", "2026-11-27"),
    ("2026-11-27T18:00", "2026-11-27T18:00+09:00"),
    ("2026-11-27T09:00:00+00:00", "2026-11-27T09:00+00:00"),
])
def test_normalize_due(raw, expected):
    assert normalize_due(raw, KST) == expected


def test_normalize_due_rejects():
    with pytest.raises(ValueError):
        normalize_due("next friday", KST)


def test_fields_to_properties_shapes():
    props = fields_to_properties(TaskFields(title=" A ", priority="P2", estimate_h=1.5, due="2026-11-27T18:00", status="진행"), SCHEMA, KST)
    assert props["제목"]["title"][0]["text"]["content"] == "A"
    assert props["우선순위"] == {"select": {"name": "P2"}}
    assert props["예상 시간"] == {"number": 1.5}
    assert props["마감"] == {"date": {"start": "2026-11-27T18:00+09:00"}}
    assert props["상태"] == {"status": {"name": "진행"}}


def test_fields_clear_and_validate():
    props = fields_to_properties(TaskFields(due=None, priority=None), SCHEMA, KST)
    assert props == {"마감": {"date": None}, "우선순위": {"select": None}}
    with pytest.raises(ValueError):
        fields_to_properties(TaskFields(status="보류"), SCHEMA, KST)
    with pytest.raises(ValueError):
        fields_to_properties(TaskFields(priority="P9"), SCHEMA, KST)
    with pytest.raises(ValueError):
        fields_to_properties(TaskFields(estimate_h=-1), SCHEMA, KST)
    with pytest.raises(ValueError):
        fields_to_properties(TaskFields(title="  "), SCHEMA, KST)


def test_open_filter_uses_groups():
    f = open_tasks_filter(SCHEMA)
    assert [c["status"]["equals"] for c in f["or"]] == ["할 일", "진행"]


class Recorder:
    def __init__(self, routes):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request):
        self.requests.append(req)
        assert req.headers["Notion-Version"] == NOTION_VERSION
        for (method, path), resp in self.routes.items():
            if req.method == method and req.url.path == path:
                return resp(req) if callable(resp) else resp
        return httpx.Response(404, json={"code": "object_not_found", "message": "no route"})


def store(routes):
    rec = Recorder({("GET", "/v1/data_sources/ds-tasks"): httpx.Response(200, json=DATA_SOURCE), **routes})
    return NotionTasks("secret", "ds-tasks", httpx.Client(transport=httpx.MockTransport(rec)), KST), rec


def test_list_tasks_filters_open_and_paginates():
    pages = iter([
        httpx.Response(200, json={"results": [page()], "has_more": True, "next_cursor": "c2"}),
        httpx.Response(200, json={"results": [page()], "has_more": False}),
    ])
    s, rec = store({("POST", "/v1/data_sources/ds-tasks/query"): lambda req: next(pages)})
    tasks = s.list_tasks()
    assert len(tasks) == 2
    queries = [json.loads(r.content) for r in rec.requests if r.method == "POST"]
    assert queries[0]["filter"]["or"][0]["status"]["equals"] == "할 일"
    assert queries[1]["start_cursor"] == "c2"


def test_create_task_uses_data_source_parent_and_default_status():
    def create(req):
        body = json.loads(req.content)
        assert body["parent"] == {"type": "data_source_id", "data_source_id": "ds-tasks"}
        assert body["properties"]["상태"] == {"status": {"name": "할 일"}}
        return httpx.Response(200, json=page(**{"상태": {"type": "status", "status": {"name": "할 일"}}}))

    s, _ = store({("POST", "/v1/pages"): create})
    assert s.create_task(TaskFields(title="ERD 정리")).status == "할 일"


def test_update_rejects_page_outside_tasks():
    other = page()
    other["parent"] = {"type": "data_source_id", "data_source_id": "ds-other"}
    s, _ = store({("GET", "/v1/pages/task-1"): httpx.Response(200, json=other)})
    with pytest.raises(NotionError, match="not in the Tasks"):
        s.update_task("task-1", TaskFields(title="x"))


def test_unauthorized_message():
    rec = Recorder({("GET", "/v1/data_sources/ds-tasks"): httpx.Response(401, json={"code": "unauthorized", "message": "API token is invalid."})})
    s = NotionTasks("bad", "ds-tasks", httpx.Client(transport=httpx.MockTransport(rec)), KST)
    with pytest.raises(NotionError, match="NOTION_TOKEN"):
        s.list_tasks()


def test_missing_token():
    with pytest.raises(NotionError, match="NOTION_TOKEN"):
        NotionTasks("", "ds-tasks", httpx.Client(), KST)
