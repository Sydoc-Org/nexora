"""_get_workitems_data threads a pidImport session token into ms02_docfield_ids
and suppresses the default source during a PID import."""

from unittest.mock import patch

from werkzeug.datastructures import MultiDict

import nx_lib.views.workitems as wv


def test_pid_ids_intersected_into_ms02_docfield_ids(app):
    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    with app.test_request_context():
        from flask import session

        session["pid_import:tok123"] = {"ids": [10, 20, 30], "pid_to_wids": {}, "payloads": {}}
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            wv._get_workitems_data(MultiDict([("pidImport", "tok123")]))
    filt = captured["filt"]
    assert filt.ms02_docfield_ids == {10, 20, 30}
    assert filt.pid_import_active is True


def test_no_pid_param_leaves_filter_unconstrained(app):
    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    with (
        app.test_request_context(),
        patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
        patch.object(wv, "has_permission", return_value=True),
    ):
        wv._get_workitems_data(MultiDict())
    assert captured["filt"].pid_import_active is False


def test_unknown_pid_token_is_ignored(app):
    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    with (
        app.test_request_context(),
        patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
        patch.object(wv, "has_permission", return_value=True),
    ):
        wv._get_workitems_data(MultiDict([("pidImport", "nope")]))
    # Unknown token -> treated as an empty import (MS02-only, zero MS02 rows).
    assert captured["filt"].pid_import_active is True
    assert captured["filt"].ms02_docfield_ids == set()


def test_pid_ids_intersected_with_existing_ms02_docfield_ids(app):
    """ms02_docfield_ids & pid_ids: {10,20,40} ∩ {10,20,30} == {10,20}."""
    from unittest.mock import MagicMock

    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    # Build a mock raw_connection whose cursor returns:
    #   - empty fetchall() for the default (SQL Server) docfield block
    #   - one row [("FieldName",)] for the MS02 cursor_nex2 block
    # Both blocks call engine_nexora_db.raw_connection(), so we use a
    # side_effect list: first call = default block, second call = MS02 block.
    def make_mock_conn(fetchall_return):
        mock_cur = MagicMock()
        mock_cur.execute.return_value = mock_cur
        mock_cur.fetchall.return_value = fetchall_return
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        return mock_conn

    mock_engine_nex = MagicMock()
    mock_engine_nex.raw_connection.side_effect = [
        make_mock_conn([]),  # conn_nex  (default docfield block) -> no configs
        make_mock_conn([("FieldName",)]),  # conn_nex2 (MS02 docfield block)   -> one name
    ]

    with app.test_request_context():
        from flask import session

        # A process permission makes target_processes non-empty, which is required
        # for both docfield blocks to execute.
        session["permissions"] = ["workitems.filter.process.foo.bar"]
        session["pid_import:tok_intersect"] = {
            "ids": [10, 20, 30],
            "pid_to_wids": {},
            "payloads": {},
        }

        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
            patch.object(wv, "get_valid_search_columns", return_value=["col_name"]),
            patch.object(wv, "engine_nexora_db", mock_engine_nex),
            patch.object(wv, "engine_ms02_docfields_pg", MagicMock()),
            patch.object(wv, "resolve_ms02_docfield_ids", return_value={10, 20, 40}),
        ):
            wv._get_workitems_data(
                MultiDict(
                    [
                        ("pidImport", "tok_intersect"),
                        ("docfield", "name"),
                        ("docvalue", "x"),
                    ]
                )
            )

    # {10,20,40} (MS02 docfield pre-resolve) ∩ {10,20,30} (pidImport) == {10,20}
    assert captured["filt"].ms02_docfield_ids == {10, 20}
    assert captured["filt"].pid_import_active is True
