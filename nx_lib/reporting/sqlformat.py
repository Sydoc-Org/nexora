"""Display-only T-SQL pretty-printer for the reporting Show-query panels.

format_sql() is best-effort: any parse problem returns the input unchanged.
The executed SQL is never altered — api_run echoes the pretty string in a
separate response field (sqlPretty) and keeps the raw `sql` authoritative
(the Copy button and every other consumer read the raw field). sqlglot
re-renders from its AST and normalizes tokens (verified: ``TOP (5000)``
becomes ``TOP 5000``), so the pretty string is for DISPLAY ONLY.
"""

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
