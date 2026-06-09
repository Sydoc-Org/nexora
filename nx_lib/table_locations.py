"""Pure helper: Octopus thin-document JSON (fetched with ``WithTables=true``)
-> table / line-item source locations. No Flask / HTTP here so it can be
unit-tested in isolation, mirroring :mod:`nx_lib.field_locations`.

Shape verified live on INT (see the design spec's "Verified shape (INT spike,
2026-06-09)"): tables live at ``doc["Tables"][] = {Name, Rows:[{ID, Cells:[]}]}``.
A cell carries ``ColumnName``, ``CellValue.Text`` (fallback ``CapturedValue``),
``Confidence``, and a ``Location`` — the *same* ``DtoImageBasedLocation`` as
scalar index fields (``Rectangle`` / ``Rectangles`` ``{Left,Top,Width,Height}``
in image pixels, page via ``PageIndex``; ``{0,0,0,0}`` = derived / un-locatable).

A table cell is therefore "just another source": each kept cell becomes
``{col, value, locations:[{page, rect}], confidence?}``, grouped into rows under
a table ``{title, columns, rows}``. Page indices use the **identical** item
iteration + per-item image-media offset as the scalar parser, so they align with
the ``urls`` list ``api_get_media_raw`` serves regardless of document shape.
"""

from .field_locations import (
    confidence_of,
    count_image_media,
    items_of,
    num,
    rect_from_octo,
)


def _cell_value(cell):
    """Text of a table cell: prefer ``CellValue.Text``, fall back to the raw
    ``CapturedValue``. ``None`` means the cell is empty (skipped)."""
    text = (cell.get("CellValue") or {}).get("Text")
    if text is None:
        text = cell.get("CapturedValue")
    return text


def _cell_locations(cell, media_offset):
    """Pixel rects for one cell, page-shifted by ``media_offset`` (image media in
    prior items). Empty list when the cell has no usable coordinates."""
    loc = cell.get("Location") or cell.get("CapturedLocation")
    out = []
    if isinstance(loc, dict):
        page_index = num(loc.get("PageIndex"))
        if page_index is not None:
            page = media_offset + int(page_index)
            raw = loc.get("Rectangles")
            if not raw:
                single = loc.get("Rectangle")
                raw = [single] if single else []
            for r in raw:
                rect = rect_from_octo(r)
                if rect is not None:
                    out.append({"page": page, "rect": rect})
    return out


def extract_table_locations(doc_json):
    """Build the ``table_sources`` list from an Octopus thin-document response.

    Returns ``[{title, columns, rows:[[{col, value, locations:[{page, rect}],
    confidence?}]]}]`` — one entry per non-empty table. ``columns`` is the
    first-seen order of valued cells' ``ColumnName``. Cells with no value are
    skipped; rows with no valued cell are dropped; tables with no rows are
    dropped (so an unpopulated table schema never reaches the UI). ``rect`` is in
    image pixels; ``page`` is the 0-based media index (matching
    ``api_get_media_raw``). ``confidence`` (0..1) is present only when reported.
    """
    out = []
    media_offset = 0
    for item in items_of(doc_json):
        for tbl in item.get("Tables") or []:
            columns = []
            seen_cols = set()
            rows_out = []
            for row in tbl.get("Rows") or []:
                cells_out = []
                for cell in row.get("Cells") or []:
                    value = _cell_value(cell)
                    if value is None:
                        continue
                    col = cell.get("ColumnName")
                    if col is not None and col not in seen_cols:
                        seen_cols.add(col)
                        columns.append(col)
                    entry = {
                        "col": col,
                        "value": value,
                        "locations": _cell_locations(cell, media_offset),
                    }
                    conf = confidence_of(cell)
                    if conf is not None:
                        entry["confidence"] = conf
                    cells_out.append(entry)
                if cells_out:
                    rows_out.append(cells_out)
            if rows_out:
                out.append({"title": tbl.get("Name"), "columns": columns, "rows": rows_out})
        media_offset += count_image_media(item)
    return out
