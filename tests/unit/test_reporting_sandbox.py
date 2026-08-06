"""Unit tests for the Reporting live-SQL sandbox (security boundary)."""

import re
import time

import pytest

from nx_lib.reporting.sandbox import (
    SqlSandboxError,
    fetch_capped,
    humanize_sql_error,
    validate_select,
    wrap_with_cap,
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select Id, Name from dbo.SomeView where Name = 'x'",
        "WITH c AS (SELECT 1 AS n) SELECT n FROM c",
        "SELECT a FROM t1 UNION SELECT a FROM t2",
        "SELECT /* note */ 1 -- trailing comment",
        "SELECT sp_balance, sp_name FROM Salespersons",
        "SELECT 1 AS intolerance",
        "SELECT /* DROP TABLE x */ 1",
    ],
)
def test_accepts_read_only_selects(sql):
    assert validate_select(sql) == sql.strip()


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "TRUNCATE TABLE t",
        "ALTER TABLE t ADD c INT",
        "CREATE TABLE t (a INT)",
        "MERGE t USING s ON t.id = s.id WHEN MATCHED THEN DELETE",
        "EXEC sp_who",
        "SELECT * FROM t; DROP TABLE t",
        "SELECT 1) AS _q; DROP TABLE t --",
        "SELECT * INTO newt FROM t",
        "GRANT SELECT ON t TO public",
        "SELECT * FROM OPENROWSET('x','y','z')",
        "",
        "   ",
    ],
)
def test_rejects_non_read_only(sql):
    with pytest.raises(SqlSandboxError):
        validate_select(sql)


def test_too_long_rejected():
    with pytest.raises(SqlSandboxError) as ei:
        validate_select("SELECT " + ("1," * 12000) + "1")
    assert ei.value.rule == "too_long"


def test_error_carries_rule():
    with pytest.raises(SqlSandboxError) as ei:
        validate_select("DROP TABLE t")
    assert ei.value.rule in ("blocked_keyword", "forbidden_node", "not_select")


def test_wrap_with_cap_shape():
    out = wrap_with_cap("SELECT 1", 50000)
    assert out.startswith("SELECT TOP (50000) * FROM (")
    assert out.rstrip().endswith(") AS _q")


def test_wrap_with_cap_coerces_int():
    assert "TOP (10)" in wrap_with_cap("SELECT 1", "10")


# ---- Task 30 (D-CTE): WITH-rooted queries can't be wrapped as a derived table --
# `SELECT TOP (n) * FROM ( WITH ... ) AS _q` is invalid T-SQL — WITH cannot appear
# inside a derived-table subquery. wrap_with_cap() must pass CTE queries through
# unwrapped; the executor caps them fetch-side instead via fetch_capped().


def test_wrap_with_cap_passes_with_query_through_unwrapped():
    sql = "WITH q AS (SELECT 1 AS a) SELECT * FROM q"
    out = wrap_with_cap(sql, 100)
    assert out == sql
    assert "FROM ( WITH" not in out
    assert re.search(r"FROM\s*\(\s*WITH", out, re.IGNORECASE) is None


def test_wrap_with_cap_plain_select_still_gets_top_wrap():
    # (b) plain SELECTs are unaffected — same shape as before this fix.
    out = wrap_with_cap("SELECT 1", 25)
    assert out.startswith("SELECT TOP (25) * FROM (")
    assert out.rstrip().endswith(") AS _q")
    assert "SELECT 1" in out


def test_wrap_with_cap_detects_with_after_line_comment():
    sql = "-- note\nWITH q AS (SELECT 1 AS a) SELECT * FROM q"
    out = wrap_with_cap(sql, 10)
    assert out == sql


def test_wrap_with_cap_detects_with_after_block_comment():
    sql = "/* note */\nWITH q AS (SELECT 1 AS a) SELECT * FROM q"
    out = wrap_with_cap(sql, 10)
    assert out == sql


def test_wrap_with_cap_detects_with_after_mixed_comments():
    sql = "/* a */ -- b\n  WITH q AS (SELECT 1 AS a) SELECT * FROM q"
    out = wrap_with_cap(sql, 10)
    assert out == sql


def test_wrap_with_cap_detects_with_after_leading_semicolon():
    # `;WITH ...` is idiomatic T-SQL style (WITH must start a batch or
    # follow a semicolon-terminated statement) — sqlglot parses it as a
    # single valid Select, so it reaches wrap_with_cap() with the `;`
    # still attached. Must be passed through unwrapped, same as bare WITH.
    sql = ";WITH q AS (SELECT 1 AS a) SELECT * FROM q"
    assert validate_select(sql) == sql
    out = wrap_with_cap(sql, 10)
    assert out == sql
    assert re.search(r"FROM\s*\(\s*;?\s*WITH", out, re.IGNORECASE) is None


# ---- Issue #129: top-level ORDER BY can't be wrapped as a derived table -----
# `SELECT TOP (n) * FROM ( SELECT ... ORDER BY x ) AS _q` fails on SQL Server
# (error 1033: ORDER BY invalid in derived tables without TOP/OFFSET/FOR XML),
# yet validate_select() rightly accepts the statement — validate and run
# disagreed. wrap_with_cap() must pass ORDER-BY-rooted queries through
# unwrapped, same as the WITH path; fetch_capped() enforces the cap instead.


def test_wrap_with_cap_passes_trailing_order_by_through_unwrapped():
    sql = "SELECT Process, COUNT(*) AS cnt FROM dbo.T GROUP BY Process ORDER BY cnt DESC"
    assert validate_select(sql) == sql
    assert wrap_with_cap(sql, 100) == sql


def test_wrap_with_cap_passes_union_trailing_order_by_through_unwrapped():
    # sqlglot parks a set-operation's trailing ORDER BY on the rightmost
    # branch, not the Union node — detection must look there.
    sql = "SELECT a FROM t1 UNION ALL SELECT a FROM t2 ORDER BY a"
    assert wrap_with_cap(sql, 100) == sql


def test_wrap_with_cap_passes_parenthesized_order_by_through_unwrapped():
    sql = "(SELECT a FROM t ORDER BY a)"
    assert wrap_with_cap(sql, 10) == sql


def test_wrap_with_cap_order_by_with_own_top_passes_unwrapped():
    # Has its own TOP so the wrap used to be legal — but unwrapped is legal
    # too and preserves the user's ordering in the visible result.
    sql = "SELECT TOP 5 a FROM t ORDER BY a"
    assert wrap_with_cap(sql, 10) == sql


def test_wrap_with_cap_inner_order_by_still_wraps():
    # ORDER BY confined to the user's own derived table (with TOP) is legal
    # inside our wrapper — must still get the SQL-side cap.
    sql = "SELECT * FROM (SELECT TOP 5 a FROM t ORDER BY a) AS s"
    out = wrap_with_cap(sql, 25)
    assert out.startswith("SELECT TOP (25) * FROM (")


def test_wrap_with_cap_within_group_order_by_still_wraps():
    # WITHIN GROUP (ORDER BY ...) is not a statement-level ORDER BY — the
    # PERCENTILE_CONT shape from the eval must keep its SQL-side cap.
    sql = (
        "SELECT DISTINCT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v) "
        "OVER (PARTITION BY p) AS m FROM t"
    )
    out = wrap_with_cap(sql, 25)
    assert out.startswith("SELECT TOP (25) * FROM (")


def test_fetch_capped_flags_truncation_for_unwrapped_order_by_query():
    sql = "SELECT a FROM t ORDER BY a"
    assert wrap_with_cap(sql, 5) == sql
    cur = _FakeCursor(rows=[[i] for i in range(9)])
    rows, truncated = fetch_capped(cur, 5)
    assert len(rows) == 5
    assert truncated is True


class _FakeCursor:
    """Duck-typed pyodbc-style cursor for exercising fetch_capped() DB-free."""

    def __init__(self, rows):
        self._rows = list(rows)

    def fetchmany(self, n):
        batch, self._rows = self._rows[:n], self._rows[n:]
        return batch


def test_fetch_capped_flags_truncation_for_unwrapped_with_query():
    # (c) Executor-level: a WITH query has no SQL-side TOP cap once wrap_with_cap
    # passes it through unwrapped, so fetch_capped() is the only enforcement —
    # it must still return at most `cap` rows and flag the truncation.
    sql = "WITH q AS (SELECT n FROM t) SELECT n FROM q"
    assert wrap_with_cap(sql, 5) == sql
    cur = _FakeCursor([(i,) for i in range(12)])
    rows, truncated = fetch_capped(cur, 5)
    assert len(rows) == 5
    assert truncated is True


def test_fetch_capped_no_truncation_when_under_cap():
    cur = _FakeCursor([(1,), (2,)])
    rows, truncated = fetch_capped(cur, 5)
    assert rows == [[1], [2]]
    assert truncated is False


def test_fetch_capped_exact_cap_count_is_not_flagged_truncated():
    # The precise +1-row probe must NOT false-positive when the real result
    # set is exactly `cap` rows (no more) — unlike the old len(rows) >= cap
    # heuristic this replaces.
    cur = _FakeCursor([(1,), (2,), (3,)])
    rows, truncated = fetch_capped(cur, 3)
    assert len(rows) == 3
    assert truncated is False


# ---- Task 54: blocklist scan ignores string-literal contents -------------
# `_BLOCKED_RE` used to scan comment-stripped text only, so a blocked word
# sitting inside a string value (WHERE note = 'update log') tripped it as a
# false positive. The literal-stripper blanks literal contents (keeping the
# quote delimiters) before the blocklist scan runs, honoring T-SQL's
# doubled-quote ('') escape so an embedded quote isn't mistaken for the
# literal's end.


def test_accepts_blocked_keyword_inside_string_literal():
    sql = "SELECT * FROM t WHERE note = 'update log'"
    assert validate_select(sql) == sql


def test_rejects_real_update_even_alongside_a_literal():
    # Non-negotiable regression check: a real DML keyword outside any
    # literal must still be caught, even when a literal (containing an
    # unrelated word) is also present in the statement.
    sql = "UPDATE t SET note = 'select this' WHERE id = 1"
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "UPDATE"


def test_literal_doubled_quote_escape_is_not_mistaken_for_terminator():
    # 'it''s here...' -- the doubled quote is an escaped literal quote
    # character, not the end of the string. If the stripper mishandled it,
    # the text after the doubled quote would fall OUTSIDE the literal and
    # the word "update" below would trip the blocklist.
    sql = "SELECT * FROM t WHERE note = 'it''s here, update noted'"
    assert validate_select(sql) == sql


def test_unterminated_literal_does_not_hide_a_real_keyword():
    # Fail-safe check: a stray unclosed quote must not swallow the rest of
    # the query into a "literal" that gets blanked out. The stripper only
    # touches well-formed '...' spans, so a real keyword after an
    # unterminated quote still reaches the blocklist raw.
    sql = "SELECT * FROM t WHERE note = 'oops UPDATE t SET a = 1"
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "UPDATE"


def test_bracket_quoted_alias_cannot_hide_a_blocklisted_keyword():
    # Regression for the 7325afd bypass: a bracket-quoted identifier legally
    # contains a bare apostrophe (T-SQL allows it in [...] aliases, and
    # aliases are attacker-chosen). An apostrophe-blind literal stripper
    # pairs that lone quote with some LATER unrelated quote and blanks
    # everything in between -- including a real OPENROWSET call -- out of
    # the blocklist scan. sqlglot's AST gate does not independently reject
    # OPENROWSET/OPENQUERY/OPENDATASOURCE (they parse as a plain exp.Select
    # with an Anonymous function, no forbidden node), so the blocklist is
    # the sole defense for this keyword family and must not be bypassable.
    sql = (
        "SELECT * FROM sys.objects AS [a'b], "
        "OPENROWSET('SQLNCLI11','Server=evil;','SELECT 1') AS q"
    )
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "OPENROWSET"


# ---- Round 2: unified comment/quote tokenizer for the blocklist scan ------
# The 05fc6c8 (round-1) fix above closed the bare-apostrophe bracket bypass
# but left two related gaps of the same class, both letting OPENROWSET slip
# past the blocklist scan while sqlglot still parses it as a harmless
# exp.Select (no forbidden AST node):
#
#   Bypass A: the round-1 bracket alternative `\[[^\]]*\]` didn't know T-SQL
#   doubles an embedded `]` to escape it ([a]]b] is the identifier a]b) — it
#   stopped at the FIRST `]`, leaving a stray quote outside its consumed
#   span to open a phantom literal that swallowed real SQL after it.
#
#   Bypass B: _strip_comments() ran BEFORE any quote-awareness, so a `--` or
#   `/* */` marker sitting inside a string literal or a quoted identifier
#   (not a real comment in T-SQL) was blindly deleted anyway, corrupting
#   what the separate literal-stripping pass then saw.
#
# Fixed by scanning with one left-to-right tokenizer (_strip_for_scan) whose
# alternation covers comments and all quoted constructs together, so a
# marker that's actually inside a quoted construct is never mistaken for a
# real comment (and vice versa).


def test_bracket_escaped_close_cannot_hide_a_blocklisted_keyword():
    # Bypass A itself: [a]]'b] is the single identifier a]b (doubled `]]`
    # escapes a literal `]`). A bracket regex that stops at the first `]`
    # leaves the trailing `'` to open a phantom literal.
    sql = (
        "SELECT * FROM sys.objects AS [a]]'b], "
        "OPENROWSET('SQLNCLI11','Server=evil;','SELECT 1') AS q"
    )
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "OPENROWSET"


def test_double_quoted_stray_apostrophe_cannot_hide_a_blocklisted_keyword():
    # Double-quoted-identifier analogue of bypass A: "a""'b" is the
    # identifier a"'b (doubled `""` escapes a literal `"`), leaving a
    # trailing `'` that could open a phantom literal under a quote-unaware
    # scanner.
    sql = (
        'SELECT * FROM sys.objects AS "a""\'b", '
        "OPENROWSET('SQLNCLI11','Server=evil;','SELECT 1') AS q"
    )
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "OPENROWSET"


@pytest.mark.parametrize(
    "sql",
    [
        # Bypass B: `--` inside a single-quoted literal is not a comment.
        "SELECT 'a--b' AS x, * FROM OPENROWSET('P','S','SELECT 1') AS q",
        # `--` inside a bracket-quoted identifier is not a comment either.
        "SELECT 1 AS [a--b], * FROM OPENROWSET('P','S','SELECT 1') AS q",
        # ...nor inside a double-quoted identifier.
        "SELECT 1 AS \"a--b\", * FROM OPENROWSET('P','S','SELECT 1') AS q",
        # `/* */` variant: a block-comment marker inside a literal.
        "SELECT '/* a */' AS x, * FROM OPENROWSET('P','S','SELECT 1') AS q",
        # `/* */` variant inside a bracket identifier.
        "SELECT 1 AS [a/*b*/c], * FROM OPENROWSET('P','S','SELECT 1') AS q",
    ],
)
def test_comment_markers_inside_quoted_constructs_do_not_hide_openrowset(sql):
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "OPENROWSET"


def test_adjacent_bracket_identifiers_do_not_confuse_the_scan():
    # Two back-to-back bracket identifiers with nothing between them must
    # each be consumed as their own token, not merged/mismatched.
    sql = "SELECT * FROM t AS [a][b], OPENROWSET('P','S','SELECT 1') AS q"
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "OPENROWSET"


def test_doubled_bracket_escape_with_multiple_pairs_still_closes_correctly():
    # Several `]]` escapes in a row inside one identifier must still leave
    # the tokenizer able to find the real closing `]` and continue scanning
    # the rest of the statement correctly.
    sql = "SELECT * FROM t AS [ab]]cd]]ef], OPENROWSET('P','S','SELECT 1') AS q"
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "OPENROWSET"


def test_bracket_identifier_and_real_literal_do_not_mask_a_later_openrowset():
    # A bracket identifier and a genuine string literal (itself containing
    # an unrelated blocklisted word, which must NOT false-positive) both
    # precede the real breach -- confirms neither construct's stripping
    # leaks into the other's span and hides what comes after.
    sql = "SELECT * FROM t AS [x], 'update' AS y, OPENROWSET('P','S','SELECT 1') AS q"
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "OPENROWSET"


def test_cte_rooted_query_with_openrowset_still_blocked():
    sql = "WITH c AS (SELECT * FROM OPENROWSET('P','S','SELECT 1') AS q) SELECT * FROM c"
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "OPENROWSET"


def test_real_line_comment_containing_a_keyword_word_is_still_stripped():
    # A GENUINE comment (not inside any quoted construct) must still be
    # blanked, even when it contains a blocklisted word -- the fix must not
    # regress legitimate comment-stripping into over-strict rejection.
    sql = "SELECT 1 -- mentions OPENROWSET in a real comment, not code"
    assert validate_select(sql) == sql.strip()


def test_real_block_comment_containing_a_keyword_word_is_still_stripped():
    sql = "SELECT /* OPENROWSET mentioned here, not real code */ 1"
    assert validate_select(sql) == sql.strip()


def test_sandbox_error_token_carries_dynamic_part():
    # The view boundary translates rule-keyed messages; the dynamic bit
    # (keyword/construct name) must ride on the exception, not be regexed
    # back out of the English message.
    with pytest.raises(SqlSandboxError) as ei:
        validate_select("SELECT 1; DROP TABLE x")
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "DROP"


# ---- Task 6: humanize_sql_error (pyodbc/ODBC driver noise -> teaching text) --

# The exact live-audit pyodbc str(exception) text for a derived-table ORDER BY
# without TOP/OFFSET (SQL Server error 1033) — known and hinted in v1.
_ODBC_ORDER_BY_1033 = (
    "('42000', '[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
    "The ORDER BY clause is invalid in views, inline functions, derived "
    "tables, subqueries, and common table expressions, unless TOP, OFFSET "
    "or FOR XML is also specified. (1033) (SQLExecDirectW)')"
)

# An incorrect-syntax message (error 102) — cleaned like any ODBC error, but
# unmapped in v1 so no Hint: line is appended.
_ODBC_INCORRECT_SYNTAX_102 = (
    "('42000', \"[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
    "Incorrect syntax near 'FROM'. (102) (SQLExecDirectW)\")"
)


def test_humanize_sql_error_strips_noise_and_hints_known_code():
    out = humanize_sql_error(_ODBC_ORDER_BY_1033)
    assert "ORDER BY clause is invalid" in out
    assert "Hint:" in out
    assert "SQLExecDirectW" not in out
    assert "[Microsoft]" not in out


def test_humanize_sql_error_strips_noise_without_hint_for_unmapped_code():
    out = humanize_sql_error(_ODBC_INCORRECT_SYNTAX_102)
    assert "Incorrect syntax near 'FROM'" in out
    assert "Hint:" not in out
    assert "SQLExecDirectW" not in out
    assert "[Microsoft]" not in out


def test_humanize_sql_error_passes_through_non_odbc_message():
    msg = "unknown metric: 'x'"
    assert humanize_sql_error(msg) == msg


def test_humanize_appends_union_order_by_hint():
    msg = (
        "('42000', \"[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
        "Incorrect syntax near the keyword 'UNION'. (156) (SQLExecDirectW)\")"
    )
    out = humanize_sql_error(msg)
    assert "Incorrect syntax near the keyword 'UNION'." in out
    assert "Hint:" in out and "last branch" in out


def test_humanize_appends_ambiguous_column_hint():
    msg = (
        "('42000', \"[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
        "Ambiguous column name 'd'. (209) (SQLExecDirectW)\")"
    )
    out = humanize_sql_error(msg)
    assert "Ambiguous column name 'd'." in out
    assert "Hint:" in out and "alias" in out


# ---- Round 3: bare-CR comment terminator + bracket-regex ReDoS ------------
# A third review pass found the round-1/round-2 tokenizer above still had two
# gaps: (1) its comment alternative only stopped at LF, but real T-SQL also
# ends a `--` comment at a bare CR, so a `\r`-terminated comment kept hiding
# whatever followed (e.g. OPENROWSET) from the blocklist scan while SQL
# Server itself would execute it; (2) round 2's `]]`-escape-aware bracket
# alternative, while semantically correct, backtracks catastrophically on
# adversarial input -- tens of seconds of pure CPU on a single request, with
# no DB call involved so SQL_TIMEOUT_S never applies -- a DoS reachable by
# any authenticated user with reporting.sql.run + a target grant + the ack.


def test_bare_cr_after_line_comment_does_not_hide_openrowset():
    # `\r` (not `\n`) after `--` must still end the comment for scan
    # purposes, matching real T-SQL/SQL Server comment-termination rules --
    # otherwise everything after the `\r`, including OPENROWSET, is hidden
    # from the blocklist scan while the server would actually execute it.
    sql = (
        "SELECT 1 AS a -- harmless\r, * FROM "
        "OPENROWSET('SQLNCLI11','Server=evil;','SELECT 1') AS q"
    )
    with pytest.raises(SqlSandboxError) as ei:
        validate_select(sql)
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "OPENROWSET"


def test_wrap_with_cap_detects_with_after_bare_cr_comment():
    # Same CR-vs-LF comment-termination fix, applied to the separate
    # quote-unaware _strip_comments() helper wrap_with_cap() uses for its
    # leading-WITH shape check. Not a security bypass on its own (this only
    # runs on already-validated SQL) -- but a CR before a leading WITH must
    # still be recognized as a CTE-rooted query, or it gets incorrectly
    # TOP-wrapped (invalid T-SQL: WITH can't appear inside a derived table).
    sql = "-- note\rWITH q AS (SELECT 1 AS a) SELECT * FROM q"
    out = wrap_with_cap(sql, 10)
    assert out == sql


def test_bracket_regex_does_not_catastrophically_backtrack():
    # Regression guard for the round-2 ReDoS: a long run of adversarial
    # bracket/quote characters must resolve quickly, not take tens of
    # seconds of pure CPU. Threshold is intentionally generous (2s, ~10x the
    # ~200ms worst-case measured on dev hardware) to avoid flaking on slow
    # CI runners while still catching a regression back to catastrophic
    # backtracking (which measured 16-29s on the same shape of payload).
    payload = "SELECT 1 FROM t WHERE x=" + "['" * 9980
    assert len(payload) <= 20000  # stay under MAX_SQL_LEN so parsing is reached
    start = time.perf_counter()
    with pytest.raises(SqlSandboxError):
        validate_select(payload)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"bracket regex took {elapsed:.2f}s -- possible ReDoS regression"
