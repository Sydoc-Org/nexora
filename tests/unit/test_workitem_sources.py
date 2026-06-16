"""Pure merge/pagination + source-normalization tests (no live DB)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import nx_lib.workitem_sources as ws
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


def test_get_source_for_workitem_cache_hit(app, monkeypatch):
    monkeypatch.setattr(ws, "_cache_lookup", lambda wid: "ms02")
    with app.app_context():
        assert ws.get_source_for_workitem(424242) == "ms02"


def test_get_source_for_workitem_probes_then_caches(app, monkeypatch):
    monkeypatch.setattr(ws, "_cache_lookup", lambda wid: None)
    cached = {}
    monkeypatch.setattr(ws, "_cache_store", lambda wid, code: cached.setdefault(wid, code))

    class FakeMs02:
        code = "ms02"

        def has_workitem(self, wid):
            return wid == 999000

    monkeypatch.setattr(ws, "non_default_source_instances", lambda: [FakeMs02()])
    with app.app_context():
        assert ws.get_source_for_workitem(999000) == "ms02"
        assert cached[999000] == "ms02"


def test_get_source_for_workitem_defaults_when_no_match(app, monkeypatch):
    monkeypatch.setattr(ws, "_cache_lookup", lambda wid: None)
    monkeypatch.setattr(ws, "non_default_source_instances", lambda: [])
    with app.app_context():
        assert ws.get_source_for_workitem(5) == "default"


def test_get_source_for_workitem_ambiguous_falls_back_to_default(app, monkeypatch):
    """Fail-safe: if >1 non-default source claims an id (id spaces overlap),
    routing must NOT guess — it logs and returns 'default'."""
    monkeypatch.setattr(ws, "_cache_lookup", lambda wid: None)
    monkeypatch.setattr(ws, "_cache_store", lambda wid, code: None)

    class Claimer:
        def __init__(self, code):
            self.code = code

        def has_workitem(self, wid):
            return True

    monkeypatch.setattr(
        ws, "non_default_source_instances", lambda: [Claimer("ms02"), Claimer("ms03")]
    )
    with app.app_context():
        assert ws.get_source_for_workitem(5) == "default"


def test_get_domain_for_workitem_maps_client_to_domain(app, monkeypatch):
    monkeypatch.setattr(ws, "get_source_for_workitem", lambda wid: "default")
    with app.app_context():
        from nx_lib.workitem_sources import CLIENTS

        assert ws.get_domain_for_workitem(5) == CLIENTS["default"].octo_domain


def test_fetch_merged_page_single_source_passthrough(app, monkeypatch):
    one = SqlServerSource()
    monkeypatch.setattr(ws, "active_sources", lambda: [one])
    monkeypatch.setattr(one, "list_workitems", lambda filt, offset, limit: ([_row(1, 10)], 1))
    with app.app_context():
        rows, total, degraded = ws.fetch_merged_page(_mk_filter(), offset=0, limit=40)
    assert total == 1
    assert degraded == []
    assert rows[0]["workitemid"] == 1


def test_fetch_merged_page_merges_and_slices(app, monkeypatch):
    s1, s2 = SqlServerSource(), SqlServerSource()
    monkeypatch.setattr(ws, "active_sources", lambda: [s1, s2])
    monkeypatch.setattr(
        s1, "list_workitems", lambda filt, offset, limit: ([_row(2, 30), _row(1, 10)], 2)
    )
    monkeypatch.setattr(s2, "list_workitems", lambda filt, offset, limit: ([_row(1001, 20)], 1))
    with app.app_context():
        rows, total, degraded = ws.fetch_merged_page(_mk_filter(), offset=0, limit=2)
    assert total == 3
    assert [r["workitemid"] for r in rows] == [2, 1001]  # top 2 of merged desc


def test_fetch_merged_page_degrades_on_source_error(app, monkeypatch):
    s1, s2 = SqlServerSource(), SqlServerSource()
    s2.code = "ms02"
    monkeypatch.setattr(ws, "active_sources", lambda: [s1, s2])
    monkeypatch.setattr(s1, "list_workitems", lambda filt, offset, limit: ([_row(2, 30)], 1))

    def boom(*a, **k):
        raise RuntimeError("PG down")

    monkeypatch.setattr(s2, "list_workitems", boom)
    with app.app_context():
        rows, total, degraded = ws.fetch_merged_page(_mk_filter(), offset=0, limit=40)
    assert [r["workitemid"] for r in rows] == [2]
    assert total == 1
    assert degraded == ["ms02"]
