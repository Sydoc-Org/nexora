"""Pure merge/pagination + source-normalization tests (no live DB)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from nx_lib.workitem_sources import (
    PostgresSource,
    SqlServerSource,
    WorkitemFilter,
    enrich_rows_from_nexora,
    merge_sorted_rows,
    resolve_nexora_filter_ids,
)


def _row(wid, mins, client="default"):
    return {
        "modifiedat": datetime(2026, 6, 16, 9, mins, 0),
        "workitemid": wid,
        "status": "Ready",
        "current_stage": "Extraction",
        "priority": 0,
        "tags": [],
        "client": client,
    }


def test_merge_sorted_rows_orders_by_modifiedat_desc():
    a = [_row(1, 10), _row(2, 30)]  # default
    b = [_row(1001, 20, "ms02")]  # ms02
    merged = merge_sorted_rows([a, b])
    assert [r["workitemid"] for r in merged] == [2, 1001, 1]


def test_merge_sorted_rows_stable_tiebreak_on_workitemid():
    a = [_row(5, 10)]
    b = [_row(2, 10, "ms02")]
    merged = merge_sorted_rows([a, b])
    assert [r["workitemid"] for r in merged] == [2, 5]


def test_merge_sorted_rows_handles_empty_sources():
    assert merge_sorted_rows([[], []]) == []


def _mk_filter():
    return WorkitemFilter(
        process_names=["Invoices"],
        client_names=["Privera"],
        activity_ignore_csv="'Ignore'",
    )


def test_sqlserver_source_normalizes_rows(app):
    count_row = [3]
    data_row = MagicMock(
        ModifiedAt=datetime(2026, 6, 16, 9, 0, 0),
        WorkItemID=7,
        Status="Ready",
        CurrentStage="Extraction",
        Priority=None,
        TagsJSON='[{"id":1,"name":"urgent","color":"#f00"}]',
    )
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = count_row
    fake_cur.fetchall.return_value = [data_row]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows, total = src.list_workitems(_mk_filter(), offset=0, limit=40)

    assert total == 3
    assert rows[0]["workitemid"] == 7
    assert rows[0]["priority"] == 0  # None -> 0
    assert rows[0]["tags"][0]["name"] == "urgent"
    assert rows[0]["client"] == "default"


def test_resolve_nexora_filter_ids_returns_none_when_no_filters(app):
    f = _mk_filter()  # no tag/priority/assigned
    with app.app_context():
        assert resolve_nexora_filter_ids(f) is None


def test_resolve_nexora_filter_ids_intersects_active_filters(app):
    f = _mk_filter()
    f.tag = "urgent"
    f.priority = "2"
    # tag query -> {1001, 1002}; priority query -> {1002, 1003}; intersect -> {1002}
    fake_cur = MagicMock()
    fake_cur.fetchall.side_effect = [
        [MagicMock(WorkItemID=1001), MagicMock(WorkItemID=1002)],
        [MagicMock(WorkItemID=1002), MagicMock(WorkItemID=1003)],
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    with patch("nx_lib.workitem_sources.engine_nexora_db") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        ids = resolve_nexora_filter_ids(f)
    assert ids == {1002}


def test_postgres_source_builds_pg_sql_and_enriches(app):
    # psycopg2 cursor returns namedtuple-ish rows; we normalize by attribute.
    count_row = [2]
    data_rows = [
        MagicMock(
            modifiedat=datetime(2026, 6, 16, 9, 5, 0),
            workitemid=1001,
            status="Ready",
            currentstage="Extraction",
        ),
    ]
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = count_row
    fake_cur.fetchall.return_value = data_rows
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = PostgresSource(CLIENTS_code="ms02")
    with (
        patch.object(src, "engine") as eng,
        patch("nx_lib.workitem_sources.enrich_rows_from_nexora", side_effect=lambda r: r),
        patch("nx_lib.workitem_sources.resolve_nexora_filter_ids", return_value=None),
        app.app_context(),
    ):
        eng.raw_connection.return_value = fake_conn
        rows, total = src.list_workitems(_mk_filter(), offset=0, limit=40)

    assert total == 2
    assert rows[0]["workitemid"] == 1001
    assert rows[0]["client"] == "ms02"
    # Verify the executed SQL used %s placeholders (psycopg2), not ?.
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "%s" in executed_sql
    assert "?" not in executed_sql


def test_enrich_rows_from_nexora_attaches_priority_and_tags(app):
    rows = [
        {"workitemid": 1001, "priority": 0, "tags": []},
        {"workitemid": 1002, "priority": 0, "tags": []},
    ]
    fake_cur = MagicMock()
    fake_cur.fetchall.side_effect = [
        # priority rows
        [MagicMock(WorkItemID=1001, Priority=3)],
        # tag rows
        [MagicMock(WorkItemID=1002, TagID=9, TagName="vip", TagColor="#0f0")],
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    with patch("nx_lib.workitem_sources.engine_nexora_db") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        out = enrich_rows_from_nexora(rows)
    by_id = {r["workitemid"]: r for r in out}
    assert by_id[1001]["priority"] == 3
    assert by_id[1002]["tags"] == [{"id": 9, "name": "vip", "color": "#0f0"}]
