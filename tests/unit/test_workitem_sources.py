"""Pure merge/pagination + source-normalization tests (no live DB)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import nx_lib.workitem_sources as ws
from nx_lib.workitem_sources import (
    PostgresSource,
    SqlServerSource,
    WorkitemFilter,
    merge_sorted_rows,
)


def _row(wid, mins, client="default"):
    return {
        "modifiedat": datetime(2026, 6, 16, 9, mins, 0),
        "workitemid": wid,
        "status": "Ready",
        "current_stage": "Extraction",
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
    assert rows[0]["client"] == "default"
    assert "priority" not in rows[0]
    assert "tags" not in rows[0]


def test_postgres_source_builds_pg_sql(app):
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
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows, total = src.list_workitems(_mk_filter(), offset=0, limit=40)

    assert total == 2
    assert rows[0]["workitemid"] == 1001
    assert rows[0]["client"] == "ms02"
    assert "priority" not in rows[0]
    assert "tags" not in rows[0]
    # Verify the executed SQL used %s placeholders (psycopg2), not ?.
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "%s" in executed_sql
    assert "?" not in executed_sql


def _captured_sql(src, filt):
    """Run list_workitems against a mock cursor and return all executed SQL."""
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = [0]
    fake_cur.fetchall.return_value = []
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    with patch.object(src, "engine") as eng:
        eng.raw_connection.return_value = fake_conn
        src.list_workitems(filt, offset=0, limit=40)
    return " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list), fake_cur


def test_status_in_progress_filter_covers_all_non_terminal_codes(app):
    """The display CASE maps every status that is not 0/5 to 'In Progress'
    (live INT has codes 3 and 4 in real use), but the status filter compared
    `Status = 1`, so 96 rows shown as 'In Progress' could not be found by
    filtering for it. Both sources must filter the whole bucket."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        f = _mk_filter()
        f.status_code = 1
        with app.app_context():
            sql, _ = _captured_sql(src, f)
        norm = sql.replace('"', "").replace(" ", "").lower()
        assert "statusnotin(0,5)" in norm, f"{type(src).__name__}: {sql}"


def test_search_id_is_exact_match_not_substring(app):
    """Searching workitem 371 must not also return 1371/3716/16371."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        f = _mk_filter()
        f.search_id = "371"
        with app.app_context():
            sql, cur = _captured_sql(src, f)
        params = [c.args[1] for c in cur.execute.call_args_list if len(c.args) > 1]
        flat = [p for group in params for p in (group if isinstance(group, list) else [group])]
        assert "%371%" not in flat, f"{type(src).__name__} still binds a LIKE pattern: {flat}"
        assert "371" in flat, f"{type(src).__name__} lost the search term: {flat}"


def test_empty_process_scope_yields_no_rows_without_sql_error(app):
    """A user with zero process permissions produced `IN ()` -- a syntax error
    in both dialects -- so both sources errored and the page showed a degraded
    banner instead of a clean empty state."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        f = WorkitemFilter(process_names=[], client_names=[], activity_ignore_csv="'Ignore'")
        with app.app_context():
            rows, total = (None, None)
            fake_cur = MagicMock()
            fake_cur.fetchone.return_value = [0]
            fake_cur.fetchall.return_value = []
            fake_conn = MagicMock()
            fake_conn.cursor.return_value = fake_cur
            with patch.object(src, "engine") as eng:
                eng.raw_connection.return_value = fake_conn
                rows, total = src.list_workitems(f, offset=0, limit=40)
            sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
        assert rows == [] and total == 0, f"{type(src).__name__}: {rows}, {total}"
        assert "in ()" not in sql.lower().replace("in  (", "in ("), sql


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
    monkeypatch.setattr(ws, "get_source_for_workitem", lambda wid, client_hint=None: "default")
    with app.app_context():
        from nx_lib.workitem_sources import CLIENTS

        assert ws.get_domain_for_workitem(5) == CLIENTS["default"].octo_domain


def test_get_source_for_workitem_honours_client_hint_over_probe(app, monkeypatch):
    """Ids collide across clients (1216 of them on INT), so the client of the
    row the user actually clicked wins over probing -- which cannot tell two
    identically numbered workitems apart."""
    monkeypatch.setattr(ws, "_cache_lookup", lambda wid: "ms02")

    def _must_not_probe():
        raise AssertionError("probe must not run when a valid client hint is given")

    monkeypatch.setattr(ws, "active_sources", _must_not_probe)
    with app.app_context():
        assert ws.get_source_for_workitem(217, client_hint="default") == "default"


def test_get_source_for_workitem_probes_default_source_too(app, monkeypatch):
    """The default source used to be excluded from the probe, so a default+MS02
    collision looked like a single MS02 claim and was cached permanently."""
    probed = []

    class _Src:
        def __init__(self, code):
            self.code = code

        def has_workitem(self, wid):
            probed.append(self.code)
            return True

    monkeypatch.setattr(ws, "_cache_lookup", lambda wid: None)
    monkeypatch.setattr(ws, "active_sources", lambda: [_Src("default"), _Src("ms02")])
    stored = []
    monkeypatch.setattr(ws, "_cache_store", lambda wid, code: stored.append(code))
    with app.app_context():
        assert ws.get_source_for_workitem(217) == "default"  # ambiguous -> fail safe
    assert "default" in probed, probed
    assert stored == [], "an ambiguous id must not be cached"


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


# ---------------- dashboard source-awareness (Task 14) ---------------- #


def test_sqlserver_recent_rows_normalizes(app):
    data_row = MagicMock(
        ID=7,
        ModifiedAt=datetime(2026, 6, 16, 9, 15, 0),
        ProcessName="Invoices",
    )
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = [data_row]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows = src.recent_rows(["Invoices"], ["Privera"], "'Ignore'", top=3)

    assert rows == [
        {
            "id": 7,
            "modifiedat": datetime(2026, 6, 16, 9, 15, 0),
            "process": "Invoices",
            "client": "default",
        }
    ]
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "?" in executed_sql
    assert "%s" not in executed_sql


def test_sqlserver_recent_rows_omits_not_in_when_ignore_csv_empty(app):
    """Empty ActivityInstancesToIgnore table (the normal default-client state)
    yields activity_ignore_csv="" -- must not render `NOT IN ()`, a SQL syntax
    error that was previously swallowed and silently emptied Recent Validations."""
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = []
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows = src.recent_rows(["Invoices"], ["Privera"], "", top=3)

    assert rows == []
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "NOT IN" not in executed_sql.upper()


def test_sqlserver_recent_rows_omits_not_in_when_ignore_csv_none(app):
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = []
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows = src.recent_rows(["Invoices"], ["Privera"], None, top=3)

    assert rows == []
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "NOT IN" not in executed_sql.upper()


def test_sqlserver_backlog_count(app):
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = [12]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        count = src.backlog_count(["Invoices"], ["Privera"])

    assert count == 12
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "C+A" in executed_sql


def test_postgres_recent_rows_uses_pg_sql(app):
    data_row = MagicMock(
        id=1001,
        modifiedat=datetime(2026, 6, 16, 9, 20, 0),
        process="Invoices",
    )
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = [data_row]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = PostgresSource(CLIENTS_code="ms02")
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows = src.recent_rows(["Invoices"], ["Privera"], "'Ignore'", top=3)

    assert rows[0]["id"] == 1001
    assert rows[0]["client"] == "ms02"
    assert rows[0]["process"] == "Invoices"
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "%s" in executed_sql
    assert '"t_WorkItems"' in executed_sql
    assert "?" not in executed_sql


def test_postgres_backlog_count(app):
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = [4]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = PostgresSource(CLIENTS_code="ms02")
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        count = src.backlog_count(["Invoices"], ["Privera"])

    assert count == 4
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "%s" in executed_sql
    assert '"t_WorkItems"' in executed_sql
    assert "?" not in executed_sql


def test_recent_activity_rows_merges_and_caps(app, monkeypatch):
    class Fake:
        def __init__(self, code, rows):
            self.code = code
            self._rows = rows

        def recent_rows(self, process_names, client_names, activity_ignore_csv, top=3):
            return self._rows

    f1 = Fake(
        "default",
        [
            {
                "id": 1,
                "modifiedat": datetime(2026, 6, 16, 9, 10),
                "process": "P",
                "client": "default",
            },
            {
                "id": 2,
                "modifiedat": datetime(2026, 6, 16, 9, 30),
                "process": "P",
                "client": "default",
            },
        ],
    )
    f2 = Fake(
        "ms02",
        [
            {
                "id": 1001,
                "modifiedat": datetime(2026, 6, 16, 9, 20),
                "process": "Q",
                "client": "ms02",
            },
        ],
    )
    monkeypatch.setattr(ws, "active_sources", lambda: [f1, f2])
    with app.app_context():
        out = ws.recent_activity_rows(["P"], ["C"], "'Ignore'", top=2)
    assert [r["id"] for r in out] == [2, 1001]  # newest first, capped to 2


def test_total_backlog_count_sums(app, monkeypatch):
    class Fake:
        def __init__(self, code, n):
            self.code = code
            self._n = n

        def backlog_count(self, process_names, client_names):
            return self._n

    monkeypatch.setattr(ws, "active_sources", lambda: [Fake("default", 3), Fake("ms02", 4)])
    with app.app_context():
        assert ws.total_backlog_count(["P"], ["C"]) == 7


# ---------------- MS02 doc-field resolver (columnar) ---------------- #

# (table, id_col, field_col, time_filter) -- the spec shape the resolver consumes.
_SPEC = ('public."DossierStatistik"', "WorkItemID", "DossierBarcode", None)
_PID_SPEC = ('public."DossierStatistik"', "WorkItemID", "DossierNummer", None)


def test_ms02_id_column_parses_join_condition():
    assert ws._ms02_id_column("d.WorkItemID = twi.id", "d") == "WorkItemID"
    assert ws._ms02_id_column("twi.id = d.WorkItemID", "d") == "WorkItemID"
    assert ws._ms02_id_column("", "d") is None
    assert ws._ms02_id_column("x.Foo = twi.id", "d") is None  # alias mismatch


def test_ms02_columnar_sql_quotes_identifiers_and_uses_ilike():
    sql = ws._ms02_columnar_sql(_SPEC[0], "WorkItemID", "DossierBarcode", None, "ILIKE %s")
    assert sql == (
        'SELECT DISTINCT "WorkItemID" FROM public."DossierStatistik" '
        'WHERE "DossierBarcode"::text ILIKE %s'
    )


def test_ms02_columnar_sql_appends_time_filter():
    sql = ws._ms02_columnar_sql(_SPEC[0], "WorkItemID", "DossierBarcode", "x > now()", "= ANY(%s)")
    assert sql.endswith("AND x > now()")
    assert '"DossierBarcode"::text = ANY(%s)' in sql


def test_ms02_columnar_sql_rejects_unsafe_identifier(app):
    with app.app_context():
        assert ws._ms02_columnar_sql(_SPEC[0], "WorkItemID", 'bad"; DROP', None, "ILIKE %s") is None


def test_resolve_ms02_docfield_ids_engine_none_returns_none():
    assert ws.resolve_ms02_docfield_ids(None, [([_SPEC], "123")]) is None


def test_resolve_ms02_docfield_ids_empty_pairs_returns_none():
    assert ws.resolve_ms02_docfield_ids(MagicMock(), []) is None


def test_resolve_ms02_docfield_ids_intersects_pairs(app):
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    # First docfield matches {1,2,3}; second {2,3,4}; AND => {2,3}.
    cur.fetchall.side_effect = [[(1,), (2,), (3,)], [(2,), (3,), (4,)]]
    with app.app_context():
        result = ws.resolve_ms02_docfield_ids(engine, [([_SPEC], "1"), ([_SPEC], "x")])
    assert result == {2, 3}


def test_resolve_ms02_docfield_ids_ors_specs_within_field(app):
    # Two specs for ONE docfield are OR'd (union), not intersected.
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.side_effect = [[(1,)], [(2,)]]
    spec2 = ('public."BatchStatistik"', "WorkItemID", "BatchName", None)
    with app.app_context():
        result = ws.resolve_ms02_docfield_ids(engine, [([_SPEC, spec2], "1")])
    assert result == {1, 2}


def test_resolve_ms02_docfield_ids_coerces_ids_to_int(app):
    # Statistik WorkItemID is varchar; the allow-set must be ints (twi."ID").
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.side_effect = [[("1",), ("2",), ("bad",)]]  # 'bad' dropped
    with app.app_context():
        result = ws.resolve_ms02_docfield_ids(engine, [([_SPEC], "1")])
    assert result == {1, 2}


def test_resolve_ms02_docfield_ids_empty_match_forces_empty(app):
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.side_effect = [[]]  # a docfield matched nothing
    with app.app_context():
        result = ws.resolve_ms02_docfield_ids(engine, [([_SPEC], "nope")])
    assert result == set()


def test_resolve_ms02_docfield_ids_query_error_returns_none(app):
    engine = MagicMock()
    engine.raw_connection.side_effect = Exception("boom")
    with app.app_context():
        assert ws.resolve_ms02_docfield_ids(engine, [([_SPEC], "1")]) is None


def test_build_where_emits_any_for_populated_ms02_docfield_ids(app):
    src = ws.PostgresSource.__new__(ws.PostgresSource)  # skip __init__
    src.code = "ms02"
    src.engine = None
    filt = ws.WorkitemFilter(
        process_names=["p"],
        client_names=["c"],
        activity_ignore_csv="",
        ms02_docfield_ids={10, 20},
    )
    with app.app_context():
        where, params = src._build_where(filt)
    assert 'twi."ID" = ANY(%s)' in where
    assert "t_DocumentIndexes" not in where
    assert "EXISTS" not in where
    assert any(isinstance(p, list) and set(p) == {10, 20} for p in params)


def test_build_where_empty_ms02_docfield_ids_forces_no_rows(app):
    src = ws.PostgresSource.__new__(ws.PostgresSource)
    src.code = "ms02"
    src.engine = None
    filt = ws.WorkitemFilter(
        process_names=["p"],
        client_names=["c"],
        activity_ignore_csv="",
        ms02_docfield_ids=set(),
    )
    with app.app_context():
        where, _ = src._build_where(filt)
    assert "1=0" in where
    assert "t_DocumentIndexes" not in where


def test_build_where_none_ms02_docfield_ids_adds_no_clause(app):
    src = ws.PostgresSource.__new__(ws.PostgresSource)
    src.code = "ms02"
    src.engine = None
    filt = ws.WorkitemFilter(
        process_names=["p"],
        client_names=["c"],
        activity_ignore_csv="",
        ms02_docfield_ids=None,
    )
    with app.app_context():
        where, _ = src._build_where(filt)
    assert "t_DocumentIndexes" not in where
    assert "ANY(%s)" not in where


def test_build_where_ignores_raw_docfields_for_ms02(app):
    # Raw docfields/docvalues must NO LONGER produce an in-query EXISTS.
    src = ws.PostgresSource.__new__(ws.PostgresSource)
    src.code = "ms02"
    src.engine = None
    filt = ws.WorkitemFilter(
        process_names=["p"],
        client_names=["c"],
        activity_ignore_csv="",
        docfields=["barcode"],
        docvalues=["123"],
    )
    with app.app_context():
        where, _ = src._build_where(filt)
    assert "t_DocumentIndexes" not in where
    assert "EXISTS" not in where


def test_resolve_ms02_docfield_ids_later_empty_forces_empty(app):
    # First docfield populates the result; a LATER docfield matching nothing must
    # still short-circuit the WHOLE result to empty (mid-loop `return set()`).
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.side_effect = [[(1,), (2,)], []]
    with app.app_context():
        result = ws.resolve_ms02_docfield_ids(engine, [([_SPEC], "1"), ([_SPEC], "nope")])
    assert result == set()


def test_resolve_ms02_pid_ids_engine_none_returns_none():
    assert ws.resolve_ms02_pid_ids(None, [_PID_SPEC], ["1", "2"]) is None


def test_resolve_ms02_pid_ids_no_specs_returns_none(app):
    with app.app_context():
        assert ws.resolve_ms02_pid_ids(MagicMock(), [], ["1"]) is None


def test_resolve_ms02_pid_ids_empty_values_returns_none(app):
    with app.app_context():
        assert ws.resolve_ms02_pid_ids(MagicMock(), [_PID_SPEC], []) is None


def test_resolve_ms02_pid_ids_unions_matches(app):
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.return_value = [(10,), (20,), (30,)]
    with app.app_context():
        result = ws.resolve_ms02_pid_ids(engine, [_PID_SPEC], ["100", "200"])
    assert result == {10, 20, 30}
    # the PID list is bound to "<pid_col>"::text = ANY(%s)
    args = cur.execute.call_args[0]
    assert sorted(args[1][0]) == ["100", "200"]


def test_resolve_ms02_pid_ids_no_match_returns_empty_set(app):
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.return_value = []
    with app.app_context():
        assert ws.resolve_ms02_pid_ids(engine, [_PID_SPEC], ["nope"]) == set()


def test_resolve_ms02_pid_ids_query_error_returns_none(app):
    engine = MagicMock()
    engine.raw_connection.side_effect = Exception("boom")
    with app.app_context():
        assert ws.resolve_ms02_pid_ids(engine, [_PID_SPEC], ["1"]) is None


# ---------------- resolve_ms02_pid_to_wids (per-PID mapping) ---------------- #


def test_resolve_ms02_pid_to_wids_returns_none_on_no_engine(app):
    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids

    with app.app_context():
        assert resolve_ms02_pid_to_wids(None, [("t", "id", "pid", None)], ["123"]) is None


def test_resolve_ms02_pid_to_wids_returns_none_on_no_specs(app):
    from unittest.mock import MagicMock

    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids

    with app.app_context():
        assert resolve_ms02_pid_to_wids(MagicMock(), [], ["123"]) is None


def test_resolve_ms02_pid_to_wids_returns_none_on_no_pids(app):
    from unittest.mock import MagicMock

    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids

    with app.app_context():
        assert resolve_ms02_pid_to_wids(MagicMock(), [("t", "id", "pid", None)], []) is None


def test_resolve_ms02_pid_to_wids_groups_by_pid(app):
    from unittest.mock import MagicMock

    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [("30111679", "100"), ("30111679", "200"), ("99999", "300")]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_engine = MagicMock()
    mock_engine.raw_connection.return_value = mock_conn

    with app.app_context():
        result = resolve_ms02_pid_to_wids(
            mock_engine,
            [("DossierStatistik", "WorkItemID", "DossierNummer", None)],
            ["30111679", "99999"],
        )
    assert result is not None
    assert set(result["30111679"]) == {100, 200}
    assert result["99999"] == [300]


def test_resolve_ms02_pid_to_wids_empty_dict_on_no_match(app):
    """Zero DB rows -> empty dict (not None)."""
    from unittest.mock import MagicMock

    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_engine = MagicMock()
    mock_engine.raw_connection.return_value = mock_conn

    with app.app_context():
        result = resolve_ms02_pid_to_wids(
            mock_engine,
            [("DossierStatistik", "WorkItemID", "DossierNummer", None)],
            ["NOTFOUND"],
        )
    assert result == {}


def test_resolve_ms02_wids_to_pids_maps_first_pid(app):
    from unittest.mock import MagicMock

    from nx_lib.workitem_sources import resolve_ms02_wids_to_pids

    cur = MagicMock()
    cur.fetchall.return_value = [(42, "100"), (43, "222"), (42, "999")]
    conn = MagicMock()
    conn.cursor.return_value = cur
    engine = MagicMock()
    engine.raw_connection.return_value = conn
    with app.app_context():
        result = resolve_ms02_wids_to_pids(
            engine, [("DossierStatistik", "WorkItemID", "DossierNummer", None)], [42, 43]
        )
    assert result[42] == "100"  # first pid per wid wins
    assert result[43] == "222"


def test_resolve_ms02_wids_to_pids_none_contract(app):
    from unittest.mock import MagicMock

    from nx_lib.workitem_sources import resolve_ms02_wids_to_pids

    with app.app_context():
        assert resolve_ms02_wids_to_pids(None, [("t", "ID", "PID", None)], [1]) is None
        assert resolve_ms02_wids_to_pids(MagicMock(), [], [1]) is None
        assert resolve_ms02_wids_to_pids(MagicMock(), [("t", "ID", "PID", None)], []) is None


def test_resolve_octo_wid_stage_returns_none_without_engine(app):
    with app.app_context():
        assert ws.resolve_octo_wid_stage(None, 42) == {
            "status": None,
            "current_stage": None,
        }


def test_resolve_octo_wid_stage_degrades_to_none_on_error(app):
    class Boom:
        def raw_connection(self):
            raise RuntimeError("octo down")

    with app.app_context():
        assert ws.resolve_octo_wid_stage(Boom(), 42) == {
            "status": None,
            "current_stage": None,
        }


def test_resolve_octo_wid_stage_maps_status_and_stage(app):
    from unittest.mock import MagicMock

    row = MagicMock(Status="In Progress", CurrentStage="Validation")
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = row
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    eng = MagicMock()
    eng.raw_connection.return_value = fake_conn
    with app.app_context():
        assert ws.resolve_octo_wid_stage(eng, 42) == {
            "status": "In Progress",
            "current_stage": "Validation",
        }
