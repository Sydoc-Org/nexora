"""ops/backlog_history/backlog_history.py — standalone collector (no live DB)."""

from unittest.mock import MagicMock, patch

from ops.backlog_history import backlog_history as bh


def test_collect_snapshot_flattens_sources_and_drops_excluded():
    octo = [
        ("Privera", "02_Posteingang", 462),
        ("Privera", "01_Reporting", 258),  # EXCLUDED
        ("Privera", "02_Invoice", 8),  # EXCLUDED
        ("Privera", "Zeus", 20),  # EXCLUDED
        ("sydoc", "DPSI_Template", 2),  # EXCLUDED
        ("Compass", "01_Invoice_SAP", 17),
    ]
    ms02 = [("sydoc", "05_PDBS", 478)]
    with (
        patch.object(bh, "fetch_octo", return_value=octo),
        patch.object(bh, "fetch_ms02", return_value=ms02),
    ):
        rows = bh.collect_snapshot()
    assert rows == [
        ("default", "Privera", "02_Posteingang", 462),
        ("default", "Compass", "01_Invoice_SAP", 17),
        ("ms02", "sydoc", "05_PDBS", 478),
    ]


def test_collect_snapshot_one_bad_source_does_not_block_the_other(capsys):
    with (
        patch.object(bh, "fetch_octo", side_effect=RuntimeError("db down")),
        patch.object(bh, "fetch_ms02", return_value=[("sydoc", "05_PDBS", 3)]),
    ):
        rows = bh.collect_snapshot()
    assert rows == [("ms02", "sydoc", "05_PDBS", 3)]
    assert "source default failed" in capsys.readouterr().err


def test_fetch_ms02_skips_gracefully_without_env(monkeypatch):
    for var in ("MS02_DB_SERVER_PRD", "MS02_DB_OCTO_RUNTIME", "MS02_DB_UID", "MS02_DB_PWD"):
        monkeypatch.delenv(var, raising=False)
    assert bh.fetch_ms02() == []


def test_write_snapshot_ensures_table_and_inserts_shared_timestamp(monkeypatch):
    monkeypatch.setenv("DB_STATISTICS", "sydoc_stat")
    fake_cur = MagicMock()
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    now = object()
    rows = [("default", "GVL", "Rechnungen", 7), ("ms02", "MS02", "Posteingang", 3)]
    with patch.object(bh, "_mssql_connect", return_value=fake_conn) as connect:
        bh.write_snapshot(rows, now)

    connect.assert_called_once_with("sydoc_stat")
    ddl = str(fake_cur.execute.call_args_list[0].args[0])
    assert "BacklogHistory" in ddl and "IF NOT EXISTS" in ddl and "SnapshotAt " in ddl
    inserts = fake_cur.execute.call_args_list[1:]
    assert [c.args[1] for c in inserts] == [
        (now, "default", "GVL", "Rechnungen", 7),
        (now, "ms02", "MS02", "Posteingang", 3),
    ]
    fake_conn.commit.assert_called_once()
    fake_conn.close.assert_called_once()


def test_write_snapshot_rolls_back_and_raises_on_error(monkeypatch):
    monkeypatch.setenv("DB_STATISTICS", "sydoc_stat")
    fake_cur = MagicMock()
    fake_cur.execute.side_effect = RuntimeError("boom")
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    with patch.object(bh, "_mssql_connect", return_value=fake_conn):
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


def test_run_once_writes_local_naive_timestamp():
    with (
        patch.object(bh, "collect_snapshot", return_value=[("default", "A", "P", 1)]),
        patch.object(bh, "write_snapshot") as write,
    ):
        assert bh.run_once() == 0
    now = write.call_args.args[1]
    assert now.tzinfo is None and now.microsecond == 0
