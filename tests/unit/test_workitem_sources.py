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
        client_process_pairs=[("Privera", "Invoices")],
        activity_ignore_map={("Privera", "Invoices"): frozenset({"Ignore"})},
    )


def test_sqlserver_source_normalizes_rows(app):
    # total rides along on every row via COUNT(*) OVER() -- no separate count
    # query for the non-empty-page path.
    data_row = MagicMock(
        ModifiedAt=datetime(2026, 6, 16, 9, 0, 0),
        WorkItemID=7,
        Status="Ready",
        CurrentStage="Extraction",
        TotalCount=3,
    )
    fake_cur = MagicMock()
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
    # Single query: COUNT(*) OVER() in the page query, no separate COUNT(*).
    assert fake_cur.execute.call_count == 1
    executed_sql = str(fake_cur.execute.call_args_list[0].args[0])
    assert "COUNT(*) OVER()" in executed_sql


def test_sqlserver_source_zero_rows_falls_back_to_count_query(app):
    """An empty page (offset past the end, or genuinely no matches) has no row
    for COUNT(*) OVER() to ride on -- must fall back to a plain COUNT query to
    tell the two cases apart, exactly like the old always-run count did."""
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = []
    fake_cur.fetchone.return_value = [5]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows, total = src.list_workitems(_mk_filter(), offset=1000, limit=40)

    assert rows == []
    assert total == 5
    assert fake_cur.execute.call_count == 2
    fallback_sql = str(fake_cur.execute.call_args_list[1].args[0])
    assert "COUNT(*)" in fallback_sql
    assert "OVER()" not in fallback_sql


def test_postgres_source_builds_pg_sql(app):
    # psycopg2 cursor returns namedtuple-ish rows; we normalize by attribute.
    # total rides along via COUNT(*) OVER() -- no separate count query.
    data_rows = [
        MagicMock(
            modifiedat=datetime(2026, 6, 16, 9, 5, 0),
            workitemid=1001,
            status="Ready",
            currentstage="Extraction",
            totalcount=2,
        ),
    ]
    fake_cur = MagicMock()
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
    # Single query: COUNT(*) OVER() in the page query, no separate COUNT(*).
    assert fake_cur.execute.call_count == 1
    assert "COUNT(*) OVER()" in executed_sql


def test_postgres_source_zero_rows_falls_back_to_count_query(app):
    """Same empty-page fallback contract as the SQL Server source."""
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = []
    fake_cur.fetchone.return_value = [4]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = PostgresSource(CLIENTS_code="ms02")
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows, total = src.list_workitems(_mk_filter(), offset=1000, limit=40)

    assert rows == []
    assert total == 4
    assert fake_cur.execute.call_count == 2
    fallback_sql = str(fake_cur.execute.call_args_list[1].args[0])
    assert "COUNT(*)" in fallback_sql
    assert "OVER()" not in fallback_sql


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


def test_deleted_workitems_hidden_unless_explicitly_filtered_for(app):
    """Status 2 (deleted) is hard-excluded from every default list. Asking for it
    by status code -- which the view only maps for holders of
    workitems.filter.status.deleted -- must DROP that exclusion, otherwise the
    two clauses contradict and the filter returns nothing."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        name = type(src).__name__
        f = _mk_filter()
        with app.app_context():
            sql, _ = _captured_sql(src, f)
        norm = sql.replace('"', "").replace(" ", "").lower()
        assert "status<>2" in norm, f"{name} stopped hiding deleted workitems: {sql}"

        f.status_code = 2
        with app.app_context():
            sql, cur = _captured_sql(src, f)
        norm = sql.replace('"', "").replace(" ", "").lower()
        assert "status<>2" not in norm, f"{name} contradicts the Deleted filter: {sql}"
        params = [c.args[1] for c in cur.execute.call_args_list if len(c.args) > 1]
        flat = [p for group in params for p in (group if isinstance(group, list) else [group])]
        assert 2 in flat, f"{name} lost the Deleted status code: {flat}"


def test_search_id_is_prefix_match_not_substring(app):
    """Searching workitem 371 must match 3710/37199 but not 1371/3716/16371 --
    prefix (LIKE '371%'), not substring (LIKE '%371%')."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        f = _mk_filter()
        f.search_id = "371"
        with app.app_context():
            sql, cur = _captured_sql(src, f)
        params = [c.args[1] for c in cur.execute.call_args_list if len(c.args) > 1]
        flat = [p for group in params for p in (group if isinstance(group, list) else [group])]
        assert "%371%" not in flat, f"{type(src).__name__} binds a full-substring pattern: {flat}"
        assert "371%" in flat, f"{type(src).__name__} lost the prefix pattern: {flat}"
        norm = sql.replace('"', "").lower()
        assert "like" in norm, f"{type(src).__name__} isn't using LIKE for the prefix match: {sql}"


def test_search_id_orders_by_relevance_shortest_id_first(app):
    """With a workitem-id search active, the closest match (fewest extra
    digits beyond the searched prefix) must sort first -- e.g. searching 11
    puts 11 above 110 above 1199. Without a search, plain recency (unrelated
    to id length) is unchanged."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        f = _mk_filter()
        f.search_id = "11"
        with app.app_context():
            sql, _ = _captured_sql(src, f)
        norm = sql.replace('"', "").lower()
        assert (
            "len(cast(workitemid" in norm or "length(workitemid" in norm
        ), f"{type(src).__name__} isn't ordering by id length for a search: {sql}"
        # The length-based ORDER BY must come before "OFFSET"/"LIMIT" (i.e. it's
        # the query's actual sort, not just present somewhere in the SQL text).
        order_pos = norm.find("order by")
        assert order_pos != -1 and "len" in norm[order_pos:], sql

        # No search -> unchanged plain-recency sort, no LEN()/LENGTH() at all.
        f2 = _mk_filter()
        with app.app_context():
            sql2, _ = _captured_sql(src, f2)
        norm2 = sql2.replace('"', "").lower()
        assert (
            "len(cast(workitemid" not in norm2 and "length(workitemid" not in norm2
        ), f"{type(src).__name__} orders by id length even without a search: {sql2}"


def test_merge_sorted_rows_search_id_ranks_shortest_id_first():
    """Across sources, a search-id merge must rank by id length (relevance)
    ahead of recency -- a short-id match from an OLDER row still beats a
    long-id match from a NEWER row."""
    a = [_row(1199, 30)]  # default: longer id, newer
    b = [_row(11, 10, "ms02")]  # ms02: shorter id (exact match), older
    merged = merge_sorted_rows([a, b], search_id="11")
    assert [r["workitemid"] for r in merged] == [11, 1199]

    # Without search_id, recency wins as before (regression guard).
    merged_no_search = merge_sorted_rows([a, b])
    assert [r["workitemid"] for r in merged_no_search] == [1199, 11]


def test_stage_filter_applied_after_latest_activity_dedup(app):
    """Stage is a derived value computed per activity row, but only the
    workitem's LATEST activity row should decide its stage (issue #147) -- a
    workitem with an earlier 'Extraction' row and a newer 'Validation' row
    must match `stage=Validation`, not both. Filtering inside the base WHERE
    (pre-dedup) would match on any row instead of just the latest, so the
    clause must be applied against the deduped rn=1 result."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        f = _mk_filter()
        f.stage = "Validation"
        with app.app_context():
            sql, cur = _captured_sql(src, f)
        norm = sql.replace('"', "").replace(" ", "").lower()
        assert "currentstage=" in norm, f"{type(src).__name__}: stage clause missing: {sql}"
        # The dedup CTE alias (LatestCTE / latest) must appear BEFORE the stage
        # clause is applied, both in the count and list queries.
        dedup_alias = "latestcte" if isinstance(src, SqlServerSource) else "latest"
        for call_args in cur.execute.call_args_list:
            stmt = str(call_args.args[0]).replace('"', "").replace(" ", "").lower()
            if "currentstage=" in stmt:
                assert (
                    dedup_alias in stmt
                ), f"{type(src).__name__}: stage filter not scoped to deduped rows: {stmt}"
        params = [c.args[1] for c in cur.execute.call_args_list if len(c.args) > 1]
        flat = [p for group in params for p in (group if isinstance(group, list) else [group])]
        assert "Validation" in flat, f"{type(src).__name__} lost the stage value: {flat}"


def test_no_stage_filter_omits_stage_clause(app):
    """stage=None (the default / 'All stages' option) must not constrain the
    query at all -- no WHERE CurrentStage clause, no extra bound param."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        sql, cur = (None, None)
        with app.app_context():
            sql, cur = _captured_sql(src, _mk_filter())
        norm = sql.replace('"', "").replace(" ", "").lower()
        assert "currentstage=" not in norm, f"{type(src).__name__}: {sql}"


def test_empty_process_scope_yields_no_rows_without_sql_error(app):
    """A user with zero process permissions produced `IN ()` -- a syntax error
    in both dialects -- so both sources errored and the page showed a degraded
    banner instead of a clean empty state."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        f = WorkitemFilter(client_process_pairs=[], activity_ignore_map={})
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


def test_pair_scope_authorizes_granted_pairs_only_not_cross_product(app):
    """A filter granted only (A, P1) and (B, P2) must build a WHERE whose
    params can only ever reconstruct those two pairs -- never the
    cross-product pairs (A, P2) / (B, P1) that two independent client/process
    IN-lists (ANDed together) would have authorized."""
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        f = WorkitemFilter(
            client_process_pairs=[("A", "P1"), ("B", "P2")],
            activity_ignore_map={},
        )
        with app.app_context():
            sql, cur = _captured_sql(src, f)

        assert (
            " or " in sql.lower()
        ), f"{type(src).__name__}: expected an OR-joined predicate: {sql}"

        count_call = cur.execute.call_args_list[0]
        count_params = count_call.args[1]
        pair_params = list(count_params[:4])
        built_pairs = list(zip(pair_params[0::2], pair_params[1::2], strict=True))
        assert built_pairs == [("A", "P1"), ("B", "P2")], f"{type(src).__name__}: {built_pairs}"
        assert ("A", "P2") not in built_pairs, f"{type(src).__name__} authorizes an ungranted pair"
        assert ("B", "P1") not in built_pairs, f"{type(src).__name__} authorizes an ungranted pair"


# ---- Phase-review fix: recent_rows/backlog_count had the SAME cross-product
# bug as list_workitems (fixed above by cc167e1), but independently -- these
# are different functions the dashboard's recent-activity feed and backlog
# KPI call directly, and were not touched by that commit. -----------------


def test_recent_rows_authorizes_granted_pairs_only_not_cross_product(app):
    """A caller granted only (A, P1) and (B, P2) must build a WHERE whose
    params can only ever reconstruct those two pairs -- never the
    cross-product pairs (A, P2) / (B, P1)."""
    pairs = [("A", "P1"), ("B", "P2")]
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        fake_cur = MagicMock()
        fake_cur.fetchall.return_value = []
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cur
        with patch.object(src, "engine") as eng, app.app_context():
            eng.raw_connection.return_value = fake_conn
            src.recent_rows(pairs, {}, top=3)

        call = fake_cur.execute.call_args_list[0]
        sql = str(call.args[0])
        params = list(call.args[1])
        assert " or " in sql.lower(), f"{type(src).__name__}: expected OR-joined predicate: {sql}"
        built_pairs = list(zip(params[0::2], params[1::2], strict=True))
        assert built_pairs == pairs, f"{type(src).__name__}: {built_pairs}"
        assert ("A", "P2") not in built_pairs, f"{type(src).__name__} authorizes an ungranted pair"
        assert ("B", "P1") not in built_pairs, f"{type(src).__name__} authorizes an ungranted pair"


def test_backlog_count_authorizes_granted_pairs_only_not_cross_product(app):
    """Same guarantee as above, for backlog_count -- the dashboard backlog
    KPI's query builder."""
    pairs = [("A", "P1"), ("B", "P2")]
    for src in (SqlServerSource(), PostgresSource(CLIENTS_code="ms02")):
        fake_cur = MagicMock()
        fake_cur.fetchone.return_value = [0]
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cur
        with patch.object(src, "engine") as eng, app.app_context():
            eng.raw_connection.return_value = fake_conn
            src.backlog_count(pairs)

        call = fake_cur.execute.call_args_list[0]
        sql = str(call.args[0])
        params = list(call.args[1])
        assert " or " in sql.lower(), f"{type(src).__name__}: expected OR-joined predicate: {sql}"
        built_pairs = list(zip(params[0::2], params[1::2], strict=True))
        assert built_pairs == pairs, f"{type(src).__name__}: {built_pairs}"
        assert ("A", "P2") not in built_pairs, f"{type(src).__name__} authorizes an ungranted pair"
        assert ("B", "P1") not in built_pairs, f"{type(src).__name__} authorizes an ungranted pair"


def test_recent_activity_rows_and_total_backlog_count_pass_pairs_through(app, monkeypatch):
    """The module-level merge/sum wrappers must forward the pairs shape
    verbatim to each source -- not re-split them back into independent
    client/process lists."""
    captured = {}

    class Fake:
        code = "default"

        def recent_rows(self, pairs, activity_ignore_map, top=3):
            captured["recent_rows_pairs"] = pairs
            return []

        def backlog_count(self, pairs):
            captured["backlog_count_pairs"] = pairs
            return 0

    monkeypatch.setattr(ws, "active_sources", lambda: [Fake()])
    pairs = [("A", "P1"), ("B", "P2")]
    with app.app_context():
        ws.recent_activity_rows(pairs, {}, top=3)
        ws.total_backlog_count(pairs)

    assert captured["recent_rows_pairs"] == pairs
    assert captured["backlog_count_pairs"] == pairs


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
    monkeypatch.setattr(ws, "non_default_source_instances", list)
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


def test_fetch_merged_page_warm_loop_does_not_blind_cache_colliding_id(app, monkeypatch):
    """A wid present in BOTH sources must be routed through the same
    collision fail-safe as get_source_for_workitem -- not pinned to whichever
    client's page happened to list it first during the cache-warm pass."""
    s1, s2 = SqlServerSource(), SqlServerSource()
    s2.code = "ms02"
    monkeypatch.setattr(ws, "active_sources", lambda: [s1, s2])
    # Both sources list -- and both sources claim -- id 1216 (the same
    # collision documented for the default/MS02 id spaces on INT).
    monkeypatch.setattr(
        s1, "list_workitems", lambda filt, offset, limit: ([_row(1216, 30, client="default")], 1)
    )
    monkeypatch.setattr(
        s2, "list_workitems", lambda filt, offset, limit: ([_row(1216, 20, client="ms02")], 1)
    )
    monkeypatch.setattr(s1, "has_workitem", lambda wid: True)
    monkeypatch.setattr(s2, "has_workitem", lambda wid: True)
    monkeypatch.setattr(ws, "_cache_lookup", lambda wid: None)
    store_calls = []
    monkeypatch.setattr(ws, "_cache_store_many", lambda pairs: store_calls.append(list(pairs)))

    with app.app_context():
        rows, total, degraded = ws.fetch_merged_page(_mk_filter(), offset=0, limit=40)

    assert [r["workitemid"] for r in rows] == [1216, 1216]  # both rows still render
    assert degraded == []
    assert store_calls == [], "colliding id must not be blind-cached by the batched warm loop"


def test_fetch_merged_page_warm_loop_caches_a_single_claimant_id(app, monkeypatch):
    """Companion to the collision test above: an unambiguous, non-colliding id
    (claimed by exactly one source) must still get warmed into the routing
    cache. Without this positive-path proof, a silently-broken warm loop (a
    swallowed exception, a bad refactor that no-ops the whole pass) would
    slip through -- the negative test alone can't distinguish "correctly
    refused to cache an ambiguous id" from "stopped caching anything at
    all". Also proves the fix for the N+1 warm-loop cost: get_source_for_workitem
    must reuse fetch_merged_page's already-built ``sources`` list (passed via
    its ``sources=`` param) rather than calling active_sources() again itself."""
    s1, s2 = SqlServerSource(), SqlServerSource()
    s2.code = "ms02"
    active_sources_calls = []

    def _active_sources():
        active_sources_calls.append(1)
        return [s1, s2]

    monkeypatch.setattr(ws, "active_sources", _active_sources)
    # id 5 is default-only, id 1001 is ms02-only -- neither collides.
    monkeypatch.setattr(
        s1, "list_workitems", lambda filt, offset, limit: ([_row(5, 30, client="default")], 1)
    )
    monkeypatch.setattr(
        s2, "list_workitems", lambda filt, offset, limit: ([_row(1001, 20, client="ms02")], 1)
    )
    monkeypatch.setattr(s1, "has_workitem", lambda wid: False)
    monkeypatch.setattr(s2, "has_workitem", lambda wid: wid == 1001)
    monkeypatch.setattr(ws, "_cache_lookup", lambda wid: None)
    store_calls = []
    monkeypatch.setattr(ws, "_cache_store_many", lambda pairs: store_calls.append(list(pairs)))

    with app.app_context():
        rows, total, degraded = ws.fetch_merged_page(_mk_filter(), offset=0, limit=40)

    assert [r["workitemid"] for r in rows] == [5, 1001]
    assert degraded == []
    # One batched call for the whole page, not one per row.
    assert store_calls == [[(1001, "ms02")]], "unambiguous id must be warmed into the cache"
    # Exactly one active_sources() call total (fetch_merged_page's own, at the
    # top of the function) -- get_source_for_workitem must not construct a
    # second fresh set of source instances per probed row.
    assert active_sources_calls == [1]


def test_fetch_merged_page_warm_loop_batches_all_uncached_rows_into_one_store_call(
    app, monkeypatch
):
    """N uncached, unambiguous rows on a page must produce exactly ONE
    _cache_store_many call carrying all N pairs -- not N per-row calls. This
    is the batching behaviour Task 2 exists to prove: the old code called
    get_source_for_workitem (and therefore _cache_store, one MERGE+commit)
    once per uncached row."""
    s1, s2 = SqlServerSource(), SqlServerSource()
    s2.code = "ms02"
    monkeypatch.setattr(ws, "active_sources", lambda: [s1, s2])
    ms02_ids = {1001, 1002, 1003, 1004}
    monkeypatch.setattr(
        s1,
        "list_workitems",
        lambda filt, offset, limit: ([_row(5, 30, client="default")], 1),
    )
    monkeypatch.setattr(
        s2,
        "list_workitems",
        lambda filt, offset, limit: (
            [_row(wid, 20 + i, client="ms02") for i, wid in enumerate(sorted(ms02_ids))],
            len(ms02_ids),
        ),
    )
    monkeypatch.setattr(s1, "has_workitem", lambda wid: False)
    monkeypatch.setattr(s2, "has_workitem", lambda wid: wid in ms02_ids)
    monkeypatch.setattr(ws, "_cache_lookup_many", lambda ids: {})
    store_calls = []
    monkeypatch.setattr(ws, "_cache_store_many", lambda pairs: store_calls.append(list(pairs)))

    with app.app_context():
        ws.fetch_merged_page(_mk_filter(), offset=0, limit=40)

    assert len(store_calls) == 1, "must batch every uncached row's cache write into one call"
    assert sorted(store_calls[0]) == [(wid, "ms02") for wid in sorted(ms02_ids)]


def test_cache_store_many_issues_one_merge_and_one_commit(app):
    """The batched upsert itself: N pairs -> exactly one cursor.execute (one
    multi-row MERGE) and one commit, not N."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    with (
        app.app_context(),
        patch.object(ws.engine_nexora_db, "raw_connection", return_value=mock_conn),
    ):
        ws._cache_store_many([(1, "ms02"), (2, "ms02"), (3, "ms02")])

    assert mock_cursor.execute.call_count == 1
    sql, params = mock_cursor.execute.call_args[0]
    assert sql.count("MERGE") == 1
    assert params == ["1", "ms02", "2", "ms02", "3", "ms02"]
    assert mock_conn.commit.call_count == 1
    mock_conn.close.assert_called_once()


def test_cache_store_many_drops_default_and_dedupes_by_id(app):
    """'default' pairs are never cached (matches _cache_store's contract) and
    a duplicate id collapses to its first occurrence before the MERGE runs,
    since a MERGE cannot target the same key twice in one USING clause."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    with (
        app.app_context(),
        patch.object(ws.engine_nexora_db, "raw_connection", return_value=mock_conn),
    ):
        ws._cache_store_many(
            [(1, "default"), (2, "ms02"), (2, "generali")]  # (2, "generali") ignored, dup id
        )

    assert mock_cursor.execute.call_count == 1
    sql, params = mock_cursor.execute.call_args[0]
    assert params == ["2", "ms02"]


def test_cache_store_many_empty_input_short_circuits(app):
    with app.app_context(), patch.object(ws.engine_nexora_db, "raw_connection") as mock_raw:
        ws._cache_store_many([])
    mock_raw.assert_not_called()


def test_cache_store_many_all_default_short_circuits(app):
    with app.app_context(), patch.object(ws.engine_nexora_db, "raw_connection") as mock_raw:
        ws._cache_store_many([(1, "default"), (2, "default")])
    mock_raw.assert_not_called()


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
        rows = src.recent_rows([("Privera", "Invoices")], {}, top=3)

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


def test_sqlserver_recent_rows_omits_not_in_when_ignore_map_empty(app):
    """Empty ActivityInstancesToIgnore table (the normal default-client state)
    yields activity_ignore_map={} -- must not render `NOT (...)`, and must not
    even reach `IN ()`, a SQL syntax error that was previously swallowed and
    silently emptied Recent Validations."""
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = []
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows = src.recent_rows([("Privera", "Invoices")], {}, top=3)

    assert rows == []
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "NOT" not in executed_sql.upper()


def test_sqlserver_recent_rows_omits_not_in_when_ignore_map_none(app):
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = []
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows = src.recent_rows([("Privera", "Invoices")], None, top=3)

    assert rows == []
    executed_sql = " ".join(str(c.args[0]) for c in fake_cur.execute.call_args_list)
    assert "NOT" not in executed_sql.upper()


def test_activity_ignore_predicate_scopes_by_process_not_globally(app):
    """The bug this fix closes: a rule configured for process P1 must never
    exclude a same-named activity on an unrelated process P2 in the same
    query -- the predicate must AND the activity match with a (client,
    process) match, not render one flat `NOT IN (...)` for every activity
    name across every process."""
    from nx_lib.workitem_sources import _activity_ignore_predicate

    ignore_map = {
        ("A", "P1"): frozenset({"Shared Name"}),
    }
    sql, params = _activity_ignore_predicate(
        ignore_map, "tp.ClientName", "tp.Name", "tai.ActivityInstanceName", "?"
    )
    assert sql is not None
    assert "tp.ClientName = ?" in sql
    assert "tp.Name = ?" in sql
    assert "tai.ActivityInstanceName IN (?)" in sql
    assert params == ["A", "P1", "Shared Name"]


def test_activity_ignore_predicate_combines_multiple_processes_with_or(app):
    from nx_lib.workitem_sources import _activity_ignore_predicate

    ignore_map = {
        ("A", "P1"): frozenset({"X"}),
        ("B", "P2"): frozenset({"Y", "Z"}),
    }
    sql, params = _activity_ignore_predicate(
        ignore_map, "tp.ClientName", "tp.Name", "tai.ActivityInstanceName", "?"
    )
    assert sql.startswith("NOT (") and sql.endswith(")")
    assert " OR " in sql
    # Every (client, process) key contributes exactly its own 2 identity
    # params plus one param per its own activity names -- never another
    # key's names.
    assert params.count("A") == 1
    assert params.count("B") == 1
    assert set(params) == {"A", "P1", "X", "B", "P2", "Y", "Z"}


def test_activity_ignore_predicate_empty_map_returns_no_clause(app):
    from nx_lib.workitem_sources import _activity_ignore_predicate

    sql, params = _activity_ignore_predicate(
        {}, "tp.ClientName", "tp.Name", "tai.ActivityInstanceName", "?"
    )
    assert sql is None
    assert params == []


def test_sqlserver_recent_rows_ignore_rule_does_not_leak_across_processes(app):
    """Live integration of the fix: a filter carrying an ignore rule for
    process P1 must not add any `tai.ActivityInstanceName` predicate scoped to
    P2 -- and the executed SQL's ignore clause is anchored to P1's identity,
    not floating free."""
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = []
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    ignore_map = {("Privera", "Invoices"): frozenset({"Deletion Marker"})}
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        rows = src.recent_rows([("Privera", "Invoices"), ("Compass", "SAP")], ignore_map, top=3)

    assert rows == []
    call = fake_cur.execute.call_args_list[0]
    executed_sql, params = call.args[0], call.args[1]
    assert "NOT (" in executed_sql
    assert "tai.ActivityInstanceName IN (?)" in executed_sql
    # The ignore rule's own (client, process) identity params are present --
    # scoping it to Privera/Invoices, not applied unconditionally.
    assert "Privera" in params and "Invoices" in params and "Deletion Marker" in params


def test_sqlserver_backlog_count(app):
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = [12]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    src = SqlServerSource()
    with patch.object(src, "engine") as eng, app.app_context():
        eng.raw_connection.return_value = fake_conn
        count = src.backlog_count([("Privera", "Invoices")])

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
        rows = src.recent_rows([("Privera", "Invoices")], {}, top=3)

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
        count = src.backlog_count([("Privera", "Invoices")])

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

        def recent_rows(self, pairs, activity_ignore_map, top=3):
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
        out = ws.recent_activity_rows([("C", "P")], {}, top=2)
    assert [r["id"] for r in out] == [2, 1001]  # newest first, capped to 2


def test_total_backlog_count_sums(app, monkeypatch):
    class Fake:
        def __init__(self, code, n):
            self.code = code
            self._n = n

        def backlog_count(self, pairs):
            return self._n

    monkeypatch.setattr(ws, "active_sources", lambda: [Fake("default", 3), Fake("ms02", 4)])
    with app.app_context():
        assert ws.total_backlog_count([("C", "P")]) == 7


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


def test_resolve_ms02_docfield_ids_or_combinator_unions(app):
    # (#148) 4-tuple entries carry (specs, value, op, comb); 'or' unions the
    # pair into the fold instead of intersecting.
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.side_effect = [[(1,)], [(2,)]]
    with app.app_context():
        result = ws.resolve_ms02_docfield_ids(
            engine,
            [([_SPEC], "a", "contains", "and"), ([_SPEC], "b", "contains", "or")],
        )
    assert result == {1, 2}


def test_resolve_ms02_docfield_ids_forced_empty_pair_ored_is_noop(app):
    # An empty-specs entry (field unmapped) contributes set(); OR'd it must not
    # shrink the result, AND'd it must zero it.
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.side_effect = [[(1,)]]
    with app.app_context():
        ored = ws.resolve_ms02_docfield_ids(
            engine, [([_SPEC], "a", "contains", "and"), ([], "b", "contains", "or")]
        )
    assert ored == {1}
    cur.fetchall.side_effect = [[(1,)]]
    with app.app_context():
        anded = ws.resolve_ms02_docfield_ids(
            engine, [([_SPEC], "a", "contains", "and"), ([], "b", "contains", "and")]
        )
    assert anded == set()


def test_resolve_ms02_docfield_ids_and_with_empty_pair_still_zeroes(app):
    # Regression for the removed early-return: pure-AND semantics unchanged --
    # a pair that matches nothing zeroes the whole result.
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.side_effect = [[(1,), (2,)], []]
    with app.app_context():
        result = ws.resolve_ms02_docfield_ids(engine, [([_SPEC], "a"), ([_SPEC], "b")])
    assert result == set()


def test_resolve_ms02_docfield_ids_eq_op_escapes_and_compares_literally(app):
    # (#148) 'eq' runs through ILIKE on the ESCAPED value: wildcards in the
    # user's value must compare literally, and 'neq' uses NOT ILIKE.
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.side_effect = [[(1,)], [(2,)]]
    with app.app_context():
        ws.resolve_ms02_docfield_ids(
            engine,
            [([_SPEC], "50%", "eq", "and"), ([_SPEC], "a_b", "neq", "and")],
        )
    (sql_eq, params_eq), _ = cur.execute.call_args_list[0]
    (sql_neq, params_neq), _ = cur.execute.call_args_list[1]
    assert "ILIKE %s" in sql_eq and "NOT ILIKE" not in sql_eq
    assert params_eq == ["50\\%"]
    assert "NOT ILIKE %s" in sql_neq
    assert params_neq == ["a\\_b"]


def test_build_where_emits_any_for_populated_ms02_docfield_ids(app):
    src = ws.PostgresSource.__new__(ws.PostgresSource)  # skip __init__
    src.code = "ms02"
    src.engine = None
    filt = ws.WorkitemFilter(
        client_process_pairs=[("c", "p")],
        activity_ignore_map={},
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
        client_process_pairs=[("c", "p")],
        activity_ignore_map={},
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
        client_process_pairs=[("c", "p")],
        activity_ignore_map={},
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
        client_process_pairs=[("c", "p")],
        activity_ignore_map={},
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


def test_resolve_ms02_pid_ids_mixed_batch_drops_only_unparseable(app):
    """(I2, #98 Task 12) A batch mixing valid ints with one unparseable value
    must keep the valid ones and drop only the bad value -- NOT skip the
    whole spec. Regression test for the docstring/code drift I4 flagged:
    the previous docstring wording ("if ANY PID fails to parse, that spec is
    skipped entirely") was already fixed in code but never had a direct
    test."""
    int_spec = ('public."DossierStatistik"', "WorkItemID", "DossierNummer", None, "int")
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.return_value = [(1,), (2,), (4,)]
    with app.app_context():
        result = ws.resolve_ms02_pid_ids(engine, [int_spec], ["1", "2", "not-a-number", "4"])
    assert result == {1, 2, 4}
    # only the parseable ints are bound -- the bad value never reaches SQL
    args = cur.execute.call_args[0]
    assert sorted(args[1][0]) == [1, 2, 4]


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


def test_resolve_ms02_wids_to_pids_casts_id_column_to_text(app):
    """Regression: the WHERE clause must cast the varchar id column ::text and
    bind a string-typed param list, mirroring resolve_ms02_pid_to_wids's
    WHERE-side cast convention -- otherwise Postgres raises an operator-type
    mismatch (varchar = ANY(int[])) on every call, silently killing the
    reverse 'In register' chip."""
    from unittest.mock import MagicMock

    from nx_lib.workitem_sources import resolve_ms02_wids_to_pids

    cur = MagicMock()
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur
    engine = MagicMock()
    engine.raw_connection.return_value = conn
    with app.app_context():
        resolve_ms02_wids_to_pids(
            engine, [("DossierStatistik", "WorkItemID", "DossierNummer", None)], [42, 43]
        )

    assert cur.execute.call_count == 1
    sql, params = cur.execute.call_args[0]
    assert 'WHERE "WorkItemID"::text = ANY(%s)' in sql
    bound_list = params[0]
    assert bound_list == ["42", "43"]
    assert all(isinstance(v, str) for v in bound_list)


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


def test_resolve_octo_wid_stage_pg_returns_none_without_engine(app):
    with app.app_context():
        assert ws._resolve_octo_wid_stage_pg(None, 42) == {
            "status": None,
            "current_stage": None,
        }


def test_resolve_octo_wid_stage_pg_degrades_to_none_on_error(app):
    class Boom:
        def raw_connection(self):
            raise RuntimeError("pg down")

    with app.app_context():
        assert ws._resolve_octo_wid_stage_pg(Boom(), 42) == {
            "status": None,
            "current_stage": None,
        }


def test_resolve_octo_wid_stage_pg_maps_status_and_stage(app):
    """Fake-cursor proof of the Postgres-dialect twin's own SQL + row mapping
    (the T-SQL twin's coverage above does not exercise this query at all --
    every existing prepared_documents test monkeypatches this function out).
    Postgres rows come back as plain tuples (no NamedTupleCursor), unlike
    resolve_octo_wid_stage's pyodbc .Status/.CurrentStage attribute access."""
    from unittest.mock import MagicMock

    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = ("In Progress", "Validation")
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    eng = MagicMock()
    eng.raw_connection.return_value = fake_conn
    with app.app_context():
        assert ws._resolve_octo_wid_stage_pg(eng, 42) == {
            "status": "In Progress",
            "current_stage": "Validation",
        }
    sql, params = fake_cur.execute.call_args[0]
    assert '"t_WorkItems"' in sql
    assert '"t_ActivityInstances"' in sql
    assert 'twi."ID" = %s' in sql
    assert params == [42]


def test_resolve_octo_wid_stage_pg_returns_empty_when_not_found(app):
    from unittest.mock import MagicMock

    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = None
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    eng = MagicMock()
    eng.raw_connection.return_value = fake_conn
    with app.app_context():
        assert ws._resolve_octo_wid_stage_pg(eng, 42) == {
            "status": None,
            "current_stage": None,
        }


def test_resolve_octo_wid_stage_pg_batch_returns_empty_without_engine(app):
    with app.app_context():
        assert ws._resolve_octo_wid_stage_pg_batch(None, [1, 2, 3]) == {}


def test_resolve_octo_wid_stage_pg_batch_returns_empty_with_no_valid_wids(app):
    from unittest.mock import MagicMock

    eng = MagicMock()
    with app.app_context():
        assert ws._resolve_octo_wid_stage_pg_batch(eng, ["not-an-int", None]) == {}
    # No round-trip attempted at all when there's nothing valid to ask for.
    eng.raw_connection.assert_not_called()


def test_resolve_octo_wid_stage_pg_batch_degrades_to_empty_on_error(app):
    class Boom:
        def raw_connection(self):
            raise RuntimeError("pg down")

    with app.app_context():
        assert ws._resolve_octo_wid_stage_pg_batch(Boom(), [1, 2]) == {}


def test_resolve_octo_wid_stage_pg_batch_issues_one_query_for_many_wids(app):
    """N wids -> exactly ONE execute() call (ANY(%s) array param), not N --
    this is the fix for the prepared-documents page's stage N+1. Same SQL
    vocabulary/column mapping as the single-wid twin, plus the wid column."""
    from unittest.mock import MagicMock

    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = [
        (42, "In Progress", "Validation"),
        (43, "Done", "Delivery"),
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    eng = MagicMock()
    eng.raw_connection.return_value = fake_conn

    with app.app_context():
        result = ws._resolve_octo_wid_stage_pg_batch(eng, [42, 43, 44])

    assert fake_cur.execute.call_count == 1
    sql, params = fake_cur.execute.call_args[0]
    assert '"t_WorkItems"' in sql
    assert '"t_ActivityInstances"' in sql
    assert "= ANY(%s)" in sql
    assert params == [[42, 43, 44]]
    # wid 44 had no matching row -- simply absent from the result, exactly
    # like the single-wid resolver returning its empty stage for a miss.
    assert result == {
        42: {"status": "In Progress", "current_stage": "Validation"},
        43: {"status": "Done", "current_stage": "Delivery"},
    }
    assert 44 not in result


def test_cache_lookup_many_issues_one_query_and_maps_hits(app):
    """Batched lookup for multiple ids does exactly ONE query (per <=1000 id
    chunk) and returns unambiguous hits keyed by id string."""
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = [("1", "ms02"), ("2", "generali")]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    eng = MagicMock()
    eng.raw_connection.return_value = fake_conn
    with app.app_context(), patch("nx_lib.workitem_sources.engine_nexora_db", eng):
        result = ws._cache_lookup_many(["1", "2", "3"])
    assert result == {"1": "ms02", "2": "generali"}
    assert fake_cur.execute.call_count == 1


def test_cache_lookup_many_omits_ambiguous_id(app):
    """An id with two cached rows (compound-PK collision) is left out of the
    map entirely -- the caller must re-probe it, never guess."""
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = [("1", "ms02"), ("1", "generali"), ("2", "ms02")]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    eng = MagicMock()
    eng.raw_connection.return_value = fake_conn
    with app.app_context(), patch("nx_lib.workitem_sources.engine_nexora_db", eng):
        result = ws._cache_lookup_many(["1", "2"])
    assert result == {"2": "ms02"}
    assert "1" not in result


def test_cache_lookup_many_empty_input_short_circuits():
    assert ws._cache_lookup_many([]) == {}


def test_cache_lookup_returns_none_and_logs_when_ambiguous(app):
    """_cache_lookup mirrors get_source_for_workitem's collision fail-safe:
    >1 row for a single id -> None (+ error log), not an arbitrary pick."""
    fake_cur = MagicMock()
    fake_cur.fetchall.return_value = [("ms02",), ("generali",)]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    eng = MagicMock()
    eng.raw_connection.return_value = fake_conn
    with (
        app.app_context(),
        patch("nx_lib.workitem_sources.engine_nexora_db", eng),
        patch.object(ws.current_app.logger, "error") as mock_log,
    ):
        result = ws._cache_lookup("42")
    assert result is None
    assert mock_log.called
