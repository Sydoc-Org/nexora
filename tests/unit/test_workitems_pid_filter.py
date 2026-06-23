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


def test_richer_stash_pid_ids_loaded_correctly(app):
    """New dict stash: ids key drives the allow-set."""
    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    with app.test_request_context():
        from flask import session

        session["pid_import:tok_rich"] = {
            "ids": [10, 20, 30],
            "pid_to_wids": {"p1": [10]},
            "payloads": {
                "p1": {"collected": True, "collected_by": "A", "prepared": False, "prepared_by": ""}
            },
        }
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            wv._get_workitems_data(MultiDict([("pidImport", "tok_rich")]))
    assert captured["filt"].ms02_docfield_ids == {10, 20, 30}
    assert captured["filt"].pid_import_active is True


def test_import_payload_merged_onto_matched_row(app):
    """Rows whose workitemid appears in pid_to_wids get pid_import grafted in."""
    matched_row = {
        "workitemid": 10,
        "status": "Done",
        "modifiedat": None,
        "priority": 0,
        "tags": [],
        "current_stage": "",
        "client": "ms02",
    }

    def fake_fetch(filt, offset, limit):
        return [matched_row], 1, []

    with app.test_request_context():
        from flask import session

        session["pid_import:tok_merge"] = {
            "ids": [10],
            "pid_to_wids": {"999": [10]},
            "payloads": {
                "999": {
                    "collected": True,
                    "collected_by": "Guy1",
                    "prepared": True,
                    "prepared_by": "Girl2",
                }
            },
        }
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            result = wv._get_workitems_data(MultiDict([("pidImport", "tok_merge")]))

    workitems = result["workitems"]
    assert len(workitems) == 1
    imp = workitems[0].get("pid_import")
    assert imp is not None
    assert imp["collected"] is True
    assert imp["collected_by"] == "Guy1"
    assert imp["prepared"] is True
    assert imp["prepared_by"] == "Girl2"


def test_unmatched_pid_becomes_synthetic_row_on_page_1(app):
    """PIDs with no wids -> synthetic row appended (offset=0 = page 1)."""

    def fake_fetch(filt, offset, limit):
        return [], 0, []

    with app.test_request_context():
        from flask import session

        session["pid_import:tok_synthetic"] = {
            "ids": [],
            "pid_to_wids": {},  # empty: no PID resolved to any workitem
            "payloads": {
                "77777": {
                    "collected": False,
                    "collected_by": "",
                    "prepared": True,
                    "prepared_by": "Bob",
                }
            },
        }
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            result = wv._get_workitems_data(MultiDict([("pidImport", "tok_synthetic")]))

    workitems = result["workitems"]
    assert len(workitems) == 1
    syn = workitems[0]
    assert syn.get("synthetic") is True
    assert syn["pid"] == "77777"
    assert syn["pid_import"]["prepared_by"] == "Bob"
    assert result["pagination"]["totalItems"] == 1


def test_synthetic_rows_not_appended_on_page_2(app):
    """offset > 0 (page 2+): no synthetic rows appended."""

    def fake_fetch(filt, offset, limit):
        return [], 0, []

    with app.test_request_context():
        from flask import session

        session["pid_import:tok_p2"] = {
            "ids": [],
            "pid_to_wids": {},
            "payloads": {
                "55555": {
                    "collected": False,
                    "collected_by": "",
                    "prepared": False,
                    "prepared_by": "",
                }
            },
        }
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            # page=2 -> offset = (2-1)*40 = 40
            result = wv._get_workitems_data(MultiDict([("pidImport", "tok_p2"), ("page", "2")]))

    assert result["workitems"] == []
    assert result["pagination"]["totalItems"] == 0


def test_legacy_flatlist_stash_degrades_without_synthetics(app):
    """Legacy bare-list session token (pre-deploy format) still drives the
    allow-set but yields NO row enrichment and NO synthetic rows."""
    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    with app.test_request_context():
        from flask import session

        # Legacy format: a bare list, not the new {ids, pid_to_wids, payloads} dict.
        session["pid_import:tok_legacy"] = [10, 20, 30]
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            result = wv._get_workitems_data(MultiDict([("pidImport", "tok_legacy")]))

    # Legacy ids still constrain the MS02 allow-set.
    assert captured["filt"].ms02_docfield_ids == {10, 20, 30}
    assert captured["filt"].pid_import_active is True
    # _pid_import_meta is None for the legacy branch -> no synthetics, no bump.
    assert result["workitems"] == []
    assert result["pagination"]["totalItems"] == 0
