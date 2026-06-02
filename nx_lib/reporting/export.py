"""Export report rows to an .xlsx workbook (openpyxl)."""

import io
import re

from openpyxl import Workbook

# Leading characters that spreadsheet apps may interpret as a live formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _safe_cell(v):
    """Neutralize spreadsheet formula injection: prefix risky leading chars with '."""
    if isinstance(v, str) and v and v[0] in _FORMULA_PREFIXES:
        return "'" + v
    return v


def rows_to_xlsx(columns, rows, *, title):
    """Return .xlsx bytes for `rows` with a header row from `columns`.

    columns: [{field, header}] — header falls back to field when None/empty.
    rows: iterable of row sequences aligned to columns.
    title: used as the worksheet title. Illegal sheet-title characters
        (\\ / ? * [ ] :) are replaced with spaces and the result is
        truncated to Excel's 31-char limit.
    """
    wb = Workbook()
    ws = wb.active
    safe_title = re.sub(r"[\\/?*\[\]:]", " ", (title or "Report")).strip() or "Report"
    ws.title = safe_title[:31]
    ws.append([_safe_cell(c.get("header") or c["field"]) for c in columns])
    for row in rows:
        ws.append([_safe_cell(v) for v in row])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
