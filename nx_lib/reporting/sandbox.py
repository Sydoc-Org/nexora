"""Live read-only SQL sandbox for Reporting Phase 2 (security boundary).

Pure and DB-free: validates that a user-supplied string is a single read-only
SELECT (or WITH ... / set-operation) and wraps it with a row cap — plain SELECTs
get a `SELECT TOP (n) * FROM (...) AS _q` wrap; WITH-rooted queries pass through
unwrapped, since WITH cannot appear inside that derived-table subquery, and
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


def _strip_comments(sql):
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", no_block)


# T-SQL string literals escape an embedded quote by doubling it: 'it''s here'
# is the 8-character value it's here, and that doubled quote is NOT the end
# of the literal. This pattern walks a well-formed '...' literal the same
# way: its content is any run of non-quote characters or doubled-quote
# pairs, closed by a single unescaped quote. A literal that never closes
# (malformed/truncated input) simply fails to match, so nothing is stripped
# for it and the raw text -- including any real keyword inside it -- still
# reaches the blocklist scan. Fail safe (under-strip), never fail open
# (over-strip and hide a real keyword).
_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")


def _strip_string_literals(sql):
    """Blank literal CONTENTS for the blocklist scan; keep the delimiters.

    'update log' -> '' so the scan sees an inert empty literal rather than
    the word "update" (a false-positive DML match against the blocklist) or
    nothing at all (which would risk merging the tokens on either side of
    the literal into something the blocklist misreads).
    """
    return _STRING_LITERAL_RE.sub("''", sql)


def validate_select(sql):
    """Return trimmed `sql` if it is one read-only query, else raise SqlSandboxError."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlSandboxError("empty", "SQL is required")
    sql = sql.strip()
    if len(sql) > MAX_SQL_LEN:
        raise SqlSandboxError("too_long", f"SQL exceeds {MAX_SQL_LEN} characters")

    scan = _strip_comments(sql)
    # The blocklist scans literal-stripped text so a keyword sitting inside a
    # string value (WHERE note = 'update log') doesn't false-positive; every
    # other check below -- LIMIT, statement-shape, forbidden-node -- still
    # runs against `scan` (comment-stripped only) or the raw `sql`, unchanged.
    m = _BLOCKED_RE.search(_strip_string_literals(scan))
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
    return sql


# A leading WITH (after stripping comments) marks a CTE-rooted query. T-SQL
# forbids WITH inside a derived-table subquery — `SELECT ... FROM ( WITH ... )
# AS _q` is a syntax error — so wrap_with_cap() below passes these through
# unwrapped instead of wrapping them; fetch_capped() enforces the row cap
# fetch-side for that path (D-CTE). WITH may also be preceded by a bare `;`
# (idiomatic T-SQL style, since WITH must start a batch or follow a
# semicolon-terminated statement) — tolerate that too.
_LEADING_WITH_RE = re.compile(r"^\s*;?\s*WITH\b", re.IGNORECASE)


def wrap_with_cap(sql, cap):
    """Wrap a validated query as a capped derived table. `cap` is server-supplied.

    A CTE-rooted query (`WITH ... SELECT ...`) is returned unwrapped: WITH
    cannot legally appear inside a derived-table subquery, so wrapping it as
    `SELECT TOP (n) * FROM ( WITH ... ) AS _q` is invalid T-SQL. The caller
    must cap such queries fetch-side instead, via fetch_capped() below,
    applied the same way on every path (wrapped or not).
    """
    cap = int(cap)
    if _LEADING_WITH_RE.match(_strip_comments(sql)):
        return sql
    return f"SELECT TOP ({cap}) * FROM (\n{sql}\n) AS _q"


def fetch_capped(cursor, cap):
    """Fetch at most `cap` rows from `cursor`. Returns (rows, truncated).

    Uniform fetch-side cap enforcement for every wrap_with_cap() output
    (D-CTE): a plain SELECT's TOP-wrapped result set is already <= cap rows,
    so this just drains it; a WITH-rooted query is passed through unwrapped
    and has no SQL-side cap at all, so this fetch is the only enforcement for
    that path. Requests cap + 1 rows so getting a full extra row means "there
    was more" without a second COUNT query.
    """
    cap = int(cap)
    fetched = cursor.fetchmany(cap + 1)
    truncated = len(fetched) > cap
    return [list(r) for r in fetched[:cap]], truncated
