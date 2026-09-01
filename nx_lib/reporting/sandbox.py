"""Live read-only SQL sandbox for Reporting Phase 2 (security boundary).

Pure and DB-free: validates that a user-supplied string is a single read-only
SELECT (or WITH ... / set-operation) and wraps it with a row cap — plain SELECTs
get a `SELECT TOP (n) * FROM (...) AS _q` wrap; WITH-rooted queries and queries
with a top-level ORDER BY pass through unwrapped, since neither construct is
legal inside that derived-table subquery (issue #129 for ORDER BY), and
fetch_capped() enforces the cap fetch-side instead (D-CTE). fetch_capped() itself
only calls .fetchmany() on whatever cursor-like object it is given, so it stays
unit-testable without a real DB connection. The view layer runs the result on a
dedicated db_datareader-only engine with a statement timeout and audits every
execution. The sqlglot AST gate is the authority; the keyword blocklist is a
backup.
"""

import re

import sqlglot
from sqlglot import exp

MAX_SQL_LEN = 20000

# Backup keyword blocklist (word-boundary, case-insensitive, comment- and
# literal-stripped).
_BLOCKED_WORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "EXEC",
    "EXECUTE",
    "INTO",
    "BACKUP",
    "RESTORE",
    "SHUTDOWN",
    "OPENROWSET",
    "OPENQUERY",
    "OPENDATASOURCE",
)
_BLOCKED_RE = re.compile(r"\b(" + "|".join(_BLOCKED_WORDS) + r")\b", re.IGNORECASE)

# LIMIT parses under sqlglot's lenient tsql dialect into the SAME AST node as
# TOP, so it passes the AST gate but fails on the real SQL Server. Textual check
# is the only reliable reject. ponytail: matches a bare column alias named
# "limit" too — bracket-quote it ([limit]) in the unlikely case you need one.
_TSQL_LIMIT_RE = re.compile(r"(?<![\[\.\w])LIMIT\b", re.IGNORECASE)

# Any of these appearing anywhere in the parsed tree is a hard reject.
_FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Into,
    exp.Set,
)

# Acceptable root expression types (read-only queries).
_QUERY_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)

# Object-scope gate (#193 finding 4). validate_select() only checked
# statement *shape* before this -- it placed no restriction on which
# database/schema a table reference targets, so `SELECT * FROM
# NexoraDB.dbo.Users` or `SELECT name FROM sys.databases` parsed as an
# ordinary exp.Table and passed; the entire boundary was the server-side RO
# login's db_datareader grant (out-of-band DBA convention, no code-level
# backstop). A `catalog`-qualified table (three-/four-part name: any
# `database.schema.table` or linked-server `server.database.schema.table`)
# reaches into a different database than the one the RO connection is
# already pinned to, so it's rejected outright regardless of which database
# is named -- this sandbox has no legitimate cross-DB use case. `sys` /
# `INFORMATION_SCHEMA` / the system databases are blocked even
# unqualified-catalog since they're reachable within the connected DB too.
_BLOCKED_SCHEMAS = {"sys", "information_schema", "master", "tempdb", "model", "msdb"}


def _find_out_of_scope_table(root):
    for t in root.find_all(exp.Table):
        if t.args.get("catalog"):
            return t
        db = t.args.get("db")
        db_name = db.name if hasattr(db, "name") else db
        if db_name and str(db_name).strip('[]"').lower() in _BLOCKED_SCHEMAS:
            return t
    return None


class SqlSandboxError(ValueError):
    """Raised when SQL fails sandbox validation. `.rule` names the failed layer."""

    def __init__(self, rule, message, token=None):
        super().__init__(message)
        self.rule = rule
        self.token = token  # dynamic part (keyword/construct) for the i18n boundary


# pyodbc surfaces driver failures as a stringified (sqlstate, message) tuple,
# e.g. ('42000', "[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]The
# ORDER BY clause is invalid ... (1033) (SQLExecDirectW)") — unreadable noise
# for both the model and the UI trace. humanize_sql_error() below strips the
# tuple wrapper, the leading "[..][..]" driver-identity brackets, and the
# trailing "(NNNN) (SQLExecDirectW)" code+call suffix, then appends a teaching
# hint for known SQL Server error codes. Messages that don't look ODBC-shaped
# pass through unchanged.
_ODBC_TUPLE_RE = re.compile(r"^\(\s*'[^']*'\s*,\s*(['\"])(?P<msg>.*)\1\s*\)\s*$", re.DOTALL)
_ODBC_LEADING_BRACKETS_RE = re.compile(r"^(?:\[[^\[\]]*\]\s*)+")
_ODBC_TRAILING_CALL_RE = re.compile(r"\s*\(SQL\w*\)\s*$")
_ODBC_TRAILING_CODE_RE = re.compile(r"\s*\((\d+)\)\s*$")

# Mapping v1: SQL Server error code -> teaching hint. Unmapped codes are still
# cleaned of driver noise, just without a Hint: line.
_SQL_ERROR_HINTS = {
    "1033": (
        "ORDER BY inside a derived table needs TOP or OFFSET — or move "
        "ORDER BY to the outer SELECT."
    ),
    "156": (
        "In a set operation (UNION/EXCEPT/INTERSECT) ORDER BY may only follow "
        "the last branch, and each branch must be a complete SELECT — remove "
        "ORDER BY/extra clauses from inner branches or wrap the whole set "
        "operation in an outer SELECT and order there."
    ),
    "205": (
        "All branches of a set operation must project the same number of "
        "columns in the same order."
    ),
    "209": (
        "The column exists in more than one table/branch — qualify it with "
        "its table or CTE alias (e.g. e.d instead of d) everywhere, "
        "including GROUP BY and ORDER BY."
    ),
}


def humanize_sql_error(msg):
    """Strip pyodbc/ODBC driver noise from `msg` and append a teaching hint.

    Pure and English-only — this text feeds the model as well as the UI tool
    trace, so it must stay deterministic; never gettext it. Non-ODBC-shaped
    messages (validation errors, tool errors) are returned unchanged.
    """
    if not isinstance(msg, str) or not msg:
        return msg
    text = msg.strip()
    tuple_match = _ODBC_TUPLE_RE.match(text)
    if tuple_match:
        text = tuple_match.group("msg")
    unbracketed = _ODBC_LEADING_BRACKETS_RE.sub("", text)
    if unbracketed == text and tuple_match is None:
        return msg  # no ODBC markers at all -> pass through verbatim
    text = _ODBC_TRAILING_CALL_RE.sub("", unbracketed)
    code_match = _ODBC_TRAILING_CODE_RE.search(text)
    text = _ODBC_TRAILING_CODE_RE.sub("", text).strip()
    hint = _SQL_ERROR_HINTS.get(code_match.group(1)) if code_match else None
    if hint:
        text = f"{text}\nHint: {hint}"
    return text


# Comment-only strip, quote-UNAWARE. Used solely by wrap_with_cap() below to
# sniff a leading WITH/`;WITH` on ALREADY-validated SQL (validate_select() has
# always run first at every call site) -- it is a shape check, not a security
# scan, so a `--`/`/* */` marker hidden inside a quoted construct near the
# very start of the query (before the point wrap_with_cap() even looks) isn't
# a real concern here the way it is for the blocklist scan. Do not reuse this
# for anything that scans untrusted SQL for blocklisted content -- use
# _strip_for_scan() below for that.
def _strip_comments(sql):
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n\r]*", " ", no_block)


# T-SQL string literals escape an embedded quote by doubling it: 'it''s here'
# is the 8-character value it's here, and that doubled quote is NOT the end
# of the literal. Bracket-quoted ([a'b]) and double-quoted ("a""b") T-SQL
# identifiers can also legally contain a bare apostrophe -- and identifiers
# (aliases) are attacker-chosen -- so an apostrophe-blind literal stripper
# can be tricked into treating everything from that apostrophe to some LATER
# unrelated apostrophe as one "literal" and blanking real SQL out of the
# blocklist scan, including a keyword.
#
# Round 1 of this fix ran comment-stripping and literal-stripping as two
# SEPARATE blind passes (_strip_comments() then a literal-only regex here).
# That split is itself exploitable, two ways:
#   - A bracket-quoted identifier can legally contain a doubled `]]` (T-SQL's
#     escape for a literal `]`), e.g. [a]]b] is the single identifier a]b.
#     The round-1 bracket alternative `\[[^\]]*\]` didn't know that and
#     stopped at the FIRST `]`, leaving a stray quote character outside its
#     consumed span to open a phantom literal that swallowed real SQL --
#     including a keyword -- following it.
#   - `--`/`/* */` inside a string literal or a quoted identifier is not a
#     real comment in T-SQL, but blind comment-stripping ran BEFORE any
#     quote-awareness and deleted from `--` to end-of-line (or matched
#     `/* ... */`) regardless of what quoted construct it was sitting
#     inside, corrupting what the later literal-stripping pass saw.
# Either way a real keyword (OPENROWSET and friends -- see below) could end
# up erased from the scan along with the fake "literal"/"comment" around it.
#
# Fixed by doing comment-stripping and quote-stripping in ONE left-to-right
# alternation instead of two independent ones, so a comment marker that is
# actually inside a quoted construct is never treated as a real comment (and
# a quote/dash genuinely inside a real comment can't confuse the scan
# either). Bracket/double-quoted identifiers are matched leftmost-first
# (before the '...' alternative) and passed through completely unchanged --
# never blanked -- so a quote character inside one can't be mistaken for the
# start of a string literal and swallow real SQL that follows. The bracket
# alternative honors the `]]` escape so a doubled `]]` can't be mistaken for
# the identifier's closing bracket. A construct that never closes
# (malformed/truncated input) simply fails to match, so nothing is stripped
# for it and the raw text -- including any real keyword inside it -- still
# reaches the blocklist scan. Fail safe (under-strip), never fail open
# (over-strip and hide a real keyword).
#
# Round 3 closed two more gaps in this same tokenizer, found by a third
# review pass:
#   - The comment alternative stopped only at LF (`--[^\n]*`), but real T-SQL
#     also ends a `--` line comment at a bare CR. A payload using `\r`
#     instead of `\n` after `--` kept everything past it OUT of the scan
#     while SQL Server itself would treat the CR as ending the comment and
#     execute what followed -- hiding OPENROWSET the same way bypasses A/B
#     above did. Fixed by stopping at either terminator: `--[^\n\r]*`. The
#     same `[^\n]` -> `[^\n\r]` fix was applied to the separate, quote-unaware
#     _strip_comments() below for consistency (its impact there is a
#     correctness bug -- a CTE query with a CR before a leading WITH could be
#     mis-wrapped -- not a security bypass, since _strip_comments() only
#     feeds wrap_with_cap()'s shape check on already-validated SQL).
#   - The round-2 bracket alternative `\[(?:[^\]]|\]\])*\]`, while a correct
#     grouped alternation, backtracks catastrophically on adversarial input
#     (e.g. a long run of `[` or `['` characters): ~20-30 seconds of pure
#     CPU for a ~20KB payload, with no DB call involved so SQL_TIMEOUT_S
#     never applies. Any authenticated user with reporting.sql.run + a
#     target grant + the ack could stall a worker process this way,
#     independent of Flask-Limiter's per-worker (not shared) rate limiting.
#     Fixed with an atomic group -- `\[(?>[^\]]*(?:\]\][^\]]*)*)\]` --  which
#     preserves identical matching semantics (same `]]`-escape handling)
#     while eliminating the backtracking, since the atomic group commits to
#     its match of "run of non-`]` chars, then `]]`-escaped run, repeat" and
#     never re-explores it token-by-token on failure. Requires Python's `re`
#     atomic-group support (native since 3.11; this project requires >=3.13).
_SCAN_TOKEN_RE = re.compile(
    r"""/\*.*?\*/|--[^\n\r]*|\[(?>[^\]]*(?:\]\][^\]]*)*)\]|"(?:[^"]|"")*"|'(?:[^']|'')*'""",
    re.DOTALL,
)


def _strip_for_scan(sql):
    """Blank comments and literal CONTENTS for the blocklist/LIMIT scan.

    Comments (`/* */`, `--...`) collapse to a single space each, matching
    the old _strip_comments() replacement -- enough separation that tokens
    on either side can't merge into a new word. String literal contents
    blank to '' (e.g. 'update log' -> '') so the scan sees an inert empty
    literal rather than the word "update" (a false-positive DML match) or a
    token merge. Bracket- and double-quoted identifiers ([a'b], "a""b") are
    matched but left completely as-is -- never blanked -- so a quote
    character (or a `--`/`/* */` marker) inside one can't be mistaken for
    the start/end of some other construct and swallow real SQL that
    follows. This is the sole stripping pass feeding the blocklist and
    LIMIT scans; every other validate_select() check runs against the raw,
    unmodified `sql`.
    """

    def repl(m):
        tok = m.group(0)
        if tok.startswith(("/*", "--")):
            return " "
        if tok[0] in '["':
            return tok
        return "''"

    return _SCAN_TOKEN_RE.sub(repl, sql)


def validate_select(sql):
    """Return trimmed `sql` if it is one read-only query, else raise SqlSandboxError."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlSandboxError("empty", "SQL is required")
    sql = sql.strip()
    if len(sql) > MAX_SQL_LEN:
        raise SqlSandboxError("too_long", f"SQL exceeds {MAX_SQL_LEN} characters")

    # The blocklist and LIMIT checks below scan comment- AND literal-stripped
    # text (single tokenizer pass, see _strip_for_scan) so a keyword sitting
    # inside a string value (WHERE note = 'update log') doesn't
    # false-positive, and a comment marker or quote hidden inside a quoted
    # construct can't hide a real keyword either; every other check --
    # statement-shape, forbidden-node -- still runs against the raw `sql`,
    # unchanged.
    scan = _strip_for_scan(sql)
    m = _BLOCKED_RE.search(scan)
    if m:
        kw = m.group(0).strip()
        raise SqlSandboxError("blocked_keyword", f"disallowed keyword: {kw}", token=kw)
    if _TSQL_LIMIT_RE.search(scan):
        raise SqlSandboxError(
            "tsql_limit",
            "T-SQL does not support LIMIT — use TOP (n) instead",
            token="LIMIT",
        )

    try:
        statements = [s for s in sqlglot.parse(sql, dialect="tsql") if s is not None]
    except Exception as e:
        raise SqlSandboxError("parse", "could not parse SQL") from e
    if len(statements) != 1:
        raise SqlSandboxError("multi_statement", "exactly one statement is allowed")

    root = statements[0]
    if isinstance(root, _FORBIDDEN_NODES) or not isinstance(root, _QUERY_ROOTS):
        raise SqlSandboxError("not_select", "only SELECT / WITH / set-operations are allowed")

    forbidden = next(root.find_all(*_FORBIDDEN_NODES), None)
    if forbidden is not None:
        name = type(forbidden).__name__
        raise SqlSandboxError("forbidden_node", f"disallowed construct: {name}", token=name)

    out_of_scope = _find_out_of_scope_table(root)
    if out_of_scope is not None:
        ref = ".".join(
            p.name if hasattr(p, "name") else str(p)
            for p in (out_of_scope.args.get("catalog"), out_of_scope.args.get("db"))
            if p
        )
        raise SqlSandboxError(
            "cross_db", f"cross-database/system table reference not allowed: {ref}", token=ref
        )
    return sql


# A leading WITH (after stripping comments) marks a CTE-rooted query. T-SQL
# forbids WITH inside a derived-table subquery — `SELECT ... FROM ( WITH ... )
# AS _q` is a syntax error — so wrap_with_cap() below passes these through
# unwrapped instead of wrapping them; fetch_capped() enforces the row cap
# fetch-side for that path (D-CTE). WITH may also be preceded by a bare `;`
# (idiomatic T-SQL style, since WITH must start a batch or follow a
# semicolon-terminated statement) — tolerate that too.
_LEADING_WITH_RE = re.compile(r"^\s*;?\s*WITH\b", re.IGNORECASE)


def _has_trailing_order_by(sql):
    """True when the statement carries a top-level ORDER BY (issue #129).

    Such a query is legal standalone but illegal inside the derived-table
    wrap (SQL Server error 1033), so wrap_with_cap() must pass it through
    unwrapped. Detection is AST-based: a WITHIN GROUP or window ORDER BY,
    or one confined to the user's own TOP-capped derived table, does not
    set the statement-level `order` arg and keeps the wrap. sqlglot parks a
    set-operation's trailing ORDER BY on the rightmost branch, so recurse
    there. Runs on already-validated SQL; an unparseable statement falls
    back to wrapping (the pre-#129 behavior).
    """
    try:
        node = sqlglot.parse_one(sql, dialect="tsql")
    except Exception:
        return False
    while isinstance(node, exp.Subquery):
        node = node.this
    while isinstance(node, exp.SetOperation):
        if node.args.get("order") is not None:
            return True
        node = node.expression
        while isinstance(node, exp.Subquery):
            node = node.this
    return node is not None and node.args.get("order") is not None


def wrap_with_cap(sql, cap):
    """Wrap a validated query as a capped derived table. `cap` is server-supplied.

    A CTE-rooted query (`WITH ... SELECT ...`) is returned unwrapped: WITH
    cannot legally appear inside a derived-table subquery, so wrapping it as
    `SELECT TOP (n) * FROM ( WITH ... ) AS _q` is invalid T-SQL. The same
    applies to a query with a top-level ORDER BY — legal standalone, error
    1033 inside the wrap (issue #129). The caller must cap such queries
    fetch-side instead, via fetch_capped() below, applied the same way on
    every path (wrapped or not).
    """
    cap = int(cap)
    if _LEADING_WITH_RE.match(_strip_comments(sql)) or _has_trailing_order_by(sql):
        return sql
    return f"SELECT TOP ({cap}) * FROM (\n{sql}\n) AS _q"


def fetch_capped(cursor, cap):
    """Fetch at most `cap` rows from `cursor`. Returns (rows, truncated).

    Uniform fetch-side cap enforcement for every wrap_with_cap() output
    (D-CTE): a plain SELECT's TOP-wrapped result set is already <= cap rows,
    so this just drains it; a WITH-rooted or top-level-ORDER-BY query is
    passed through unwrapped and has no SQL-side cap at all, so this fetch is
    the only enforcement for that path. Requests cap + 1 rows so getting a
    full extra row means "there was more" without a second COUNT query.
    """
    cap = int(cap)
    fetched = cursor.fetchmany(cap + 1)
    truncated = len(fetched) > cap
    return [list(r) for r in fetched[:cap]], truncated
