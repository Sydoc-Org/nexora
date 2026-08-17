"""Unit tests for nx_lib.table_locations — pure parsing of the Octopus
thin-document JSON (WithTables=true) into table/line-item source locations.

Shape verified live on INT (see the design spec's "Verified shape (INT spike,
2026-06-09)"): tables at doc["Tables"][] = {Name, Rows:[{ID, Cells:[...]}]}; a
cell has ColumnName, CellValue.Text (fallback CapturedValue), Confidence, and a
Location (the same DtoImageBasedLocation as scalar fields — Rectangle/Rectangles
{Left,Top,Width,Height} in image pixels, page via PageIndex; {0,0,0,0} = none).
"""

from nx_lib.table_locations import extract_table_locations

R = {"Left": 851, "Top": 2407, "Width": 543, "Height": 544}
ZERO = {"Left": 0, "Top": 0, "Width": 0, "Height": 0}


def _cell(col, text, rect=None, conf=None, page_index=0, captured=None):
    cell = {
        "ColumnName": col,
        "CapturedValue": captured,
        "CellValue": {"Text": text},
        "Confidence": conf,
    }
    if rect is not None:
        cell["Location"] = {"PageIndex": page_index, "Rectangle": rect, "Rectangles": [rect]}
    return cell


def _table(name, rows, doc_key="Tables"):
    return {
        doc_key: [{"Name": name, "Rows": [{"ID": f"r{i}", "Cells": r} for i, r in enumerate(rows)]}]
    }


# --- happy path ------------------------------------------------------------


def test_cell_with_rect_yields_box():
    doc = _table("TabVat", [[_cell("TabNetAmount", "236.82", R, conf=0.0)]])
    ts = extract_table_locations(doc)
    assert len(ts) == 1
    assert ts[0]["title"] == "TabVat"
    assert ts[0]["columns"] == ["TabNetAmount"]
    cell = ts[0]["rows"][0][0]
    assert cell["col"] == "TabNetAmount"
    assert cell["value"] == "236.82"
    assert cell["locations"] == [
        {"page": 0, "rect": {"left": 851, "top": 2407, "width": 543, "height": 544}}
    ]
    assert cell["confidence"] == 0.0


def test_columns_derived_in_first_seen_order():
    doc = _table(
        "T",
        [
            [_cell("A", "1"), _cell("B", "2")],
            [_cell("A", "3"), _cell("C", "4")],
        ],
    )
    assert extract_table_locations(doc)[0]["columns"] == ["A", "B", "C"]


def test_value_falls_back_to_captured_value():
    cell = {
        "ColumnName": "X",
        "CapturedValue": "7.7",
        "CellValue": {"Text": None},
        "Location": {"PageIndex": 0, "Rectangle": R},
    }
    doc = {"Tables": [{"Name": "T", "Rows": [{"Cells": [cell]}]}]}
    assert extract_table_locations(doc)[0]["rows"][0][0]["value"] == "7.7"


# --- un-locatable / empty --------------------------------------------------


def test_cell_without_rect_is_unlocatable():
    doc = _table("T", [[_cell("Qty", "3")]])
    assert extract_table_locations(doc)[0]["rows"][0][0]["locations"] == []


def test_degenerate_zero_rect_dropped():
    doc = _table("T", [[_cell("Qty", "3", ZERO)]])
    assert extract_table_locations(doc)[0]["rows"][0][0]["locations"] == []


def test_empty_cells_skipped_but_valued_kept():
    doc = _table("T", [[_cell("A", None), _cell("B", "v")]])
    rows = extract_table_locations(doc)[0]["rows"]
    assert rows == [[{"col": "B", "value": "v", "locations": []}]]


def test_row_with_no_valued_cells_dropped():
    doc = _table("T", [[_cell("A", None), _cell("B", None)]])
    assert extract_table_locations(doc) == []


def test_empty_table_dropped():
    assert extract_table_locations({"Tables": [{"Name": "T", "Rows": []}]}) == []


def test_no_tables_returns_empty():
    assert extract_table_locations({"Tables": []}) == []
    assert extract_table_locations({}) == []


# --- multi-box / confidence -------------------------------------------------


def test_multiple_rectangles_per_cell():
    r2 = {"Left": 10, "Top": 20, "Width": 30, "Height": 40}
    cell = {
        "ColumnName": "A",
        "CellValue": {"Text": "v"},
        "Location": {"PageIndex": 0, "Rectangles": [R, r2]},
    }
    doc = {"Tables": [{"Name": "T", "Rows": [{"Cells": [cell]}]}]}
    locs = extract_table_locations(doc)[0]["rows"][0][0]["locations"]
    assert len(locs) == 2


def test_confidence_percent_scale_normalized():
    doc = _table("T", [[_cell("A", "v", R, conf=88)]])
    assert extract_table_locations(doc)[0]["rows"][0][0]["confidence"] == 0.88


def test_confidence_absent_key_omitted():
    cell = {
        "ColumnName": "A",
        "CellValue": {"Text": "v"},
        "Location": {"PageIndex": 0, "Rectangle": R},
    }
    doc = {"Tables": [{"Name": "T", "Rows": [{"Cells": [cell]}]}]}
    assert "confidence" not in extract_table_locations(doc)[0]["rows"][0][0]


# --- Batch page offset ------------------------------------------------------


def test_batch_page_offset_shifts_child_table_page():
    # child[0] has 1 image medium -> child[1]'s PageIndex 0 maps to global page 1
    child0 = {"Media": [{"Extension": ".jpg", "Url": "u0"}], "Tables": []}
    child1 = _table("T", [[_cell("A", "v", R, page_index=0)]])
    child1["Media"] = []
    doc = {"DocumentType": "Batch", "ChildDocuments": [child0, child1]}
    cell = extract_table_locations(doc)[0]["rows"][0][0]
    assert cell["locations"][0]["page"] == 1


# --- nested / non-"Batch" container documents (MS02 MobScn* tree) -----------


def test_non_batch_container_recurses_for_tables():
    leaf = _table("T", [[_cell("A", "v", R, page_index=0)]])
    leaf["Media"] = [{"Extension": ".jpg", "Url": "u"}]
    dossier = {"DocumentType": "MobScnDossier", "ChildDocuments": [leaf]}
    ts = extract_table_locations(dossier)
    assert len(ts) == 1
    assert ts[0]["rows"][0][0]["value"] == "v"


def test_multi_level_container_table_page_offset():
    # MobScnBatch -> MobScnDossier -> [leaf0 (1 image, no table), leaf1 (table)]
    leaf0 = {"Media": [{"Extension": ".jpg", "Url": "u0"}], "Tables": []}
    leaf1 = _table("T", [[_cell("A", "v", R, page_index=0)]])
    leaf1["Media"] = []
    dossier = {"DocumentType": "MobScnDossier", "ChildDocuments": [leaf0, leaf1]}
    batch = {"DocumentType": "MobScnBatch", "ChildDocuments": [dossier]}
    cell = extract_table_locations(batch)[0]["rows"][0][0]
    assert cell["locations"][0]["page"] == 1


# --- PDF-expanded page offset (mixed PDF + image container) ----------------
# Mirrors test_field_locations.py: octo.get_extensions_urls_fields expands each
# PDF medium into N page slots (real I/O) before calling this module, and
# passes the pre-computed per-item counts in as ``pdf_page_counts``.


def test_pdf_media_counted_in_table_page_offset_when_supplied():
    # child0 (a PDF, pre-counted upstream as 2 pages) has no table of its own;
    # child1's cell PageIndex 0 must map to global page 2 (not 0).
    child0 = {"Media": [{"Extension": ".pdf", "Url": "u0"}], "Tables": []}
    child1 = _table("T", [[_cell("A", "v", R, page_index=0)]])
    child1["Media"] = []
    doc = {"DocumentType": "Batch", "ChildDocuments": [child0, child1]}
    cell = extract_table_locations(doc, pdf_page_counts=[2, 0])[0]["rows"][0][0]
    assert cell["locations"][0]["page"] == 2


def test_pdf_media_defaults_to_zero_pages_without_pdf_page_counts():
    # Backward compatibility: no pdf_page_counts -> pre-fix behaviour (PDF
    # contributes 0 to the offset).
    child0 = {"Media": [{"Extension": ".pdf", "Url": "u0"}], "Tables": []}
    child1 = _table("T", [[_cell("A", "v", R, page_index=0)]])
    child1["Media"] = []
    doc = {"DocumentType": "Batch", "ChildDocuments": [child0, child1]}
    cell = extract_table_locations(doc)[0]["rows"][0][0]
    assert cell["locations"][0]["page"] == 0


# --- image media without a URL (skipped by octo.get_extensions_urls_fields) -
# extract_table_locations shares field_locations._count_image_media for its
# page offset, so a URL-less image between two real pages must not shift a
# later table cell's page either.


def test_url_less_image_between_two_real_pages_does_not_shift_table_offset():
    # child0: real image (rendered page 0), no table.
    # child1: URL-less image only -- octo skips it, never becomes a page.
    # child2: real image (rendered page 1) + the table cell under test.
    # A naive counter would put the cell's PageIndex 0 at global page 2.
    child0 = {"Media": [{"Extension": ".jpg", "Url": "u0"}], "Tables": []}
    child1 = {"Media": [{"Extension": ".jpg", "Url": None}], "Tables": []}
    child2 = _table("T", [[_cell("A", "v", R, page_index=0)]])
    child2["Media"] = [{"Extension": ".jpg", "Url": "u2"}]
    doc = {"DocumentType": "Batch", "ChildDocuments": [child0, child1, child2]}
    cell = extract_table_locations(doc)[0]["rows"][0][0]
    assert cell["locations"][0]["page"] == 1
