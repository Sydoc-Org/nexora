"""Unit tests for the dbo.PreparedDocuments data-access helpers.

CI/TEST has no live NexoraDB, so the cursor/connection is mocked (mirroring
tests/unit/test_workitem_sources.py). Insert vs update is classified by a
pre-SELECT existence check per PID, NOT by MERGE OUTPUT (the repo's proven
MERGE exemplar _cache_store uses neither OUTPUT nor a post-fetch).
"""

from unittest.mock import MagicMock

import pytest

import nx_lib.prepared_documents as pd


def _mock_engine(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    engine = MagicMock()
    engine.raw_connection.return_value = conn
    return engine, conn


def test_upsert_inserts_then_updates_same_pid_no_dup(monkeypatch):
    """Re-uploading the same PID issues a MERGE per row and reports counts; the
    pre-SELECT existence check classifies row 1 as insert, row 2 as update."""
    cur = MagicMock()
    # Per row: one SELECT (existence) then one MERGE. fetchone() answers the
    # SELECT: None -> not present (insert); (1,) -> present (update).
    cur.fetchone.side_effect = [None, (1,)]
    engine, conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)

    rows = [
        {
            "pid": "100",
            "collected": True,
            "collected_by": "A",
            "prepared": False,
            "prepared_by": "",
        },
        {
            "pid": "100",
            "collected": False,
            "collected_by": "",
            "prepared": True,
            "prepared_by": "B",
        },
    ]
    result = pd.upsert_prepared_documents(rows, uploaded_by=7)

    assert result == {"inserted": 1, "updated": 1, "total": 2}
    # Two executes per row (SELECT + MERGE) -> 4 total.
    assert cur.execute.call_count == 4
    # The MERGE keys on PID and targets the register.
    merge_calls = [c for c in cur.execute.call_args_list if "MERGE" in c.args[0].upper()]
    assert len(merge_calls) == 2
    assert "PreparedDocuments" in merge_calls[0].args[0]
    assert 7 in merge_calls[0].args[1]  # UploadedBy stamped
    conn.commit.assert_called_once()


def test_upsert_mixed_batch_counts(monkeypatch):
    """A batch with one new and one existing PID -> inserted=1, updated=1."""
    cur = MagicMock()
    cur.fetchone.side_effect = [None, (1,)]
    engine, conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    rows = [
        {
            "pid": "111",
            "collected": True,
            "collected_by": "A",
            "prepared": False,
            "prepared_by": "",
        },
        {
            "pid": "222",
            "collected": False,
            "collected_by": "",
            "prepared": True,
            "prepared_by": "B",
        },
    ]
    result = pd.upsert_prepared_documents(rows, uploaded_by=3)
    assert result == {"inserted": 1, "updated": 1, "total": 2}


def test_upsert_raises_runtimeerror_on_db_failure(app, monkeypatch):
    cur = MagicMock()
    cur.execute.side_effect = Exception("boom")
    engine, conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    rows = [
        {
            "pid": "1",
            "collected": False,
            "collected_by": "",
            "prepared": False,
            "prepared_by": "",
        }
    ]
    with app.app_context(), pytest.raises(RuntimeError, match="prepared documents upsert failed"):
        pd.upsert_prepared_documents(rows, uploaded_by=None)
    conn.rollback.assert_called_once()


def test_fetch_page_maps_columns(monkeypatch):
    cur = MagicMock()
    cur.fetchall.return_value = [
        (1, "100", True, "A", False, "", 7, "2026-06-23T10:00:00", None),
    ]
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    rows = pd.fetch_prepared_documents_page(offset=0, limit=40)
    assert rows[0]["pid"] == "100"
    assert rows[0]["collected"] is True
    assert rows[0]["collected_by"] == "A"
    assert rows[0]["prepared_by"] == ""
    sql_used = cur.execute.call_args.args[0]
    assert "OFFSET" in sql_used.upper()
    assert "FETCH NEXT" in sql_used.upper()


def test_count_returns_int(monkeypatch):
    cur = MagicMock()
    cur.fetchone.return_value = (12,)
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    assert pd.count_prepared_documents() == 12


def test_clear_deletes_all(monkeypatch):
    cur = MagicMock()
    cur.rowcount = 5
    engine, conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    assert pd.clear_prepared_documents() == 5
    sql_used = cur.execute.call_args.args[0]
    assert "DELETE" in sql_used.upper()
    conn.commit.assert_called_once()


def test_pids_in_register_empty_input_no_db(monkeypatch):
    class _Boom:
        def raw_connection(self):
            raise AssertionError("should not connect")

    monkeypatch.setattr(pd, "engine_nexora_db", _Boom())
    assert pd.pids_in_register([]) == set()


def test_pids_in_register_returns_matched_set(monkeypatch):
    cur = MagicMock()
    cur.fetchall.return_value = [("100",), ("222",)]
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    result = pd.pids_in_register(["100", "200", "222"])
    assert result == {"100", "222"}
    sql_used = cur.execute.call_args.args[0]
    assert "PreparedDocuments" in sql_used
    assert sql_used.count("?") == 3  # one placeholder per input pid (parameterized)
    assert cur.execute.call_args.args[1] == ["100", "200", "222"]


def test_pids_in_register_never_raises(app, monkeypatch):
    cur = MagicMock()
    cur.execute.side_effect = Exception("boom")
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    with app.app_context():
        assert pd.pids_in_register(["1"]) == set()


def test_count_with_pid_adds_where(monkeypatch):
    cur = MagicMock()
    cur.fetchone.return_value = (1,)
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    assert pd.count_prepared_documents(pid="100") == 1
    sql_used = cur.execute.call_args.args[0]
    assert "WHERE PID = ?" in sql_used
    assert cur.execute.call_args.args[1] == ["100"]


def test_fetch_page_with_pid_filters(monkeypatch):
    cur = MagicMock()
    cur.fetchall.return_value = [(1, "100", True, "A", False, "", 7, None, None)]
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    rows = pd.fetch_prepared_documents_page(0, 40, pid="100")
    assert rows[0]["pid"] == "100"
    sql_used = cur.execute.call_args.args[0]
    assert "WHERE PID = ?" in sql_used


def test_count_with_collected_and_prepared_filters(monkeypatch):
    cur = MagicMock()
    cur.fetchone.return_value = (1,)
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    assert pd.count_prepared_documents(collected=True, prepared=False) == 1
    sql_used = cur.execute.call_args.args[0]
    assert "Collected = ?" in sql_used
    assert "Prepared = ?" in sql_used
    assert cur.execute.call_args.args[1] == [1, 0]


def test_fetch_page_group_by_orders_by_column(monkeypatch):
    cur = MagicMock()
    cur.fetchall.return_value = []
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    pd.fetch_prepared_documents_page(0, 40, group_by="collected_by")
    sql_used = cur.execute.call_args.args[0]
    assert "ORDER BY CollectedBy ASC, ID DESC" in sql_used


def test_fetch_page_unknown_group_by_falls_back_to_id_desc(monkeypatch):
    cur = MagicMock()
    cur.fetchall.return_value = []
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    pd.fetch_prepared_documents_page(0, 40, group_by="not_a_real_column")
    sql_used = cur.execute.call_args.args[0]
    assert "ORDER BY ID DESC" in sql_used
