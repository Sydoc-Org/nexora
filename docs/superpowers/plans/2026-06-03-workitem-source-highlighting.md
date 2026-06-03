# Workitem Source Highlighting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only "show sources" toggle to the workitems document viewer that overlays highlight boxes on the page image showing exactly where each extracted index-field value was found.

**Architecture:** Capture the positional data already returned by the Octopus document-service call (currently discarded in `get_extensions_urls_fields`), normalize every bounding box to 0–1 fractions of page size in a pure, unit-tested helper, and ship it in `api_get_media_info` as a `field_sources` array. The front-end renders absolutely-positioned overlay `<div>`s scaled to the rendered image size, in both the `#imageModal` lightbox and the page thumbnails.

**Tech Stack:** Flask (route in `nx_lib/views/workitems.py`), Octopus client (`nx_lib/octo.py`), new pure helper module (`nx_lib/field_locations.py`), Jinja templates + vanilla JS (`templates/workitems_overview.html`, `templates/js/_workitems_overview_js.html`), Flask-Babel i18n, pytest (unit) + Playwright (e2e).

**Spec:** `docs/superpowers/specs/2026-06-03-workitem-source-highlighting-design.md`

**Branch:** `feature/2.5.63.1` (a concurrent session is actively editing `workitems_overview.html`, `_ui.html`, `nexora-ui.css`). **Mitigation:** for every task that edits a shared front-end file, RE-READ the file immediately before editing, anchor edits on element IDs / function names (not line numbers), keep edits narrow and append-only where possible, and commit immediately after each task. Put all new CSS in a **new** file (`static/css/source-highlight.css`), never in `nexora-ui.css`.

---

## File Structure

- **Create** `nx_lib/field_locations.py` — pure functions: `normalize_rect(...)` (math, no I/O) and `extract_field_locations(doc_json, field_mapping)` (parses the Octopus document JSON into a `field_sources` list). No Flask, no HTTP — fully unit-testable.
- **Modify** `nx_lib/octo.py` — `get_extensions_urls_fields` calls `extract_field_locations` on the `doc_json` it already fetches and returns it as a 4th tuple element.
- **Modify** `nx_lib/views/workitems.py` — `api_get_media_info` includes `field_sources` (permission-suppressed) and caches it.
- **Create** `static/css/source-highlight.css` — highlight box + pulse styles (isolated from the contested `nexora-ui.css`).
- **Modify** `templates/workitems_overview.html` — link the new CSS; add the "Show sources" toggle button + overlay container to `#imageModal`; mark up the field list for click-to-locate.
- **Modify** `templates/js/_workitems_overview_js.html` — store `field_sources`, render overlays (lightbox + thumbnails), click-to-locate, `localStorage` toggle.
- **Create** `tests/unit/test_field_locations.py` — `normalize_rect` + `extract_field_locations`.
- **Create** `tests/unit/test_media_info_field_sources.py` — `api_get_media_info` payload + permission suppression (mocked Octopus).
- **Create** `tests/e2e/test_workitem_source_highlight.py` — toggle + click-to-locate in the browser.
- **Modify** `messages.pot` + `translations/{de,fr,it}/LC_MESSAGES/messages.po` — new UI strings.
- **Modify** `CHANGELOG.md`, `docs/howto/` (if a workitems how-to exists), `CLAUDE.md` (workitems section) — docs.

**Internal data contract** (the shape `field_sources` carries end to end):

```python
# one entry per mapped index field
{
    "key": "Invoice number",        # target key (also used as label)
    "label": "Invoice number",
    "value": "INV-001",             # FieldValue.Text (may be None/"")
    "locations": [                  # [] => un-locatable
        {"page": 0, "rect": {"x": 0.62, "y": 0.08, "w": 0.18, "h": 0.03}},
    ],
}
```
`page` is the 0-based media index (matches `api_get_media_raw`). `rect` is normalized 0–1, origin top-left.

---

### Task 1: Spike — verify the Octopus coordinate shape on live INT

**Goal:** Discover, against a real INT document, (a) exactly which JSON keys carry per-field coordinates, (b) their unit (pixels / points / normalized), (c) the origin (top-left vs bottom-left), (d) whether page dimensions are present, and (e) whether page orientation is applied. This pins down the five key-name constants in Task 3. **No production code is written or committed in this task.**

**Files:**
- Create (throwaway, DO NOT COMMIT): `scratch_probe_octo.py`

- [ ] **Step 1: Find a real workitem id that has media + extracted fields**

Run (read-only):
```bash
python -c "from nx_lib.config import *; import nx_lib.db as db; \
c=db.engine_octo_ro.raw_connection().cursor(); \
c.execute('SELECT TOP 5 WorkItemID FROM WorkItems ORDER BY WorkItemID DESC'); \
print([r[0] for r in c.fetchall()])"
```
Expected: a list of recent workitem ids. If `engine_octo_ro` is not provisioned, instead read an id from the workitems page in the browser (`nx -u -b --loginas:<user>` → open `/workitems`). Record one id as `WID`.

- [ ] **Step 2: Dump the document JSON structure for that workitem**

Create `scratch_probe_octo.py`:
```python
import json, os
os.environ.setdefault("ENVIRONMENT", "INT")
from nx_lib.octo import get_workitemdata_param, get_access_token, OCTO_DOMAIN
import requests

WID = 0  # <-- set to the id from Step 1
workitemdata, document_id = get_workitemdata_param(WID)
url = (f"https://{OCTO_DOMAIN}/api/documentservice/api/v2.1/documentService/thin/Document/"
       f"{document_id}?WithExtensions=true&WithDocumentStructure=true&WithTables=false"
       f"&WithDocumentAudits=true&LoadMediaStreams=true")
token = get_access_token()
r = requests.get(url, headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json",
                               "workitemdata": workitemdata}, timeout=20)
doc = r.json()
items = doc.get("ChildDocuments") or [doc]
for it in items:
    for f in (it.get("IndexFields") or []):
        # Print the FULL field object so we can see where coordinates live
        print(json.dumps(f, indent=2, default=str)[:4000])
        print("=" * 60)
    # page/media dimensions
    for m in (it.get("Media") or []):
        print("MEDIA keys:", list(m.keys()))
        print({k: m.get(k) for k in ("Extension", "Width", "Height", "PageNumber", "Url")})
```
Run: `python scratch_probe_octo.py`
Expected: printed `IndexFields` objects. Inspect them.

- [ ] **Step 3: Record findings in the spec**

In `docs/superpowers/specs/2026-06-03-workitem-source-highlighting-design.md`, under "Risks", append a "## Verified coordinate shape (INT)" section recording the real key paths, e.g.:
- Per-field rectangles live at: `FieldValue.Zones[].{Left,Top,Right,Bottom}` (CONFIRM/CORRECT)
- Page index key: `Zone.Page` (0- or 1-based — CONFIRM)
- Unit: image pixels (CONFIRM)
- Origin: top-left (CONFIRM)
- Page dimensions from: `Media[].Width/Height` or `Page.Width/Height` (CONFIRM)
- Whether `WithExtensions=true` was required (the current call uses `false`) and payload delta.

- [ ] **Step 4: Delete the scratch file and commit the spec finding**

```bash
rm scratch_probe_octo.py
git add docs/superpowers/specs/2026-06-03-workitem-source-highlighting-design.md
git commit -m "docs(workitems): record verified Octopus coordinate shape for source highlighting"
```
Expected: clean commit, no `scratch_probe_octo.py` tracked.

> If Step 3 reveals the shape differs from the assumptions in Tasks 2–3, adjust the constants/keys in Task 3 (`_ZONES_KEY`, `_PAGE_KEY`, etc.) and the `origin`/unit handling before implementing. The pure `normalize_rect` math in Task 2 is shape-independent and needs no change.

---

### Task 2: Pure `normalize_rect` helper (TDD)

**Files:**
- Create: `nx_lib/field_locations.py`
- Test: `tests/unit/test_field_locations.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_field_locations.py`:
```python
from nx_lib.field_locations import normalize_rect


def test_normalize_top_left_basic():
    r = normalize_rect(100, 50, 200, 30, page_w=1000, page_h=800, origin="top-left")
    assert r == {"x": 0.1, "y": 0.0625, "w": 0.2, "h": 0.0375}


def test_normalize_bottom_left_flips_y():
    # bottom-left: y is distance from page bottom to the box's bottom edge
    r = normalize_rect(100, 50, 200, 30, page_w=1000, page_h=800, origin="bottom-left")
    # top-left y = (800 - 50 - 30) / 800 = 720/800 = 0.9
    assert r["y"] == 0.9
    assert r["x"] == 0.1 and r["w"] == 0.2 and r["h"] == 0.0375


def test_normalize_clamps_into_unit_range():
    r = normalize_rect(-10, -10, 1020, 810, page_w=1000, page_h=800, origin="top-left")
    assert r == {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}


def test_normalize_rejects_zero_area():
    assert normalize_rect(10, 10, 0, 30, page_w=1000, page_h=800) is None
    assert normalize_rect(10, 10, 200, 0, page_w=1000, page_h=800) is None


def test_normalize_rejects_bad_page_dims():
    assert normalize_rect(10, 10, 20, 20, page_w=0, page_h=800) is None
    assert normalize_rect(10, 10, 20, 20, page_w=1000, page_h=None) is None


def test_normalize_rejects_non_numeric():
    assert normalize_rect("a", 10, 20, 20, page_w=1000, page_h=800) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_field_locations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nx_lib.field_locations'`.

- [ ] **Step 3: Implement `normalize_rect`**

Create `nx_lib/field_locations.py`:
```python
"""Pure helpers that turn the Octopus document JSON into normalized field
source locations. No Flask / HTTP here so it can be unit-tested in isolation.

A "location" is a bounding box normalized to fractions of the page (0..1,
origin top-left) plus the 0-based page index it sits on.
"""


def _num(v):
    """Return v as float, or None if not a finite number."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return f


def _clamp01(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def normalize_rect(x, y, w, h, page_w, page_h, origin="top-left"):
    """Normalize a pixel-space box to 0..1 fractions of the page, origin
    top-left. Returns {"x","y","w","h"} or None if the box or page dims are
    invalid (non-numeric, zero/negative area, or zero page size)."""
    x, y, w, h = _num(x), _num(y), _num(w), _num(h)
    pw, ph = _num(page_w), _num(page_h)
    if None in (x, y, w, h, pw, ph):
        return None
    if pw <= 0 or ph <= 0 or w <= 0 or h <= 0:
        return None
    if origin == "bottom-left":
        y = ph - y - h
    nx = _clamp01(x / pw)
    ny = _clamp01(y / ph)
    nw = _clamp01(w / pw)
    nh = _clamp01(h / ph)
    # Clamp width/height so x+w and y+h stay within the page.
    nw = min(nw, 1.0 - nx)
    nh = min(nh, 1.0 - ny)
    if nw <= 0 or nh <= 0:
        return None
    return {"x": round(nx, 6), "y": round(ny, 6), "w": round(nw, 6), "h": round(nh, 6)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_field_locations.py -v`
Expected: PASS (6 passed). Note: `test_normalize_clamps_into_unit_range` expects `{0,0,1,1}` — the width clamp keeps `nw = min(1.0, 1.0-0.0) = 1.0`. Confirm the rounding yields exactly `0.0`/`1.0`.

- [ ] **Step 5: Commit**

```bash
git add nx_lib/field_locations.py tests/unit/test_field_locations.py
git commit -m "feat(workitems): pure normalize_rect helper for source locations"
```

---

### Task 3: `extract_field_locations` parser (TDD)

**Files:**
- Modify: `nx_lib/field_locations.py`
- Test: `tests/unit/test_field_locations.py`

> The key-name constants below reflect the EXPECTED Octopus shape. If Task 1 found different names/units/origin, change ONLY the constants and the `origin=`/unit handling here.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_field_locations.py`:
```python
from nx_lib.field_locations import extract_field_locations

# Mirrors the Octopus thin-document shape (confirm against Task 1 findings).
def _field(name, text, zones):
    return {"Name": name, "FieldValue": {"Text": text, "Zones": zones}}

def _zone(page, left, top, right, bottom):
    return {"Page": page, "Left": left, "Top": top, "Right": right, "Bottom": bottom}

MAPPING = {"InvoiceNo": "Invoice number", "Total": "Total", "Notes": "Notes"}


def test_extract_single_zone_field():
    doc = {"Media": [{"Width": 1000, "Height": 800, "Extension": ".jpg"}],
           "IndexFields": [_field("InvoiceNo", "INV-001", [_zone(0, 620, 80, 800, 104)])]}
    out = extract_field_locations(doc, MAPPING)
    assert out == [{
        "key": "Invoice number", "label": "Invoice number", "value": "INV-001",
        "locations": [{"page": 0, "rect": {"x": 0.62, "y": 0.1, "w": 0.18, "h": 0.03}}],
    }]


def test_unlocatable_field_has_empty_locations():
    doc = {"Media": [{"Width": 1000, "Height": 800}],
           "IndexFields": [_field("Total", "1234.50", [])]}
    out = extract_field_locations(doc, MAPPING)
    assert out == [{"key": "Total", "label": "Total", "value": "1234.50", "locations": []}]


def test_multi_zone_field_yields_multiple_boxes():
    doc = {"Media": [{"Width": 1000, "Height": 800}],
           "IndexFields": [_field("Notes", "two lines",
                                  [_zone(0, 10, 10, 110, 40), _zone(1, 10, 50, 210, 80)])]}
    out = extract_field_locations(doc, MAPPING)
    assert len(out[0]["locations"]) == 2
    assert out[0]["locations"][0]["page"] == 0
    assert out[0]["locations"][1]["page"] == 1


def test_unmapped_field_is_skipped():
    doc = {"Media": [{"Width": 1000, "Height": 800}],
           "IndexFields": [_field("InternalId", "x", [_zone(0, 1, 1, 2, 2)])]}
    assert extract_field_locations(doc, MAPPING) == []


def test_malformed_zone_dropped_but_field_kept():
    doc = {"Media": [{"Width": 1000, "Height": 800}],
           "IndexFields": [_field("InvoiceNo", "INV-001",
                                  [{"Page": 0, "Left": "?", "Top": 1, "Right": 2, "Bottom": 2}])]}
    out = extract_field_locations(doc, MAPPING)
    assert out[0]["locations"] == []  # bad zone dropped, field still present


def test_batch_child_documents_are_processed():
    child = {"Media": [{"Width": 1000, "Height": 800}],
             "IndexFields": [_field("InvoiceNo", "INV-9", [_zone(0, 100, 100, 200, 130)])]}
    doc = {"DocumentType": "Batch", "ChildDocuments": [child]}
    out = extract_field_locations(doc, MAPPING)
    assert out and out[0]["value"] == "INV-9" and out[0]["locations"]


def test_missing_page_dims_makes_field_unlocatable():
    doc = {"Media": [{"Extension": ".jpg"}],  # no Width/Height
           "IndexFields": [_field("InvoiceNo", "INV-001", [_zone(0, 1, 1, 2, 2)])]}
    out = extract_field_locations(doc, MAPPING)
    assert out[0]["locations"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_field_locations.py -k extract -v`
Expected: FAIL — `ImportError: cannot import name 'extract_field_locations'`.

- [ ] **Step 3: Implement `extract_field_locations`**

Append to `nx_lib/field_locations.py`:
```python
# --- Octopus thin-document key names (confirm/adjust per Task 1) -----------
_ZONES_KEY = "Zones"        # IndexField.FieldValue[_ZONES_KEY]
_PAGE_KEY = "Page"          # Zone[_PAGE_KEY] (0-based; if 1-based, subtract 1 below)
_LEFT, _TOP, _RIGHT, _BOTTOM = "Left", "Top", "Right", "Bottom"
_COORD_ORIGIN = "top-left"  # or "bottom-left"
_PAGE_1_BASED = False       # set True if Task 1 shows pages are 1-based


def _page_dims(item):
    """Return [(w, h), ...] indexed by page from the item's Media list, or []
    if dimensions are absent. Index aligns with api_get_media_raw media_index
    (image media only)."""
    dims = []
    for m in (item.get("Media") or []):
        ext = str(m.get("Extension", "")).lower()
        if ext in (".jpg", ".jpeg", ".png", ".tif"):
            dims.append((_num(m.get("Width")), _num(m.get("Height"))))
    return dims


def _items(doc_json):
    if doc_json.get("DocumentType") == "Batch" and doc_json.get("ChildDocuments"):
        return doc_json["ChildDocuments"]
    return [doc_json]


def extract_field_locations(doc_json, field_mapping):
    """Build the field_sources list from an Octopus thin-document response.

    Returns [{key, label, value, locations:[{page, rect}]}], one entry per
    mapped index field present in the document. locations == [] means the
    field has no usable coordinates (un-locatable)."""
    out = []
    seen = set()
    for item in _items(doc_json):
        dims = _page_dims(item)
        for fobj in (item.get("IndexFields") or []):
            source_name = fobj.get("Name")
            if source_name not in field_mapping:
                continue
            key = field_mapping[source_name]
            if key in seen:
                continue
            seen.add(key)
            fv = fobj.get("FieldValue") or {}
            value = fv.get("Text")
            locations = []
            for z in (fv.get(_ZONES_KEY) or []):
                page = z.get(_PAGE_KEY)
                page = _num(page)
                if page is None:
                    continue
                page = int(page) - (1 if _PAGE_1_BASED else 0)
                left, top = z.get(_LEFT), z.get(_TOP)
                right, bottom = z.get(_RIGHT), z.get(_BOTTOM)
                lf, tp, rt, bt = _num(left), _num(top), _num(right), _num(bottom)
                if None in (lf, tp, rt, bt):
                    continue
                pw, ph = (dims[page] if 0 <= page < len(dims) else (None, None))
                rect = normalize_rect(lf, tp, rt - lf, bt - tp, pw, ph, origin=_COORD_ORIGIN)
                if rect is None:
                    continue
                locations.append({"page": page, "rect": rect})
            out.append({"key": key, "label": key, "value": value, "locations": locations})
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_field_locations.py -v`
Expected: PASS (all 13 tests).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/field_locations.py tests/unit/test_field_locations.py
git commit -m "feat(workitems): parse Octopus index-field coordinates into source locations"
```

---

### Task 4: Wire `field_sources` through the Octopus client

**Files:**
- Modify: `nx_lib/octo.py` (`get_extensions_urls_fields`, ~line 100)

- [ ] **Step 1: Run impact analysis (CLAUDE.md GitNexus rule)**

Run the GitNexus impact tool on the function before editing:
`gitnexus_impact({target: "get_extensions_urls_fields", direction: "upstream"})`
Expected: report listing callers (`api_get_media_info`, `api_get_media_raw`). Confirm both are updated in this task / Task 5. Report the risk level to the user if HIGH/CRITICAL.

- [ ] **Step 2: Re-read the function and add the parse call**

In `nx_lib/octo.py`, add the import at the top:
```python
from .field_locations import extract_field_locations
```
Then change `get_extensions_urls_fields` to compute and return `field_sources`. Replace the `return extensions, urls, fields` line with:
```python
    field_sources = extract_field_locations(doc_json, field_mapping)
    return extensions, urls, fields, field_sources
```
And change the early error return `return [], [], {}` to:
```python
        return [], [], {}, []
```

- [ ] **Step 3: Update the call site in `api_get_media_raw`**

In `nx_lib/views/workitems.py`, `api_get_media_raw` unpacks the tuple in two places (the cache-miss branch). Re-read the function and change each:
```python
extensions, urls, fields = get_extensions_urls_fields(workitemdata, document_id, domain)
```
to:
```python
extensions, urls, fields, _field_sources = get_extensions_urls_fields(workitemdata, document_id, domain)
```
(`api_get_media_raw` does not use field_sources; the `_` makes that explicit.)

- [ ] **Step 4: Verify nothing else unpacks the 3-tuple**

Run: `git grep -n "get_extensions_urls_fields" -- "*.py"`
Expected: only `nx_lib/octo.py` (def), `nx_lib/views/workitems.py` (the two media routes). Each call site now unpacks 4 values.

- [ ] **Step 5: Run the existing workitems tests**

Run: `python -m pytest tests/unit -k "media or workitem" -v`
Expected: PASS (no regressions). If a test mocks `get_extensions_urls_fields` to return a 3-tuple, update the mock to a 4-tuple.

- [ ] **Step 6: Commit**

```bash
git add nx_lib/octo.py nx_lib/views/workitems.py
git commit -m "feat(workitems): return field_sources from Octopus document fetch"
```

---

### Task 5: Expose `field_sources` in `api_get_media_info` with permission suppression (TDD)

**Files:**
- Modify: `nx_lib/views/workitems.py` (`api_get_media_info`, ~line 975)
- Test: `tests/unit/test_media_info_field_sources.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_media_info_field_sources.py`:
```python
import pytest
from nx_lib import create_app


@pytest.fixture
def client(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app.test_client()


SOURCES = [
    {"key": "Invoice number", "label": "Invoice number", "value": "INV-1",
     "locations": [{"page": 0, "rect": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05}}]},
    {"key": "Total", "label": "Total", "value": "9.99", "locations": []},
]


def _patch_octo(monkeypatch, perms):
    import nx_lib.views.workitems as w
    monkeypatch.setattr(w, "get_domain_for_workitem", lambda wid: "d")
    monkeypatch.setattr(w, "get_workitemdata_param", lambda wid, dom: ("wd", "doc1"))
    monkeypatch.setattr(
        w, "get_extensions_urls_fields",
        lambda *a, **k: ([".jpg"], ["u0"], {"Invoice number": "INV-1", "Total": "9.99"}, SOURCES),
    )
    monkeypatch.setattr(w, "has_permission", lambda code: code in perms)
    w.cache.clear()


def test_media_info_includes_field_sources(client, monkeypatch):
    _patch_octo(monkeypatch, {"workitems.details.view", "workitems.details.view.images",
                              "workitems.details.view.fields"})
    with client.session_transaction() as s:
        s["userid"], s["username"] = "1", "tester"
    r = client.get("/api/get_media_info/123")
    assert r.status_code == 200
    data = r.get_json()
    assert data["field_sources"] == SOURCES


def test_field_sources_empty_without_fields_perm(client, monkeypatch):
    _patch_octo(monkeypatch, {"workitems.details.view", "workitems.details.view.images"})
    with client.session_transaction() as s:
        s["userid"], s["username"] = "1", "tester"
    r = client.get("/api/get_media_info/123")
    assert r.get_json()["field_sources"] == []


def test_locations_stripped_without_images_perm(client, monkeypatch):
    _patch_octo(monkeypatch, {"workitems.details.view", "workitems.details.view.fields"})
    with client.session_transaction() as s:
        s["userid"], s["username"] = "1", "tester"
    r = client.get("/api/get_media_info/123")
    srcs = r.get_json()["field_sources"]
    assert srcs and all(s["locations"] == [] for s in srcs)  # values kept, boxes removed
```

> If the route's permission decorator (`@require_permission("workitems.details.view")`) or session keys differ from the above, re-read `api_get_media_info` and align the fixture. Confirm the URL rule name (`/api/get_media_info/<workitem_id>`) in `register_routes`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/test_media_info_field_sources.py -v`
Expected: FAIL — `KeyError: 'field_sources'` (route doesn't return it yet).

- [ ] **Step 3: Implement in `api_get_media_info`**

Re-read `api_get_media_info`. Update the unpack and response build. Change:
```python
extensions, urls, fields = get_extensions_urls_fields(workitemdata, document_id, domain)
```
to:
```python
extensions, urls, fields, field_sources = get_extensions_urls_fields(workitemdata, document_id, domain)
```
Add `field_sources` to `response_data` (the dict that gets cached):
```python
        response_data = {
            "workitem_id": workitem_id,
            "media_count": media_count,
            "fields": fields,
            "field_sources": field_sources,
        }
```
Apply permission suppression in BOTH the cache-hit branch and the fresh branch. After computing `filtered_response` (and in the cached `response_data.copy()` branch), add:
```python
        # field_sources: need fields perm to see them at all; need images perm
        # to see WHERE (the boxes) since highlighting requires the page image.
        if not can_view_fields:
            filtered_response["field_sources"] = []
        elif not can_view_images:
            filtered_response["field_sources"] = [
                {**s, "locations": []} for s in filtered_response.get("field_sources", [])
            ]
```
Make sure the cache-hit branch (top of the function) applies the same suppression to its `response_data.copy()` before returning. Refactor the suppression into a local helper `def _suppress(d):` inside the function and call it in both branches to stay DRY.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/test_media_info_field_sources.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/views/workitems.py tests/unit/test_media_info_field_sources.py
git commit -m "feat(workitems): expose field_sources in media_info with perm suppression"
```

---

### Task 6: Highlight CSS + lightbox overlay scaffold

**Files:**
- Create: `static/css/source-highlight.css`
- Modify: `templates/workitems_overview.html` (link CSS; add toggle + overlay to `#imageModal`)

- [ ] **Step 1: Create the CSS**

Create `static/css/source-highlight.css`:
```css
/* Source-highlight overlay for the workitems document viewer.
   Kept in its own file to avoid colliding with nexora-ui.css. */
.src-hl-wrap { position: relative; display: inline-block; line-height: 0; }
.src-hl-box {
  position: absolute;
  border: 2px solid rgba(234, 88, 12, 0.9);      /* orange-600 */
  background: rgba(234, 88, 12, 0.18);
  border-radius: 2px;
  pointer-events: none;
  box-sizing: border-box;
  transition: opacity .15s ease;
}
.src-hl-box.is-pulse { animation: srcHlPulse 1.1s ease-out 2; }
@keyframes srcHlPulse {
  0%   { box-shadow: 0 0 0 0 rgba(234, 88, 12, 0.55); }
  100% { box-shadow: 0 0 0 14px rgba(234, 88, 12, 0); }
}
.src-hl-toggle.is-on { background: rgba(234, 88, 12, 0.15); color: #c2410c; }
.src-field-row.is-locatable { cursor: pointer; }
.src-field-row.is-locatable:hover { background: rgba(234, 88, 12, 0.06); }
.src-no-loc-badge {
  font-size: .65rem; padding: 0 .35rem; border-radius: 9999px;
  background: #f3f4f6; color: #9ca3af; margin-left: .35rem; white-space: nowrap;
}
```

- [ ] **Step 2: Link the CSS in the page `<head>`**

Re-read `templates/workitems_overview.html`. Next to the existing favicon/`<link>` lines in `<head>`, add:
```html
  <link rel="stylesheet" href="{{ url_for('static', filename='css/source-highlight.css') }}">
```

- [ ] **Step 3: Add the toggle button + overlay wrapper to `#imageModal`**

Re-read the `#imageModal` block (currently `#modalImage` + `.modal-prev` / `.modal-next`). Wrap the image so overlays can be positioned over it, and add a toggle button. Replace the `<img ... id="modalImage">` with:
```html
      <button type="button" id="srcHlToggle" class="src-hl-toggle"
              title="{{ _('Show where extracted values were found') }}"
              data-testid="workitems-src-toggle">
        <i class="fas fa-magnifying-glass-location mr-1"></i>{{ _('Show sources') }}
      </button>
      <div id="modalImageWrap" class="src-hl-wrap">
        <img class="modal-content" id="modalImage">
        <div id="srcHlLayer"></div>
      </div>
```
(Keep `.modal-prev` / `.modal-next` / `.modal-close` as they are.)

- [ ] **Step 4: Verify the template renders (smoke)**

Restart the dev server (Jinja cache) and load the page:
```bash
nx -u
```
Then in a browser open `/workitems` (or drive Playwright). Expected: page loads, no template error; the toggle button is present in the image modal markup (it can be unstyled/non-functional at this step).

- [ ] **Step 5: Commit**

```bash
git add static/css/source-highlight.css templates/workitems_overview.html
git commit -m "feat(workitems): add source-highlight CSS and lightbox overlay scaffold"
```

> Add `static/css/source-highlight.css` to the deploy include set if needed — `static/` is already mirrored to prod, so no `deploy.yml` change is required. (Confirm `static/` is not in an `/XD` exclude.)

---

### Task 7: Render highlight boxes in the lightbox + toggle behavior

**Files:**
- Modify: `templates/js/_workitems_overview_js.html`

> This file is being edited by the concurrent session. RE-READ it immediately before editing. Add new functions; touch existing ones minimally.

- [ ] **Step 1: Store field_sources when media_info loads**

Re-read the media-info fetch block (where `mediaInfo.fields` is read, ~`const fields = mediaInfo.fields || {}`). Alongside it add:
```javascript
const fieldSources = mediaInfo.field_sources || [];
window.__srcByWorkitem = window.__srcByWorkitem || {};
window.__srcByWorkitem[workitemid] = fieldSources;
```

- [ ] **Step 2: Track current page + workitem in the lightbox**

Find where the image modal is opened (the `.workitem-image` click handler that sets `#modalImage.src` and the prev/next handlers). Ensure a module-scoped state object exists; add near the top of the IIFE:
```javascript
const srcHl = { workitemid: null, page: 0, on: localStorage.getItem('srcHlOn') === '1' };
```
In the open-modal handler, set `srcHl.workitemid` and `srcHl.page` (the media index being shown). In prev/next handlers, update `srcHl.page` then call `renderSrcOverlay()`.

- [ ] **Step 3: Implement the overlay renderer + toggle**

Append these functions inside the IIFE:
```javascript
function currentSources() {
  return (window.__srcByWorkitem && window.__srcByWorkitem[srcHl.workitemid]) || [];
}

function renderSrcOverlay(pulseKey) {
  const layer = document.getElementById('srcHlLayer');
  const img = document.getElementById('modalImage');
  if (!layer || !img) return;
  layer.innerHTML = '';
  const toggle = document.getElementById('srcHlToggle');
  if (toggle) toggle.classList.toggle('is-on', srcHl.on);
  if (!srcHl.on && !pulseKey) return;
  const w = img.clientWidth, h = img.clientHeight;
  if (!w || !h) return;  // image not laid out yet
  currentSources().forEach(src => {
    (src.locations || []).forEach(loc => {
      if (loc.page !== srcHl.page) return;
      const r = loc.rect;
      const box = document.createElement('div');
      box.className = 'src-hl-box' + (pulseKey && src.key === pulseKey ? ' is-pulse' : '');
      box.style.left = (r.x * w) + 'px';
      box.style.top = (r.y * h) + 'px';
      box.style.width = (r.w * w) + 'px';
      box.style.height = (r.h * h) + 'px';
      box.title = src.label + ': ' + (src.value == null ? '' : src.value);
      layer.appendChild(box);
    });
  });
}

function setSrcHl(on) {
  srcHl.on = on;
  localStorage.setItem('srcHlOn', on ? '1' : '0');
  renderSrcOverlay();
}
```

- [ ] **Step 4: Wire the toggle + re-render on image load/resize**

In the DOM-ready/init block, add:
```javascript
const _hlToggle = document.getElementById('srcHlToggle');
if (_hlToggle) _hlToggle.addEventListener('click', () => setSrcHl(!srcHl.on));
const _modalImg = document.getElementById('modalImage');
if (_modalImg) _modalImg.addEventListener('load', () => renderSrcOverlay());
window.addEventListener('resize', () => renderSrcOverlay());
```

- [ ] **Step 5: Manual verify (Playwright, drive it yourself)**

Restart dev server (Jinja cache), drive the browser per the remote-screenshot rule:
```bash
nx -u -b --loginas:<workitems-user>
```
Open `/workitems`, expand a workitem with media, open the image modal, click "Show sources". Expected: orange boxes appear over the page; toggling off clears them; prev/next keeps boxes on the correct page. Save a screenshot to `var/screenshots/source-highlight-lightbox.png` and send it to the user.

- [ ] **Step 6: Commit**

```bash
git add templates/js/_workitems_overview_js.html
git commit -m "feat(workitems): render source-highlight boxes in the document lightbox"
```

---

### Task 8: Thumbnails — full-page (object-contain) + overlay boxes

**Files:**
- Modify: `templates/js/_workitems_overview_js.html` (`loadImage`)
- Modify: `static/css/source-highlight.css`

- [ ] **Step 1: Switch thumbnails to object-contain inside a positioned wrapper**

Re-read `loadImage`. The image is created with class `'w-40 h-40 object-cover rounded shadow-lg workitem-image cursor-pointer'`. Change `object-cover` to `object-contain`, and wrap the `<img>` in a `div.src-hl-wrap.src-thumb` (so boxes can be absolutely positioned). After the image loads, build overlay boxes for that page (media index) using the stored sources, scaled to the rendered thumbnail. Add a `data-page` attribute = index.
```javascript
imgElement.className = 'w-40 h-40 object-contain rounded shadow-lg workitem-image cursor-pointer bg-gray-50';
```
Add a helper used on thumb load:
```javascript
function renderThumbOverlay(wrap, imgEl, workitemid, page) {
  const old = wrap.querySelector('.src-hl-layer-thumb');
  if (old) old.remove();
  if (localStorage.getItem('srcHlOn') !== '1') return;
  const srcs = (window.__srcByWorkitem && window.__srcByWorkitem[workitemid]) || [];
  const w = imgEl.clientWidth, h = imgEl.clientHeight;
  if (!w || !h) return;
  const layer = document.createElement('div');
  layer.className = 'src-hl-layer-thumb';
  srcs.forEach(s => (s.locations || []).forEach(loc => {
    if (loc.page !== page) return;
    const r = loc.rect, b = document.createElement('div');
    b.className = 'src-hl-box';
    b.style.left = (r.x*w)+'px'; b.style.top = (r.y*h)+'px';
    b.style.width = (r.w*w)+'px'; b.style.height = (r.h*h)+'px';
    layer.appendChild(b);
  }));
  wrap.appendChild(layer);
}
```
Call it from `imgElement.onload` (after `placeholder.replaceWith(...)`), passing the wrapper, image, `workitemid`, and `index`.

- [ ] **Step 2: CSS for the thumbnail layer**

Append to `static/css/source-highlight.css`:
```css
.src-thumb { position: relative; }
.src-hl-layer-thumb { position: absolute; inset: 0; pointer-events: none; }
.src-hl-layer-thumb .src-hl-box { border-width: 1.5px; }
```

- [ ] **Step 3: Re-render thumbnails when the global toggle flips**

In `setSrcHl(on)` (Task 7), after persisting, also refresh visible thumbnails:
```javascript
document.querySelectorAll('.src-thumb img.workitem-image').forEach(img => {
  const wrap = img.closest('.src-thumb');
  if (wrap) renderThumbOverlay(wrap, img, wrap.dataset.workitemid, parseInt(wrap.dataset.page || '0', 10));
});
```
Ensure the wrapper carries `data-workitemid` and `data-page` (set them when building the wrapper in `loadImage`).

- [ ] **Step 4: Manual verify (Playwright)**

Restart dev server. With "Show sources" on, expand a workitem: thumbnails show the full page (letterboxed, not cropped) with small boxes. Screenshot to `var/screenshots/source-highlight-thumbs.png` and send to the user.

- [ ] **Step 5: Commit**

```bash
git add templates/js/_workitems_overview_js.html static/css/source-highlight.css
git commit -m "feat(workitems): full-page thumbnails with source-highlight overlays"
```

> The `object-cover` → `object-contain` change alters existing thumbnail appearance. Check `tests/e2e/` for assertions on `.workitem-image` classes and update if any reference `object-cover`.

---

### Task 9: Field-list click-to-locate + un-locatable badge

**Files:**
- Modify: `templates/js/_workitems_overview_js.html` (the fields `<dl>` builder)

- [ ] **Step 1: Re-read the fields-render block**

Find where `fieldsHtml` is built (`for (const key in fields)` producing `<dt>`/`<dd>` rows). The values come from `mediaInfo.fields`; locations come from `field_sources`. Build a quick lookup: `const srcByKey = Object.fromEntries(fieldSources.map(s => [s.key, s]));`

- [ ] **Step 2: Mark rows locatable / un-locatable**

For each field row, look up `srcByKey[key]`. If it has ≥1 location, add class `src-field-row is-locatable`, `data-key="${key}"`, and `data-page` = its first location's page. If it has no locations, append a badge:
```javascript
const src = srcByKey[key];
const hasLoc = src && src.locations && src.locations.length > 0;
const rowCls = 'src-field-row' + (hasLoc ? ' is-locatable' : '');
const page = hasLoc ? src.locations[0].page : '';
const badge = (src && !hasLoc)
  ? `<span class="src-no-loc-badge">{{ _('no source location') }}</span>` : '';
// include in the row: <div class="${rowCls}" data-key="${key}" data-page="${page}"> ... ${label}${badge} ... </div>
```

- [ ] **Step 3: Click handler — open modal at the field's page and pulse**

Add a delegated listener on the fields container (or document) for `.src-field-row.is-locatable` clicks:
```javascript
document.addEventListener('click', (e) => {
  const row = e.target.closest('.src-field-row.is-locatable');
  if (!row) return;
  const fc = row.closest('[id^="fields-container-"]');
  if (!fc) return;
  const workitemid = fc.id.replace('fields-container-', '');
  const key = row.dataset.key;
  const page = parseInt(row.dataset.page || '0', 10);
  openDocModalAt(workitemid, page, key);  // see Step 4
});
```

- [ ] **Step 4: Implement `openDocModalAt`**

Reuse the existing open-modal logic. Implement a helper that loads the page image into `#modalImage`, sets `srcHl.workitemid`/`srcHl.page`, forces the overlay on for the pulse, and calls `renderSrcOverlay(key)`:
```javascript
function openDocModalAt(workitemid, page, pulseKey) {
  srcHl.workitemid = workitemid;
  srcHl.page = page;
  // open modal + set #modalImage.src to api/get_media_raw/{workitemid}/{page}
  // (call the SAME function the thumbnail click uses; if it's inline, factor it out)
  showDocModal(workitemid, page);   // existing/extracted open routine
  const img = document.getElementById('modalImage');
  const draw = () => renderSrcOverlay(pulseKey);
  if (img.complete && img.clientWidth) draw(); else img.addEventListener('load', draw, { once: true });
}
```
If the current open-modal logic is inline in the click handler, extract it into `showDocModal(workitemid, page)` and call it from both the thumbnail click and here (DRY).

- [ ] **Step 5: Manual verify (Playwright)**

Restart dev server. Expand a workitem, click a field value that has a location → modal opens at the right page, that field's box pulses. A field with no location shows the "no source location" badge and isn't clickable. Screenshot to `var/screenshots/source-highlight-click.png`, send to user.

- [ ] **Step 6: Commit**

```bash
git add templates/js/_workitems_overview_js.html
git commit -m "feat(workitems): click a field to locate its source on the document"
```

---

### Task 10: i18n — extract, translate, compile

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po`

New strings introduced: `Show sources`, `Show where extracted values were found`, `no source location`.

- [ ] **Step 1: Extract**

Run:
```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```
Expected: the three new msgids appear in each `messages.po`.

- [ ] **Step 2: Translate (non-fuzzy) in de/fr/it**

Edit each `translations/<lang>/LC_MESSAGES/messages.po`, fill the `msgstr` and remove any `#, fuzzy` flags. Suggested:
- de: `Quellen anzeigen`, `Anzeigen, wo die extrahierten Werte gefunden wurden`, `keine Fundstelle`
- fr: `Afficher les sources`, `Afficher où les valeurs extraites ont été trouvées`, `aucune source localisée`
- it: `Mostra origini`, `Mostra dove sono stati trovati i valori estratti`, `nessuna posizione di origine`

- [ ] **Step 3: Compile + test**

Run:
```bash
pybabel compile -d translations
python -m pytest test_translations.py -v
```
Expected: PASS (pot in sync; all msgids translated non-fuzzy in de/fr/it).

- [ ] **Step 4: Commit**

```bash
git add messages.pot translations
git commit -m "i18n(workitems): translate source-highlight strings (de/fr/it)"
```

---

### Task 11: e2e test

**Files:**
- Create: `tests/e2e/test_workitem_source_highlight.py`

> Re-read an existing e2e test (e.g. `tests/e2e/test_admin.py`) for the project's fixtures (app server fixture, login helper, base URL, page object). Mirror those conventions exactly. The test should NOT hit live Octopus — stub `field_sources` via the same mechanism other e2e media tests use (a monkeypatched route, a seeded NEXORA_TEST workitem, or a network stub).

- [ ] **Step 1: Write the e2e test**

Create `tests/e2e/test_workitem_source_highlight.py` following local conventions. Skeleton:
```python
# Conventions (login, server fixture, selectors) MUST match existing e2e tests.
def test_toggle_shows_source_boxes(logged_in_page, seed_workitem_with_sources):
    page = logged_in_page
    page.goto("/workitems")
    page.get_by_test_id("workitem-row").first.click()          # expand (match real selector)
    page.locator(".workitem-image").first.click()              # open lightbox
    page.get_by_test_id("workitems-src-toggle").click()        # Show sources
    assert page.locator("#srcHlLayer .src-hl-box").count() > 0


def test_unlocatable_field_has_badge(logged_in_page, seed_workitem_with_sources):
    page = logged_in_page
    page.goto("/workitems")
    page.get_by_test_id("workitem-row").first.click()
    assert page.locator(".src-no-loc-badge").count() >= 1
```

- [ ] **Step 2: Reset test DB state, then run**

Per the pre-push gate note, reset NEXORA_TEST state first:
```bash
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_workitem_source_highlight.py -v
```
Expected: PASS. If selectors differ, fix them against the real DOM (use the screenshots from Tasks 7–9).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_workitem_source_highlight.py
git commit -m "test(workitems): e2e for source-highlight toggle and badge"
```

---

### Task 12: Docs + changelog

**Files:**
- Modify: `CHANGELOG.md`, `CLAUDE.md` (workitems/architecture note), `docs/howto/*` (if a workitems doc exists)

- [ ] **Step 1: Changelog**

Add under `[Unreleased] → Added` in `CHANGELOG.md`:
```markdown
- Workitems: "Show sources" toggle on the document viewer highlights where each
  extracted index-field value was found on the page (read-only). Coordinates come
  from the Octopus document service, normalized server-side; renders in the
  lightbox and thumbnails. Fields without coordinates show a "no source location"
  badge. Reuses `workitems.details.view.images` + `.fields` (no new permission).
```

- [ ] **Step 2: CLAUDE.md / how-to**

In `CLAUDE.md`, in the routing/architecture description of the workitems area, add a sentence noting `api_get_media_info` now returns `field_sources` and that `nx_lib/field_locations.py` holds the pure coordinate-normalization logic. If a workitems how-to exists under `docs/howto/`, add a short "Source highlighting" subsection; otherwise skip.

- [ ] **Step 3: Run full unit suite + detect changes**

Run:
```bash
python -m pytest tests/unit -q
gitnexus_detect_changes()
```
Expected: green unit suite; detect_changes shows only the symbols touched by this feature.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md CLAUDE.md docs
git commit -m "docs(workitems): document source-highlighting feature"
```

---

## Self-Review (completed by plan author)

**Spec coverage:** toggle + click (Tasks 7, 9) ✓; lightbox + thumbnails (Tasks 7, 8) ✓; un-locatable badge (Task 9) ✓; read-only / no write-back (no task mutates data) ✓; backend normalization to 0–1 (Task 2) ✓; coords ride existing call (Task 4) ✓; `field_sources` contract (Tasks 3, 5) ✓; perm reuse + suppression (Task 5) ✓; i18n de/fr/it (Task 10) ✓; unit + e2e tests (Tasks 2,3,5,11) ✓; live coord verification first (Task 1) ✓; rotation/orientation risk (called out in Task 1 Step 3) ✓.

**Placeholder scan:** Front-end tasks intentionally anchor on element IDs / function names (not line numbers) because the file is concurrently edited — each such step says "re-read before editing." The one genuine unknown (exact Octopus key names/unit/origin) is isolated to Task 1 and to named constants at the top of Task 3, by design — not a placeholder but a single reconciliation point.

**Type consistency:** `field_sources` entry shape (`key/label/value/locations[].{page,rect{x,y,w,h}}`) is identical across Tasks 3, 5, 7, 8, 9. `normalize_rect` signature matches its caller in `extract_field_locations`. `srcHl` state object and `renderSrcOverlay(pulseKey)` / `setSrcHl(on)` / `renderThumbOverlay(...)` / `openDocModalAt(...)` / `showDocModal(...)` names are consistent across Tasks 7–9.
