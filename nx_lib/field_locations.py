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
    """Flatten a thin-document tree to the leaf documents that actually carry
    pages + index fields, in pre-order.

    A document with a non-empty ``ChildDocuments`` list is a *container* and
    contributes nothing itself — we descend into its children, recursively, to
    any depth. A document with no children is a leaf and represents itself.

    This generalises the original one-level ``DocumentType == "Batch"`` switch:
    an Octo "Batch" is just a container one level deep, while client document
    trees can nest further (e.g. MS02's ``MobScnBatch`` -> ``MobScnDossier`` ->
    ``MobScnDocument``). Gating on the *presence of children* rather than a
    literal type name flattens both the same way, so the page images and field
    values of the leaf documents surface on the parent workitem regardless of
    how the client names its container types. One-level batches and plain
    single documents are unaffected (same leaves, same order)."""
    children = doc_json.get("ChildDocuments")
    if children:
        leaves = []
        for child in children:
            leaves.extend(_items(child))
        return leaves
    return [doc_json]


def _pdf_pages_for(pdf_page_counts, idx):
    """Look up the pre-computed PDF page count for leaf item ``idx`` in
    ``pdf_page_counts`` (see ``extract_field_locations``), or 0 when absent /
    out of range (no PDF data supplied, or a shorter sequence than expected)."""
    if pdf_page_counts is None or idx >= len(pdf_page_counts):
        return 0
    return pdf_page_counts[idx]


def _count_image_media(item, pdf_pages=0):
    """Media-slot count for one leaf item: 1 slot per whitelisted image
    extension, plus ``pdf_pages`` slots for any PDF media in this item that
    were already expanded to per-page images upstream (see
    ``extract_field_locations``'s ``pdf_page_counts`` parameter). Defaults to
    the old IMG_EXTS-only behaviour (PDFs contribute 0) when the caller
    doesn't supply a PDF page count."""
    return (
        sum(1 for m in (item.get("Media") or []) if str(m.get("Extension", "")).lower() in IMG_EXTS)
        + pdf_pages
    )


def extract_field_locations(doc_json, field_mapping, pdf_page_counts=None):
    """Build the field_sources list from an Octopus thin-document response.

    Returns ``[{key, label, value, locations:[{page, rect}], confidence?}]`` —
    one entry per mapped index field that has a (non-None) value, mirroring the
    existing ``fields`` dict (first occurrence of a target key wins).
    ``locations == []`` means the field has no usable coordinates (un-locatable).
    ``rect`` is in image pixels; ``page`` is the 0-based media index (matching
    api_get_media_raw). ``confidence`` (optional, 0..1) is present only when
    Octopus reports an extraction confidence; the UI colours boxes by it.

    ``pdf_page_counts`` (optional): a sequence of ints, one per leaf item in the
    same order as ``_items(doc_json)`` produces them, giving the number of
    PDF-expanded page slots that item's PDF media occupy (real page counting is
    I/O — pypdfium2 over a fetched PDF — so it's computed once by the caller,
    typically octo.get_extensions_urls_fields, and threaded in here rather than
    done in this I/O-free module). Omit (or pass None) to keep the pre-fix
    behaviour where PDF media contribute 0 to the page offset.
    """
    out = []
    seen = set()
    media_offset = 0  # image (+ PDF-expanded) media in prior child items
    for idx, item in enumerate(_items(doc_json)):
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
        media_offset += _count_image_media(item, _pdf_pages_for(pdf_page_counts, idx))
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
pdf_pages_for = _pdf_pages_for
