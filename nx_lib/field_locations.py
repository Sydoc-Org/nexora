"""Pure helpers that turn the Octopus thin-document JSON into field source
locations. No Flask / HTTP here so it can be unit-tested in isolation.

Coordinates live at ``IndexField.Location`` (an ``DtoImageBasedLocation``) as
``Rectangle`` / ``Rectangles`` ``{Left, Top, Width, Height}`` in **image
pixels**, origin top-left, with the page given by ``Location.PageIndex``
(0-based). We ship raw pixel rects; the front-end normalizes them against the
page image's ``naturalWidth`` / ``naturalHeight``. See the design spec's
"Verified coordinate shape" section.
"""

# Mirror the image extensions used by octo.get_extensions_urls_fields so that
# our page indices line up with the order media URLs are collected.
IMG_EXTS = (".jpg", ".jpeg", ".png", ".tif")


def _num(v):
    """Return v as float, or None if not a finite number."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return f


def _confidence(fobj):
    """Extraction confidence for an IndexField as a 0..1 float, or None.

    Octopus exposes ``Confidence`` on the IndexField; some pipelines put it on
    ``FieldValue`` instead, so try both. Scales vary (a 0..1 fraction or a 0..100
    percent), so normalize to a 0..1 fraction the UI can bucket into
    high/medium/low. Returns None when absent, unparseable, or negative."""
    raw = fobj.get("Confidence")
    if raw is None:
        raw = (fobj.get("FieldValue") or {}).get("Confidence")
    c = _num(raw)
    if c is None or c < 0:
        return None
    if c > 1:  # 0..100 percent scale -> fraction
        c = c / 100.0
    return min(c, 1.0)


def _rect_from_octo(r):
    """Validate one Octopus rectangle ``{Left,Top,Width,Height}`` (pixels).

    Returns ``{"left","top","width","height"}`` as ints, or None if the rect is
    missing, non-numeric, or degenerate (width/height <= 0 — e.g. the {0,0,0,0}
    rects that derived/inferred field values carry)."""
    if not isinstance(r, dict):
        return None
    left, top = _num(r.get("Left")), _num(r.get("Top"))
    width, height = _num(r.get("Width")), _num(r.get("Height"))
    if None in (left, top, width, height):
        return None
    if width <= 0 or height <= 0:
        return None
    return {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}


def _rects_from_location(loc):
    """Return the list of valid pixel rects from a Location object. Prefers
    ``Rectangles`` (multi-box), falls back to the single ``Rectangle``."""
    if not isinstance(loc, dict):
        return []
    raw = loc.get("Rectangles")
    if not raw:
        single = loc.get("Rectangle")
        raw = [single] if single else []
    out = []
    for r in raw:
        rect = _rect_from_octo(r)
        if rect is not None:
            out.append(rect)
    return out


def _items(doc_json):
    """Batch documents expose their pages via ChildDocuments; everything else
    is a single item."""
    if doc_json.get("DocumentType") == "Batch" and doc_json.get("ChildDocuments"):
        return doc_json["ChildDocuments"]
    return [doc_json]


def _count_image_media(item):
    return sum(
        1 for m in (item.get("Media") or []) if str(m.get("Extension", "")).lower() in IMG_EXTS
    )


def extract_field_locations(doc_json, field_mapping):
    """Build the field_sources list from an Octopus thin-document response.

    Returns ``[{key, label, value, locations:[{page, rect}], confidence?}]`` —
    one entry per mapped index field that has a (non-None) value, mirroring the
    existing ``fields`` dict (first occurrence of a target key wins).
    ``locations == []`` means the field has no usable coordinates (un-locatable).
    ``rect`` is in image pixels; ``page`` is the 0-based media index (matching
    api_get_media_raw). ``confidence`` (optional, 0..1) is present only when
    Octopus reports an extraction confidence; the UI colours boxes by it.
    """
    out = []
    seen = set()
    media_offset = 0  # image media in prior child items (Batch page alignment)
    for item in _items(doc_json):
        for fobj in item.get("IndexFields") or []:
            name = fobj.get("Name")
            if name not in field_mapping:
                continue
            key = field_mapping[name]
            value = (fobj.get("FieldValue") or {}).get("Text")
            if value is None:
                continue  # mirror the existing fields dict (only set values shown)
            if key in seen:
                continue
            seen.add(key)
            loc = fobj.get("Location") or fobj.get("CapturedLocation")
            locations = []
            if isinstance(loc, dict):
                page_index = _num(loc.get("PageIndex"))
                if page_index is not None:
                    page = media_offset + int(page_index)
                    for rect in _rects_from_location(loc):
                        locations.append({"page": page, "rect": rect})
            entry = {"key": key, "label": key, "value": value, "locations": locations}
            conf = _confidence(fobj)
            if conf is not None:
                entry["confidence"] = conf  # optional: 0..1, drives box colour in the UI
            out.append(entry)
        media_offset += _count_image_media(item)
    return out


# Public aliases so the sibling table_locations parser can share one
# implementation of rect / confidence / page-offset handling (DRY) instead of
# copy-pasting. Behaviour is identical; the underscore names stay for existing
# callers/tests.
num = _num
rect_from_octo = _rect_from_octo
confidence_of = _confidence
items_of = _items
count_image_media = _count_image_media
