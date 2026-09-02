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


# ==================== _resolve_prepared_doc_wid_stages (batch) ====================
# nx_lib.views.workitems._resolve_prepared_doc_wid_stages resolves a whole
# prepared-documents page's wids in ONE query instead of one per PID (up to
# 200/page). Kept here alongside the rest of the prepared-documents coverage.


def test_resolve_prepared_doc_wid_stages_batches_into_one_pg_query(monkeypatch, app):
    """N wids -> exactly ONE _resolve_octo_wid_stage_pg_batch call (not N),
    and each wid's resolved stage matches what the old per-wid loop over
    _resolve_octo_wid_stage_pg would have produced."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS, ClientConfig

    ms02_engine = object()
    ms02_client = ClientConfig(
        code="ms02",
        runtime_engine=ms02_engine,
        dialect="postgres",
        octo_domain="ms02.example",
        octo_client_id="id",
        octo_secret="secret",
        octo_grant_type="client_credentials",
    )
    monkeypatch.setitem(CLIENTS, "ms02", ms02_client)

    calls = []

    def fake_pg_batch(engine, wids):
        calls.append((engine, list(wids)))
        return {
            42: {"status": "Ready", "current_stage": "Import"},
            43: {"status": "Done", "current_stage": "Delivery"},
            # 44 intentionally missing -- a wid with no DB match.
        }

    monkeypatch.setattr(wv, "_resolve_octo_wid_stage_pg_batch", fake_pg_batch)

    with app.app_context():
        result = wv._resolve_prepared_doc_wid_stages([42, 43, 44])

    assert len(calls) == 1  # ONE round-trip for all 3 wids, not 3.
    assert calls[0][0] is ms02_engine
    assert result == {
        42: {"status": "Ready", "current_stage": "Import"},
        43: {"status": "Done", "current_stage": "Delivery"},
        # A wid missing from the batch result degrades to the same empty
        # stage the single-wid resolver returns for a miss -- never absent
        # from the returned dict, so callers can always index by wid.
        44: {"status": None, "current_stage": None},
    }


def test_resolve_prepared_doc_wid_stages_empty_input_short_circuits(app):
    import nx_lib.views.workitems as wv

    with app.app_context():
        assert wv._resolve_prepared_doc_wid_stages([]) == {}


def test_resolve_prepared_doc_wid_stages_fails_closed_without_ms02_client(monkeypatch, app):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.delitem(CLIENTS, "ms02", raising=False)
    with app.app_context():
        assert wv._resolve_prepared_doc_wid_stages([1, 2]) == {
            1: {"status": None, "current_stage": None},
            2: {"status": None, "current_stage": None},
        }


def test_resolve_prepared_doc_wid_stages_fails_closed_on_malformed_client(monkeypatch, app):
    """A malformed CLIENTS['ms02'] entry (e.g. missing .dialect) must not
    raise -- same fail-closed contract as the single-wid resolver."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setitem(CLIENTS, "ms02", object())
    with app.app_context():
        assert wv._resolve_prepared_doc_wid_stages([1, 2]) == {
            1: {"status": None, "current_stage": None},
            2: {"status": None, "current_stage": None},
        }
