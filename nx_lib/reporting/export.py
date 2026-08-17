"""Export report rows to an .xlsx workbook (openpyxl) or a .csv file."""

import csv
import decimal
import io
import re
from datetime import UTC, date, datetime, time

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

# Leading characters that spreadsheet apps may interpret as a live formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")

# Types openpyxl/csv already know how to render — everything else gets str()'d.
# (date covers datetime too, since datetime is a date subclass.)
_PRIMITIVE_CELL_TYPES = (str, int, float, bool, decimal.Decimal, date, time)


def _safe_cell(v):
    """Coerce a raw DB cell into something openpyxl/csv can write, then
    neutralize spreadsheet formula injection.

    - bytes/bytearray/memoryview (varbinary, rowversion, image columns) are
      decoded best-effort to text — openpyxl raises TypeError on raw bytes,
      and the csv path would otherwise write the Python b'...' repr literally.
    - Control characters outside the small set XML allows (tab/CR/LF) are
      stripped with openpyxl's own ILLEGAL_CHARACTERS_RE — the same pattern
      openpyxl uses internally to reject a cell value.
    - Any other non-primitive type (UUID, etc.) is stringified as a last
      resort; a cell must never 500 the export.
    - Finally, a leading formula-trigger character is prefixed with ' so
      spreadsheet apps don't evaluate it as a live formula.
    """
    if isinstance(v, bytes | bytearray | memoryview):
        v = bytes(v).decode("utf-8", "replace")
    elif v is not None and not isinstance(v, _PRIMITIVE_CELL_TYPES):
        v = str(v)
    if isinstance(v, str):
        v = ILLEGAL_CHARACTERS_RE.sub("", v)
        if v and v[0] in _FORMULA_PREFIXES:
            return "'" + v
    return v


def rows_to_xlsx(columns, rows, *, title, chart_png=None, generated_at=None, forecast_start=None):
    """Return .xlsx bytes: bold title, meta line, optional chart image, then
    a styled header row and the data.

    columns: [{field, header}] — header falls back to field when None/empty.
    rows: iterable of row sequences aligned to columns.
    title: report title; also the worksheet title (sanitized — illegal
        sheet-title characters (\\ / ? * [ ] :) replaced with spaces,
        truncated to Excel's 31-char limit).
    chart_png: optional PNG bytes rendered above the data table.
    generated_at: optional datetime for the meta line (defaults to utcnow).
    forecast_start: optional 0-based index into `rows` — rows at/after this
        index are predicted (not actual) and are styled grey-italic.
    """
    wb = Workbook()
    ws = wb.active
    safe_title = re.sub(r"[\\/?*\[\]:]", " ", (title or "Report")).strip() or "Report"
    ws.title = safe_title[:31]

    # Row 1: bold title — _safe_cell guards formula-injection (e.g. =HYPERLINK titles)
    ws["A1"] = _safe_cell(title or "Report")
    ws["A1"].font = Font(bold=True, size=14)

    # Row 2: meta line (grey)
    stamp = (generated_at or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    row_list = list(rows)
    ws["A2"] = f"Generated {stamp} — {len(row_list)} rows"
    ws["A2"].font = Font(size=10, color="6B7280")

    # Row 4+: optional chart image, then header row
    header_row = 4
    if chart_png:
        try:
            from openpyxl.drawing.image import Image as XlsxImage

            img = XlsxImage(io.BytesIO(chart_png))
            # scale to ~640px wide, keep aspect
            if img.width and img.width > 640:
                ratio = 640.0 / img.width
                img_h = int(img.height * ratio)
                img.width, img.height = 640, img_h
            ws.add_image(img, "A4")
            header_row = 4 + max(1, int((img.height or 300) / 20)) + 1
        except Exception:
            pass  # malformed PNG — fall back to chartless layout

    # Header row: bold + fill
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="EEF2FF")
    for i, col in enumerate(columns, start=1):
        cell = ws.cell(
            row=header_row, column=i, value=_safe_cell(col.get("header") or col.get("field"))
        )
        cell.font = header_font
        cell.fill = header_fill
        ws.column_dimensions[get_column_letter(i)].width = 18

    # Data rows
    fc_font = Font(italic=True, color="6B7280")
    for r_off, row in enumerate(row_list, start=1):
        is_fc = forecast_start is not None and (r_off - 1) >= forecast_start
        for c_off, val in enumerate(row, start=1):
            cell = ws.cell(row=header_row + r_off, column=c_off, value=_safe_cell(val))
            if is_fc:
                cell.font = fc_font

    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def rows_to_csv(columns, rows):
    """Return UTF-8 (BOM-prefixed) .csv bytes for `rows` with a header row.

    columns: [{field, header}] — header falls back to field when None/empty.
    rows: iterable of row sequences aligned to columns.

    The BOM makes Excel detect UTF-8 on double-click. Cells are passed through
    the same formula-injection guard as the xlsx path. Line terminator is
    CRLF (RFC 4180) so the file opens cleanly on Windows and in Excel.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([_safe_cell(c.get("header") or c["field"]) for c in columns])
    for row in rows:
        writer.writerow(["" if v is None else _safe_cell(v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")
