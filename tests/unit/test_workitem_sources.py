"""Pure merge/pagination + source-normalization tests (no live DB)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from nx_lib.workitem_sources import SqlServerSource, WorkitemFilter, merge_sorted_rows


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
