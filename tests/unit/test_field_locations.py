"""Unit tests for nx_lib.field_locations — pure parsing of the Octopus
thin-document JSON into field source locations (image-pixel rects).

Shape verified live on INT (see the design spec's "Verified coordinate shape"):
coordinates live at IndexField.Location (DtoImageBasedLocation) as
Rectangle / Rectangles {Left,Top,Width,Height} in image pixels; page via
Location.PageIndex; degenerate {0,0,0,0} rects are un-locatable.
"""

from nx_lib.field_locations import _rect_from_octo, extract_field_locations

# --- _rect_from_octo -------------------------------------------------------


def test_rect_basic():
    assert _rect_from_octo({"Left": 749, "Top": 473, "Width": 347, "Height": 50}) == {
        "left": 749,
        "top": 473,
        "width": 347,
        "height": 50,
    }


def test_rect_degenerate_zero_is_none():
    assert _rect_from_octo({"Left": 0, "Top": 0, "Width": 0, "Height": 0}) is None


def test_rect_negative_dims_is_none():
    assert _rect_from_octo({"Left": 5, "Top": 5, "Width": -3, "Height": 10}) is None
    assert _rect_from_octo({"Left": 5, "Top": 5, "Width": 3, "Height": 0}) is None


def test_rect_non_numeric_is_none():
    assert _rect_from_octo({"Left": "?", "Top": 1, "Width": 2, "Height": 2}) is None


def test_rect_non_dict_is_none():
    assert _rect_from_octo(None) is None
    assert _rect_from_octo([1, 2, 3]) is None


# --- extract_field_locations ----------------------------------------------

MAPPING = {"DocNo": "Doc number", "DocDate": "Doc date", "VatRate1": "VAT rate", "Notes": "Notes"}


def _field(name, text, location=None, captured=None):
    f = {"Name": name, "FieldValue": {"Text": text}}
    f["Location"] = location
    f["CapturedLocation"] = captured
    return f


def _loc(page_index, rects):
    """rects: list of (x,y,w,h). Single-element -> also sets Rectangle."""
    rect_objs = [{"Left": x, "Top": y, "Width": w, "Height": h} for (x, y, w, h) in rects]
    loc = {"PageNumber": page_index + 1, "PageIndex": page_index, "Rectangles": rect_objs}
    if rect_objs:
        loc["Rectangle"] = rect_objs[0]
    return loc


def test_single_located_mapped_field():
    doc = {"IndexFields": [_field("DocNo", "INV-1", _loc(0, [(749, 473, 347, 50)]))]}
    assert extract_field_locations(doc, MAPPING) == [
        {
            "key": "Doc number",
            "label": "Doc number",
            "value": "INV-1",
            "locations": [
                {"page": 0, "rect": {"left": 749, "top": 473, "width": 347, "height": 50}}
            ],
        }
    ]


def test_degenerate_rect_field_is_unlocatable():
    # VatRate1 has a value but {0,0,0,0} rect -> shown, but no location.
    doc = {"IndexFields": [_field("VatRate1", "7.7", _loc(0, [(0, 0, 0, 0)]))]}
    out = extract_field_locations(doc, MAPPING)
    assert out == [{"key": "VAT rate", "label": "VAT rate", "value": "7.7", "locations": []}]


def test_multi_rectangle_field():
    doc = {
        "IndexFields": [
            _field("Notes", "two lines", _loc(1, [(10, 10, 100, 30), (10, 50, 200, 30)]))
        ]
    }
    out = extract_field_locations(doc, MAPPING)
    assert len(out[0]["locations"]) == 2
    assert all(loc["page"] == 1 for loc in out[0]["locations"])


def test_unmapped_field_skipped():
    doc = {"IndexFields": [_field("InternalId", "x", _loc(0, [(1, 1, 5, 5)]))]}
    assert extract_field_locations(doc, MAPPING) == []


def test_none_value_field_skipped():
    # mirrors existing `fields` dict: only non-None FieldValue.Text is shown
    doc = {"IndexFields": [_field("DocNo", None, _loc(0, [(1, 1, 5, 5)]))]}
    assert extract_field_locations(doc, MAPPING) == []


def test_captured_location_fallback():
    doc = {
        "IndexFields": [_field("DocNo", "INV-2", location=None, captured=_loc(2, [(5, 6, 7, 8)]))]
    }
    out = extract_field_locations(doc, MAPPING)
    assert out[0]["locations"] == [
        {"page": 2, "rect": {"left": 5, "top": 6, "width": 7, "height": 8}}
    ]


def test_no_location_yields_empty():
    doc = {"IndexFields": [_field("DocNo", "INV-3", location=None, captured=None)]}
    assert extract_field_locations(doc, MAPPING)[0]["locations"] == []


def test_first_occurrence_wins():
    doc = {
        "IndexFields": [
            _field("DocNo", "first", _loc(0, [(1, 1, 5, 5)])),
            _field("DocNo", "second", _loc(1, [(2, 2, 9, 9)])),
        ]
    }
    out = extract_field_locations(doc, MAPPING)
    assert len(out) == 1 and out[0]["value"] == "first" and out[0]["locations"][0]["page"] == 0


def test_batch_child_documents_offset_page_by_prior_image_media():
    # child 0 has one .jpg page -> child 1's PageIndex 0 maps to global page 1.
    child0 = {
        "Media": [{"Extension": ".jpg", "Url": "u0"}],
        "IndexFields": [_field("DocNo", "A", _loc(0, [(1, 1, 5, 5)]))],
    }
    child1 = {
        "Media": [{"Extension": ".jpg", "Url": "u1"}],
        "IndexFields": [_field("DocDate", "B", _loc(0, [(2, 2, 6, 6)]))],
    }
    doc = {"DocumentType": "Batch", "ChildDocuments": [child0, child1]}
    out = {o["key"]: o for o in extract_field_locations(doc, MAPPING)}
    assert out["Doc number"]["locations"][0]["page"] == 0  # child0, offset 0
    assert out["Doc date"]["locations"][0]["page"] == 1  # child1, offset +1
