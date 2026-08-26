"""Unit tests for nx_lib.process_helpers — stat-query builders."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nx_lib import process_helpers as ph_mod
from nx_lib.process_helpers import (
    build_stat_query,
    get_activity_instances_to_ignore,
    get_params_from_process_list,
    prepare_process_selection_lists,
    prepare_process_selection_sql,
)


@pytest.fixture(autouse=True)
def clear_cache(app):
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()
    yield
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()


@pytest.fixture()
def ph_fake_session(monkeypatch):
    """Patch nx_lib.process_helpers.session (it imports session at module
    level, separate from security.session)."""
    sess = {}
    monkeypatch.setattr("nx_lib.process_helpers.session", sess)
    return sess


# ---------- prepare_process_selection_sql ----------


def test_prepare_process_selection_sql_all_builds_pair_predicate_not_cross_product(
    app, ph_fake_session
):
    """Grants: (A, P1) and (B, P2) only. The OLD shape independently uniqued
    clients=[A,B] and processes=[P1,P2] into two IN-lists, which -- ANDed
    together -- authorize the full cross product (A,P2) and (B,P1) too. The
    fixed shape must return an OR-joined pair predicate whose params can only
    ever reconstruct the two GRANTED pairs."""
    ph_fake_session["permissions"] = [
        "stat.A.P1",
        "stat.B.P2",
        "unrelated.perm",
    ]
    with app.app_context():
        params, predicate = prepare_process_selection_sql("stat.", "all")

    assert predicate == "(client = ? AND process = ?) OR (client = ? AND process = ?)"
    assert params == ["A", "P1", "B", "P2"]

    # Reconstruct the (client, process) pairs the predicate can actually match.
    built_pairs = list(zip(params[0::2], params[1::2], strict=True))
    assert built_pairs == [("A", "P1"), ("B", "P2")]
    # The illegitimate cross-product pairs must never be constructible.
    assert ("A", "P2") not in built_pairs
    assert ("B", "P1") not in built_pairs


def test_prepare_process_selection_sql_specific_uses_has_permission(app, ph_fake_session):
    ph_fake_session["permissions"] = ["stat.Privera.Invoices"]
    # Need to also patch security.session because has_permission reads it
    import nx_lib.security as sec_mod

    with patch.object(sec_mod, "session", ph_fake_session), app.app_context():
        params, predicate = prepare_process_selection_sql("stat.", "Privera.Invoices")
    assert params == ["Privera", "Invoices"]
    assert predicate == "(client = ? AND process = ?)"


def test_prepare_process_selection_sql_specific_without_perm_empty(app, ph_fake_session):
    import nx_lib.security as sec_mod

    ph_fake_session["permissions"] = []
    with patch.object(sec_mod, "session", ph_fake_session), app.app_context():
        params, predicate = prepare_process_selection_sql("stat.", "Privera.Invoices")
    assert params == []
    assert predicate == ""


def test_prepare_process_selection_sql_logs_and_raises_on_exception(app, ph_fake_session):
    # Force an exception by making session.get raise
    bad_sess = MagicMock()
    bad_sess.get.side_effect = RuntimeError("boom")
    with (
        patch.object(ph_mod, "session", bad_sess),
        app.app_context(),
        pytest.raises(RuntimeError),
    ):
        prepare_process_selection_sql("stat.", "all")


# ---------- prepare_process_selection_lists ----------


def test_prepare_process_selection_lists_all_builds_granted_pairs_not_cross_product(
    app, ph_fake_session
):
    """Same cross-product scenario as the _sql twin, for the list-building
    sibling used by the multi-source WorkitemFilter."""
    ph_fake_session["permissions"] = [
        "workitems.filter.process.A.P1",
        "workitems.filter.process.B.P2",
        "unrelated.perm",
    ]
    with app.app_context():
        pairs = prepare_process_selection_lists("workitems.filter.process.", "all")

    assert pairs == [("A", "P1"), ("B", "P2")]
    assert ("A", "P2") not in pairs
    assert ("B", "P1") not in pairs


def test_prepare_process_selection_lists_specific_uses_has_permission(app, ph_fake_session):
    ph_fake_session["permissions"] = ["workitems.filter.process.Privera.Invoices"]
    import nx_lib.security as sec_mod

    with patch.object(sec_mod, "session", ph_fake_session), app.app_context():
        pairs = prepare_process_selection_lists("workitems.filter.process.", "Privera.Invoices")
    assert pairs == [("Privera", "Invoices")]


def test_prepare_process_selection_lists_specific_without_perm_empty(app, ph_fake_session):
    import nx_lib.security as sec_mod

    ph_fake_session["permissions"] = []
    with patch.object(sec_mod, "session", ph_fake_session), app.app_context():
        pairs = prepare_process_selection_lists("workitems.filter.process.", "Privera.Invoices")
    assert pairs == []


def test_prepare_process_selection_lists_logs_and_raises_on_exception(app, ph_fake_session):
    bad_sess = MagicMock()
    bad_sess.get.side_effect = RuntimeError("boom")
    with (
        patch.object(ph_mod, "session", bad_sess),
        app.app_context(),
        pytest.raises(RuntimeError),
    ):
        prepare_process_selection_lists("workitems.filter.process.", "all")


def test_prepare_process_selection_lists_multiselect_keeps_only_granted(app, ph_fake_session):
    """Comma-joined multi-selection (issue #150): every entry is checked on its
    own, so an ungranted process smuggled into the list is dropped rather than
    authorizing the whole selection."""
    import nx_lib.security as sec_mod

    ph_fake_session["permissions"] = [
        "workitems.filter.process.A.P1",
        "workitems.filter.process.B.P2",
    ]
    with patch.object(sec_mod, "session", ph_fake_session), app.app_context():
        pairs = prepare_process_selection_lists("workitems.filter.process.", "A.P1,C.P3,B.P2")
    assert pairs == [("A", "P1"), ("B", "P2")]


# ---------- normalize_process_selection ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("all", ("all", ["A.P1", "B.P2", "C.P3"])),
        ("", ("all", ["A.P1", "B.P2", "C.P3"])),
        (None, ("all", ["A.P1", "B.P2", "C.P3"])),
        ("A.P1", ("A.P1", ["A.P1"])),
        ("B.P2,A.P1", ("A.P1,B.P2", ["A.P1", "B.P2"])),  # sorted -> stable cache key
        (" A.P1 , B.P2 ", ("A.P1,B.P2", ["A.P1", "B.P2"])),
        ("A.P1,A.P1", ("A.P1", ["A.P1"])),
        ("A.P1,ZZ.evil", ("A.P1", ["A.P1"])),  # ungranted entry dropped
        ("ZZ.evil", ("all", ["A.P1", "B.P2", "C.P3"])),  # nothing left -> full allowed set
        ("A.P1,B.P2,C.P3", ("all", ["A.P1", "B.P2", "C.P3"])),  # everything == all
    ],
)
def test_normalize_process_selection(value, expected):
    assert ph_mod.normalize_process_selection(value, {"C.P3", "A.P1", "B.P2"}) == expected


def test_normalize_process_selection_empty_allowed_set():
    assert ph_mod.normalize_process_selection("A.P1", []) == ("all", [])


# ---------- get_activity_instances_to_ignore ----------


def test_get_activity_instances_to_ignore_uses_cache(app):
    """When cache.get returns a value, the DB is not touched."""
    from nx_lib.extensions import cache

    with app.app_context():
        cache.set("activity_instances_ignore", "cached-value")
        result = get_activity_instances_to_ignore()
    assert result == "cached-value"


def test_get_activity_instances_to_ignore_returns_joined_quoted(app):
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = [
        MagicMock(ActivityInstanceName="Approval"),
        MagicMock(ActivityInstanceName="Index"),
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with (
        patch.object(ph_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        result = get_activity_instances_to_ignore()

    assert result == "'Approval', 'Index'"


def test_get_activity_instances_to_ignore_escapes_embedded_quotes(app):
    """A name containing a literal single quote (e.g. "O'Brien"-style) must
    have it doubled per SQL string-literal escaping, so the raw-spliced
    `NOT IN ({csv})` fragment stays syntactically valid instead of breaking
    (or injecting) on the unescaped quote."""
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = [
        MagicMock(ActivityInstanceName="O'Brien Review"),
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with (
        patch.object(ph_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        result = get_activity_instances_to_ignore()

    assert result == "'O''Brien Review'"
    # A naive split on "'" around an unescaped quote would leave an odd
    # number of quotes (unbalanced literal); doubling keeps it even/paired.
    assert result.count("'") % 2 == 0


def test_get_activity_instances_to_ignore_returns_empty_string_on_db_error(app):
    """If raw_connection raises, the function logs and returns "" explicitly
    (not None) -- callers treat the ignore-csv as a string, and an implicit
    None previously risked `NOT IN (None)`-style misuse downstream."""
    with (
        patch.object(ph_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.side_effect = RuntimeError("DB down")
        result = get_activity_instances_to_ignore()
    assert result == ""


# ---------- get_params_from_process_list ----------


def test_get_params_from_process_list_empty():
    params, proc_ph, client_ph = get_params_from_process_list([])
    assert params == []
    assert proc_ph == ""
    assert client_ph == ""


def test_get_params_from_process_list_filters_non_dotted_entries():
    params, proc_ph, client_ph = get_params_from_process_list(
        ["Privera.Invoices", "nodot", "Sydoc.Workitems"]
    )
    # Procs: Invoices, Workitems. Clients: Privera, Sydoc.
    assert params == ["Invoices", "Workitems", "Privera", "Sydoc"]
    assert proc_ph == "?, ?"
    assert client_ph == "?, ?"


def test_get_params_from_process_list_dedups_and_sorts():
    params, proc_ph, client_ph = get_params_from_process_list(
        ["Privera.Invoices", "Privera.Invoices", "Sydoc.Invoices"]
    )
    # Procs unique: ['Invoices']. Clients unique: ['Privera', 'Sydoc']
    assert params == ["Invoices", "Privera", "Sydoc"]
    assert proc_ph == "?"
    assert client_ph == "?, ?"


# ---------- build_stat_query ----------


def test_build_stat_query_returns_row(app, monkeypatch):
    fake_source = SimpleNamespace(
        table="Workitems", export_column="Status,Date", extra_condition="WHERE foo=1"
    )
    captured = {}

    def fake_sources_for(client, processes=None):
        captured["client"] = client
        captured["processes"] = processes
        return [fake_source]

    monkeypatch.setattr(ph_mod.mapping_config, "sources_for", fake_sources_for)

    with app.app_context():
        result = build_stat_query("Invoices")

    assert result == ("Workitems", "Status,Date", "WHERE foo=1")
    assert captured == {"client": None, "processes": ["Invoices"]}


def test_build_stat_query_returns_none_on_db_error(app, monkeypatch):
    # mapping_config.sources_for degrades to [] on a registry load failure
    # (see mapping_config.registry()'s failure contract) -- build_stat_query
    # must return None in that case, matching the legacy except-block.
    monkeypatch.setattr(ph_mod.mapping_config, "sources_for", lambda client, processes=None: [])

    with app.app_context():
        result = build_stat_query("Invoices")
    assert result is None
