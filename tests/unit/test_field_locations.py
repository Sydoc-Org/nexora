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


# --- nested / non-"Batch" container documents -----------------------------
# MS02 documents are a tree (MobScnBatch -> MobScnDossier -> MobScnDocument)
# whose page images + index fields live on the leaf documents, and whose types
# are NOT the literal "Batch". The flatten must recurse on any document that has
# children, to any depth, regardless of DocumentType.


def test_non_batch_container_recurses_to_leaf_fields():
    leaf = {
        "DocumentType": "MobScnDocument",
        "Media": [{"Extension": ".jpg", "Url": "u0"}],
        "IndexFields": [_field("DocNo", "INV-9", _loc(0, [(1, 1, 5, 5)]))],
    }
    dossier = {
        "DocumentType": "MobScnDossier",
        "Media": [],
        "IndexFields": [],
        "ChildDocuments": [leaf],
    }
    assert extract_field_locations(dossier, MAPPING) == [
        {
            "key": "Doc number",
            "label": "Doc number",
            "value": "INV-9",
            "locations": [{"page": 0, "rect": {"left": 1, "top": 1, "width": 5, "height": 5}}],
        }
    ]


def test_multi_level_container_offsets_pages_across_all_leaves():
    leaf_a = {
        "Media": [{"Extension": ".jpg", "Url": "a"}],
        "IndexFields": [_field("DocNo", "A", _loc(0, [(1, 1, 5, 5)]))],
    }
    leaf_b = {
        "Media": [{"Extension": ".jpg", "Url": "b"}],
        "IndexFields": [_field("DocDate", "B", _loc(0, [(2, 2, 6, 6)]))],
    }
    dossier1 = {"DocumentType": "MobScnDossier", "ChildDocuments": [leaf_a]}
    dossier2 = {"DocumentType": "MobScnDossier", "ChildDocuments": [leaf_b]}
    batch = {"DocumentType": "MobScnBatch", "ChildDocuments": [dossier1, dossier2]}
    out = {o["key"]: o for o in extract_field_locations(batch, MAPPING)}
    assert out["Doc number"]["locations"][0]["page"] == 0  # leaf_a, offset 0
    assert out["Doc date"]["locations"][0]["page"] == 1  # leaf_b, offset +1 (after leaf_a's image)


def test_container_own_media_and_fields_ignored():
    # A container's own media/fields are never emitted — only its leaves'
    # (mirrors the original Batch behavior, which ignored the batch root).
    leaf = {
        "Media": [{"Extension": ".jpg", "Url": "leaf"}],
        "IndexFields": [_field("DocNo", "leaf-val", _loc(0, [(1, 1, 5, 5)]))],
    }
    batch = {
        "DocumentType": "MobScnBatch",
        "Media": [{"Extension": ".jpg", "Url": "batch-cover"}],
        "IndexFields": [_field("DocNo", "batch-val", _loc(0, [(9, 9, 9, 9)]))],
        "ChildDocuments": [leaf],
    }
    assert extract_field_locations(batch, MAPPING) == [
        {
            "key": "Doc number",
            "label": "Doc number",
            "value": "leaf-val",
            "locations": [{"page": 0, "rect": {"left": 1, "top": 1, "width": 5, "height": 5}}],
        }
    ]


def test_empty_child_documents_treated_as_leaf():
    # ChildDocuments == [] is falsy -> the node is its own leaf, not a container.
    doc = {
        "DocumentType": "Single",
        "ChildDocuments": [],
        "IndexFields": [_field("DocNo", "X", _loc(0, [(1, 1, 5, 5)]))],
    }
    assert extract_field_locations(doc, MAPPING)[0]["value"] == "X"


# --- confidence (optional key) --------------------------------------------


def _field_conf(name, text, confidence, location=None):
    f = _field(name, text, location)
    f["Confidence"] = confidence
    return f


def test_confidence_fraction_scale_passthrough():
    doc = {"IndexFields": [_field_conf("DocNo", "INV", 0.91, _loc(0, [(1, 1, 5, 5)]))]}
    assert extract_field_locations(doc, MAPPING)[0]["confidence"] == 0.91


def test_confidence_percent_scale_normalized():
    doc = {"IndexFields": [_field_conf("DocNo", "INV", 91, _loc(0, [(1, 1, 5, 5)]))]}
    assert extract_field_locations(doc, MAPPING)[0]["confidence"] == 0.91


def test_confidence_clamped_to_one():
    doc = {"IndexFields": [_field_conf("DocNo", "INV", 150, _loc(0, [(1, 1, 5, 5)]))]}
    assert extract_field_locations(doc, MAPPING)[0]["confidence"] == 1.0


def test_confidence_absent_key_omitted():
    doc = {"IndexFields": [_field("DocNo", "INV", _loc(0, [(1, 1, 5, 5)]))]}
    assert "confidence" not in extract_field_locations(doc, MAPPING)[0]


def test_confidence_negative_is_omitted():
    doc = {"IndexFields": [_field_conf("DocNo", "INV", -1, _loc(0, [(1, 1, 5, 5)]))]}
    assert "confidence" not in extract_field_locations(doc, MAPPING)[0]


def test_confidence_from_fieldvalue_fallback():
    f = _field("DocNo", "INV", _loc(0, [(1, 1, 5, 5)]))
    f["FieldValue"]["Confidence"] = 80  # IndexField has no Confidence; FieldValue does
    out = extract_field_locations({"IndexFields": [f]}, MAPPING)
    assert out[0]["confidence"] == 0.8


def test_confidence_present_on_unlocatable_field():
    # confidence is independent of whether the field has usable coordinates
    doc = {"IndexFields": [_field_conf("DocNo", "INV", 0.6, location=None)]}
    out = extract_field_locations(doc, MAPPING)
    assert out[0]["locations"] == [] and out[0]["confidence"] == 0.6
