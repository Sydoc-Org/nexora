"""Display-only T-SQL pretty-printer for the reporting Show-query panels.

format_sql() is best-effort: any parse problem returns the input unchanged.
The executed SQL is never altered — api_run echoes the pretty string in a
separate response field (sqlPretty) and keeps the raw `sql` authoritative
(the Copy button and every other consumer read the raw field). sqlglot
re-renders from its AST and normalizes tokens (verified: ``TOP (5000)``
becomes ``TOP 5000``), so the pretty string is for DISPLAY ONLY.
"""

import datetime
import decimal
import re

import sqlglot


def format_sql(sql):
    """Pretty-print a T-SQL string for display.

    Preserves pyodbc ``?`` placeholders and keeps every statement when the
    input contains more than one. Falls back to the input on any sqlglot
    error — an unformattable string must never break a run response.
    """
    if not isinstance(sql, str) or not sql.strip():
        return sql
    try:
        statements = sqlglot.transpile(sql, read="tsql", write="tsql", pretty=True)
    except Exception:
        return sql
    pretty = ";\n".join(s for s in statements if s)
    return pretty or sql


# Mirrors the client highlighter's tokenization (_reporting_sqlformat_js.html):
# a ? inside a 'string' (with '' escapes), a [bracketed identifier] or a
# -- comment is never a placeholder.
_INLINE_TOKEN_RE = re.compile(r"(--[^\n]*)" r"|('(?:[^']|'')*')" r"|(\[[^\]]*\])" r"|(\?)")


def _sql_literal(value):
    """One bound parameter as a T-SQL literal, or None for unknown types."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):  # before int: bool subclasses int
        return "1" if value else "0"
    if isinstance(value, int | float | decimal.Decimal):
        return str(value)
    if isinstance(value, datetime.date | datetime.datetime | datetime.time):
        return "'" + value.isoformat() + "'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def inline_sql_params(sql, params):
    """Return `sql` with each bare pyodbc ``?`` replaced by its literal.

    Display/copy only — execution stays parameterized (api_run keeps sending
    sql+params to pyodbc). Returns None when the placeholder count disagrees
    with len(params) or a parameter has no literal form; callers fall back to
    the placeholder rendering, so this can never lie about what executed.
    """
    if not isinstance(sql, str):
        return None
    out = []
    pos = 0
    i = 0
    for m in _INLINE_TOKEN_RE.finditer(sql):
        out.append(sql[pos : m.start()])
        if m.group(4):
            if i >= len(params):
                return None
            lit = _sql_literal(params[i])
            if lit is None:
                return None
            out.append(lit)
            i += 1
        else:
            out.append(m.group(0))
        pos = m.end()
    out.append(sql[pos:])
    if i != len(params):
        return None
    return "".join(out)
