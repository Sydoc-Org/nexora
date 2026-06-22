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

        session["pid_import:tok123"] = [10, 20, 30]
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
