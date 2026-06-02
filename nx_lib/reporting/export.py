"""Export report rows to an .xlsx workbook (openpyxl)."""

import io
import re

from openpyxl import Workbook


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
    ws.append([(c.get("header") or c["field"]) for c in columns])
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
