"""Live read-only SQL sandbox for Reporting Phase 2 (security boundary).

Pure and DB-free: validates that a user-supplied string is a single read-only
SELECT (or WITH ... / set-operation) and wraps it with a row cap. The view layer
runs the result on a dedicated db_datareader-only engine with a statement timeout
and audits every execution. The sqlglot AST gate is the authority; the keyword
blocklist is a backup.
"""

import re

import sqlglot
from sqlglot import exp

MAX_SQL_LEN = 20000

# Backup keyword blocklist (word-boundary, case-insensitive, comment-stripped).
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


def _strip_comments(sql):
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", no_block)


def validate_select(sql):
    """Return trimmed `sql` if it is one read-only query, else raise SqlSandboxError."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlSandboxError("empty", "SQL is required")
    sql = sql.strip()
    if len(sql) > MAX_SQL_LEN:
        raise SqlSandboxError("too_long", f"SQL exceeds {MAX_SQL_LEN} characters")

    scan = _strip_comments(sql)
    m = _BLOCKED_RE.search(scan)
    if m:
        kw = m.group(0).strip()
        raise SqlSandboxError("blocked_keyword", f"disallowed keyword: {kw}", token=kw)

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


def wrap_with_cap(sql, cap):
    """Wrap a validated query as a capped derived table. `cap` is server-supplied."""
    cap = int(cap)
    return f"SELECT TOP ({cap}) * FROM (\n{sql}\n) AS _q"
