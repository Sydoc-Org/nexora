"""ops/backlog_history.py — snapshot collection + StatisticsDB write (no live DB)."""

from unittest.mock import MagicMock, patch

import ops.backlog_history as bh


def _src(code, rows=None, err=None):
    src = MagicMock()
    src.code = code
    if err:
        src.backlog_by_process.side_effect = err
    else:
        src.backlog_by_process.return_value = rows or []
    return src


def test_collect_snapshot_flattens_all_sources(app):
    default = _src("default", [{"client": "GVL", "process": "Rechnungen", "count": 7}])
    ms02 = _src("ms02", [{"client": "MS02", "process": "Posteingang", "count": 3}])
    with patch.object(bh, "active_sources", return_value=[default, ms02]), app.app_context():
        rows = bh.collect_snapshot()
    assert rows == [
        ("default", "GVL", "Rechnungen", 7),
        ("ms02", "MS02", "Posteingang", 3),
    ]


def test_collect_snapshot_one_bad_source_does_not_block_others(app):
    bad = _src("default", err=RuntimeError("db down"))
    ms02 = _src("ms02", [{"client": "MS02", "process": "Posteingang", "count": 3}])
    with patch.object(bh, "active_sources", return_value=[bad, ms02]), app.app_context():
        rows = bh.collect_snapshot()
    assert rows == [("ms02", "MS02", "Posteingang", 3)]


def test_write_snapshot_ensures_table_and_inserts_shared_timestamp():
    fake_cur = MagicMock()
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    eng = MagicMock()
    eng.raw_connection.return_value = fake_conn
    now = object()
    rows = [("default", "GVL", "Rechnungen", 7), ("ms02", "MS02", "Posteingang", 3)]
    with patch.object(bh, "engine_statistics_db", eng):
        bh.write_snapshot(rows, now)

    ddl = str(fake_cur.execute.call_args_list[0].args[0])
    assert "BacklogHistory" in ddl and "IF NOT EXISTS" in ddl
    inserts = fake_cur.execute.call_args_list[1:]
    assert [c.args[1] for c in inserts] == [
        (now, "default", "GVL", "Rechnungen", 7),
        (now, "ms02", "MS02", "Posteingang", 3),
    ]
    fake_conn.commit.assert_called_once()
    fake_conn.close.assert_called_once()


def test_write_snapshot_rolls_back_and_raises_on_error():
    fake_cur = MagicMock()
    fake_cur.execute.side_effect = RuntimeError("boom")
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    eng = MagicMock()
    eng.raw_connection.return_value = fake_conn
    with patch.object(bh, "engine_statistics_db", eng):
        try:
            bh.write_snapshot([("default", "A", "P", 1)], object())
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass
    fake_conn.rollback.assert_called_once()
    fake_conn.close.assert_called_once()


def test_run_once_dry_run_writes_nothing():
    with (
        patch.object(bh, "collect_snapshot", return_value=[("default", "A", "P", 1)]),
        patch.object(bh, "write_snapshot") as write,
    ):
        assert bh.run_once(dry_run=True) == 0
    write.assert_not_called()
