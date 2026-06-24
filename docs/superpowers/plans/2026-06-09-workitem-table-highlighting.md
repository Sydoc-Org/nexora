# Workitem table / line-item source highlighting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the read-only "Show sources" overlay on the workitems document viewer from scalar index fields to table / line-item cells — each extracted cell value gets a highlight box on the page and a click-to-locate row in a line-item grid.

**Architecture:** A table cell is "just another source." The backend opt-in-fetches table data (`with_tables=True`, only from `api_get_media_info`), a new pure parser `nx_lib/table_locations.py` turns it into a `table_sources` array (reusing `field_locations.py`'s rect/confidence/offset helpers), and the existing front-end render loop draws cell boxes (distinct hue) + a compact grid. Per-cell coords are confirmed by a live INT spike (Task 1) and the renderer degrades to row/table grain if cells lack rects.

**Tech Stack:** Python 3 / Flask, pytest, vanilla JS (Jinja partial), Flask-Babel, Playwright (e2e).

**Spec:** `docs/superpowers/specs/2026-06-09-workitem-table-highlighting-design.md`

---

## File Structure

- **Create** `nx_lib/table_locations.py` — pure `extract_table_locations(doc_json) -> table_sources`; imports shared helpers from `field_locations.py`.
- **Modify** `nx_lib/field_locations.py` — promote shared helpers (`_rect_from_octo`/`rect_from_octo`, `_confidence`/`confidence_of`, `_count_image_media`, `_items`, `_num`) to importable names; behavior unchanged.
- **Modify** `nx_lib/octo.py:101` — `get_extensions_urls_fields(..., with_tables=False)` → 5-tuple; request `WithTables=true` only when asked.
- **Modify** `nx_lib/views/workitems.py` — `api_get_media_info` passes `with_tables=True`, returns + caches `table_sources`, suppresses by perm; update the 3 other call sites (dashboard activity ~609, csv export, `api_get_media_raw` ~1041) and `dashboard.py` to the 5-tuple.
- **Modify** `templates/js/_workitems_overview_js.html` — store `__tableByWorkitem`, flatten cells into the box render + thumbnails (kind `cell`), line-item grid in the field panel, click-to-locate.
- **Modify** `templates/workitems_overview.html` — (only if a grid container/markup hook is needed; the panel is built in JS, so likely no change).
- **Modify** `static/css/source-highlight.css` — `.src-box--cell` hue + `.src-table-grid` styles.
- **Test** `tests/unit/test_table_locations.py` (new), `tests/unit/test_octo.py` (5-tuple), `tests/unit/test_media_info_table_sources.py` (new), `tests/e2e/test_workitem_table_highlight.py` (new).
- **i18n/docs** `messages.pot` + `translations/{de,fr,it}`, `CHANGELOG.md`, `CLAUDE.md`.

---

### Task 1: Live INT spike — confirm the table coordinate shape

**Files:**
- Create (throwaway, NOT committed): `tmp_spike_tables.py` at worktree root.

- [ ] **Step 1: Ensure worktree dev env**

The worktree lacks the gitignored env files. Copy them from the main checkout (they stay gitignored):

```bash
cp C:/dev/nexora/env/INT.env C:/dev/nexora.wt/table-highlight/env/INT.env
```

Use the main checkout's venv python for all commands: `C:/dev/nexora/venv/Scripts/python.exe`.

- [ ] **Step 2: Write the spike script**

```python
# tmp_spike_tables.py — throwaway; prints the table shape for one workitem.
import os, json, sys
os.environ["ENVIRONMENT"] = "INT"
from nx_main import app
import requests
from nx_lib.octo import (
    get_domain_for_workitem, get_workitemdata_param, get_access_token, OCTO_DOMAIN,
)

WID = int(sys.argv[1]) if len(sys.argv) > 1 else 18299
with app.app_context():
    domain = get_domain_for_workitem(WID) or OCTO_DOMAIN
    workitemdata, document_id = get_workitemdata_param(WID, domain)
    token = get_access_token(domain)
    url = (
        f"https://{domain}/api/documentservice/api/v2.1/documentService/thin/Document/"
        f"{document_id}?WithExtensions=false&WithDocumentStructure=true"
        f"&WithTables=true&WithDocumentAudits=true&LoadMediaStreams=true"
    )
    r = requests.get(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "workitemdata": workitemdata,
    }, timeout=20)
    r.raise_for_status()
    doc = r.json()
    print("payload bytes:", len(r.content))
    print("top-level keys:", sorted(doc.keys()))
    # Hunt for the table container; print the first table's structure verbatim.
    for k in ("Tables", "DocumentTables", "TableFields"):
        if doc.get(k):
            print(f"--- {k}[0] ---")
            print(json.dumps(doc[k][0], indent=2)[:4000])
    # Batch fallback
    for child in (doc.get("ChildDocuments") or []):
        for k in ("Tables", "DocumentTables", "TableFields"):
            if child.get(k):
                print(f"--- child {k}[0] ---")
                print(json.dumps(child[k][0], indent=2)[:4000])
                break
```

- [ ] **Step 3: Run it against a workitem with line items**

Run: `cd C:/dev/nexora.wt/table-highlight && ENVIRONMENT=INT C:/dev/nexora/venv/Scripts/python.exe tmp_spike_tables.py 18299`
Expected: prints payload size, top-level keys, and the first table's JSON. If WID 18299 has no `Tables`, try other invoice WIDs until one returns a table.

- [ ] **Step 4: Record findings in the spec**

Fill the spec's "Verified shape (INT spike)" section: the exact JSON path to tables → rows → cells, where each cell's rect lives (`Location.Rectangle(s)`? a `Cell.Location`?), unit/origin, page index field, header/column source, and the payload delta vs `WithTables=false`. **Adjust Tasks 2 & 5 to the real shape** before building.

- [ ] **Step 5: Delete the throwaway + commit the spec update**

```bash
rm tmp_spike_tables.py
git add docs/superpowers/specs/2026-06-09-workitem-table-highlighting-design.md
SQL_SYNC_SKIP=1 git commit -m "docs(workitems): record table-shape INT spike findings"
```

---

### Task 2: Pure `extract_table_locations` parser

> Test fixtures below use the **expected** shape (tables → rows → cells, each cell with an `IndexField.Location`-style rect). If Task 1 reveals a different shape, update the fixtures + parser together.

**Files:**
- Modify: `nx_lib/field_locations.py` (promote shared helpers)
- Create: `nx_lib/table_locations.py`
- Test: `tests/unit/test_table_locations.py`

- [ ] **Step 1: Promote shared helpers in `field_locations.py`**

Add public aliases (keep the `_`-prefixed ones as references so existing code is untouched):

```python
# at end of nx_lib/field_locations.py
rect_from_octo = _rect_from_octo
confidence_of = _confidence
count_image_media = _count_image_media
items_of = _items
num = _num
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/unit/test_table_locations.py
from nx_lib.table_locations import extract_table_locations

def _cell(col, text, rect=None, conf=None, page_index=0):
    f = {"Name": col, "FieldValue": {"Text": text}}
    if rect is not None:
        f["Location"] = {"PageIndex": page_index, "Rectangle": rect, "Rectangles": [rect]}
    if conf is not None:
        f["Confidence"] = conf
    return f

R = {"Left": 120, "Top": 880, "Width": 300, "Height": 28}

def _doc(rows, columns=("Description", "Qty")):
    return {"Tables": [{"Title": "Positionen", "Columns": list(columns), "Rows": rows}]}

def test_cell_with_rect_yields_box():
    doc = _doc([[_cell("Description", "Widget A", R, conf=0.97)]], columns=("Description",))
    ts = extract_table_locations(doc)
    assert len(ts) == 1
    cell = ts[0]["rows"][0][0]
    assert cell["value"] == "Widget A"
    assert cell["locations"] == [{"page": 0, "rect": {"left":120,"top":880,"width":300,"height":28}}]
    assert cell["confidence"] == 0.97

def test_cell_without_rect_is_unlocatable():
    doc = _doc([[_cell("Qty", "3")]], columns=("Qty",))
    cell = extract_table_locations(doc)[0]["rows"][0][0]
    assert cell["locations"] == []

def test_degenerate_rect_dropped():
    doc = _doc([[_cell("Qty", "0", {"Left":0,"Top":0,"Width":0,"Height":0})]], columns=("Qty",))
    assert extract_table_locations(doc)[0]["rows"][0][0]["locations"] == []

def test_no_tables_returns_empty():
    assert extract_table_locations({"Tables": []}) == []
    assert extract_table_locations({}) == []

def test_batch_page_offset():
    # child 0 has 1 image media -> child 1's table page index shifts by 1
    child0 = {"Media": [{"Extension": ".jpg", "Url": "u0"}], "Tables": []}
    child1 = {"Media": [], "Tables": _doc([[_cell("Description","X", R, page_index=0)]],
                                          columns=("Description",))["Tables"]}
    doc = {"DocumentType": "Batch", "ChildDocuments": [child0, child1]}
    cell = extract_table_locations(doc)[0]["rows"][0][0]
    assert cell["locations"][0]["page"] == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `C:/dev/nexora/venv/Scripts/python.exe -m pytest tests/unit/test_table_locations.py -q`
Expected: FAIL (`ModuleNotFoundError: nx_lib.table_locations`).

- [ ] **Step 4: Implement the parser**

```python
# nx_lib/table_locations.py
"""Pure helper: Octopus thin-document (WithTables=true) -> table_sources.
No Flask/HTTP. A table cell mirrors a scalar field_source: {value, locations,
confidence?}, grouped into rows/columns. Reuses field_locations' rect/confidence/
offset helpers so both parsers share one implementation."""
from .field_locations import (
    rect_from_octo, confidence_of, count_image_media, items_of, num,
)

def _cell_locations(fobj, media_offset):
    loc = fobj.get("Location") or fobj.get("CapturedLocation")
    out = []
    if isinstance(loc, dict):
        pi = num(loc.get("PageIndex"))
        if pi is not None:
            page = media_offset + int(pi)
            raw = loc.get("Rectangles") or ([loc["Rectangle"]] if loc.get("Rectangle") else [])
            for r in raw:
                rect = rect_from_octo(r)
                if rect is not None:
                    out.append({"page": page, "rect": rect})
    return out

def _tables_of(item):
    return item.get("Tables") or []

def extract_table_locations(doc_json):
    out = []
    media_offset = 0
    for item in items_of(doc_json):
        for tbl in _tables_of(item):
            columns = list(tbl.get("Columns") or [])
            rows_out = []
            for row in tbl.get("Rows") or []:
                cells_out = []
                for fobj in row or []:
                    value = (fobj.get("FieldValue") or {}).get("Text")
                    if value is None:
                        continue
                    cell = {
                        "col": fobj.get("Name"),
                        "value": value,
                        "locations": _cell_locations(fobj, media_offset),
                    }
                    conf = confidence_of(fobj)
                    if conf is not None:
                        cell["confidence"] = conf
                    cells_out.append(cell)
                if cells_out:
                    rows_out.append(cells_out)
            if rows_out:
                out.append({"title": tbl.get("Title"), "columns": columns, "rows": rows_out})
        media_offset += count_image_media(item)
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `C:/dev/nexora/venv/Scripts/python.exe -m pytest tests/unit/test_table_locations.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add nx_lib/field_locations.py nx_lib/table_locations.py tests/unit/test_table_locations.py
SQL_SYNC_SKIP=1 git commit -m "feat(workitems): pure table_locations parser + tests"
```

---

### Task 3: `get_extensions_urls_fields` opt-in table fetch (5-tuple)

**Files:**
- Modify: `nx_lib/octo.py:101`
- Test: `tests/unit/test_octo.py`

- [ ] **Step 1: Update the failing test**

In `tests/unit/test_octo.py`, the existing 4-tuple assertions become 5-tuple. Add:

```python
def test_with_tables_false_returns_empty_table_sources(monkeypatch):
    # existing mock of requests.get returning a no-table doc
    res = get_extensions_urls_fields("wd", "docid")
    assert res[4] == []            # table_sources default empty

def test_with_tables_true_parses_tables(monkeypatch):
    # mock requests.get to return a doc with one Tables entry (shape from Task 1)
    res = get_extensions_urls_fields("wd", "docid", with_tables=True)
    assert res[4] and res[4][0]["rows"]
```

- [ ] **Step 2: Run to verify fail**

Run: `C:/dev/nexora/venv/Scripts/python.exe -m pytest tests/unit/test_octo.py -q`
Expected: FAIL (4-tuple unpack / `with_tables` unexpected kwarg).

- [ ] **Step 3: Implement**

```python
def get_extensions_urls_fields(workitemdata, document_id, domain=None, with_tables=False):
    if domain is None:
        domain = OCTO_DOMAIN
    url = (
        f"https://{domain}/api/documentservice/api/v2.1/documentService/thin/Document/"
        f"{document_id}?WithExtensions=false&WithDocumentStructure=true"
        f"&WithTables={'true' if with_tables else 'false'}&WithDocumentAudits=true&LoadMediaStreams=true"
    )
    # ... unchanged auth/fetch ...
    except Exception as e:
        current_app.logger.error(f"Error fetching document details: {e}")
        return [], [], {}, [], []           # 5-tuple on error
    # ... unchanged urls/fields/field_sources build ...
    from .table_locations import extract_table_locations
    table_sources = extract_table_locations(doc_json) if with_tables else []
    return extensions, urls, fields, field_sources, table_sources
```

- [ ] **Step 4: Update the 3 other call sites to the 5-tuple**

`nx_lib/views/workitems.py` ~614 and ~1041, and `nx_lib/views/dashboard.py` activity (~609 region is workitems; grep `get_extensions_urls_fields`): change `extensions, urls, fields, _fs = ...` → `extensions, urls, fields, _fs, _ts = ...` (these keep `with_tables=False`).

Run: `C:/dev/nexora/venv/Scripts/python.exe -c "import ast,sys; [print(p) for p in []]"` then grep to confirm no remaining 4-tuple unpack:
`grep -rn "= get_extensions_urls_fields" nx_lib/`

- [ ] **Step 5: Run to verify pass**

Run: `C:/dev/nexora/venv/Scripts/python.exe -m pytest tests/unit/test_octo.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add nx_lib/octo.py nx_lib/views/workitems.py nx_lib/views/dashboard.py tests/unit/test_octo.py
SQL_SYNC_SKIP=1 git commit -m "feat(workitems): opt-in table fetch in get_extensions_urls_fields"
```

---

### Task 4: `api_get_media_info` returns + suppresses `table_sources`

**Files:**
- Modify: `nx_lib/views/workitems.py:975` (`api_get_media_info`)
- Test: `tests/unit/test_media_info_table_sources.py`

- [ ] **Step 1: Write the failing tests**

Mirror `tests/unit/test_media_info_field_sources.py`. Assert: with both perms, response has `table_sources` with cell `locations`; without `view.images`, every cell's `locations == []` but values remain; without `view.fields`, `table_sources == []`.

```python
def test_table_sources_present_with_perms(client_with_perms): ...
def test_table_sources_locations_stripped_without_images(client_no_images): ...
def test_table_sources_empty_without_fields(client_no_fields): ...
```

- [ ] **Step 2: Run to verify fail**

Run: `C:/dev/nexora/venv/Scripts/python.exe -m pytest tests/unit/test_media_info_table_sources.py -q`
Expected: FAIL (`table_sources` missing).

- [ ] **Step 3: Implement**

In `api_get_media_info`: call `get_extensions_urls_fields(..., with_tables=True)` unpacking the 5-tuple; add `"table_sources": table_sources` to the response dict and the cached dict. Extend the perm `_suppress()` (the nested helper at ~989) so:

```python
if not can_view_fields:
    d["fields"] = {}
    d["field_sources"] = []
    d["table_sources"] = []
elif not can_view_images:
    d["field_sources"] = [{**s, "locations": []} for s in d.get("field_sources", [])]
    d["table_sources"] = [
        {**t, "rows": [[{**c, "locations": []} for c in row] for row in t.get("rows", [])]}
        for t in d.get("table_sources", [])
    ]
return d
```

- [ ] **Step 4: Run to verify pass**

Run: `C:/dev/nexora/venv/Scripts/python.exe -m pytest tests/unit/test_media_info_table_sources.py tests/unit/test_media_info_field_sources.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nx_lib/views/workitems.py tests/unit/test_media_info_table_sources.py
SQL_SYNC_SKIP=1 git commit -m "feat(workitems): api_get_media_info ships table_sources (perm-suppressed)"
```

---

### Task 5: Front-end — cell boxes + line-item grid + click-to-locate

**Files:**
- Modify: `templates/js/_workitems_overview_js.html`
- Modify: `static/css/source-highlight.css`

- [ ] **Step 1: Store table sources**

Where `window.__srcByWorkitem[workitemid] = mediaInfo.field_sources || []` (~619), add:
`window.__tableByWorkitem[workitemid] = mediaInfo.table_sources || [];` (init the map near `__srcByWorkitem`).

- [ ] **Step 2: Feed cells into the box renderer**

Add a helper that flattens table cells to the source shape the box loops expect, tagged `kind:'cell'`:

```javascript
function tableCellSources(workitemid) {
  const tables = (window.__tableByWorkitem && window.__tableByWorkitem[workitemid]) || [];
  const out = [];
  tables.forEach((t, ti) => (t.rows || []).forEach((row, ri) => row.forEach((c, ci) => {
    if (c.locations && c.locations.length)
      out.push({ key: `t${ti}r${ri}c${ci}`, label: c.col, value: c.value,
                 locations: c.locations, confidence: c.confidence, kind: 'cell' });
  })));
  return out;
}
```

Update `currentSources()` (~1908) and the thumbnail box loop (~701) and `hasAnyLocation()` (~1912) to concatenate `tableCellSources(wid)`. In the box element builder (~1937), add `box.classList.add('src-box--' + (src.kind || 'field'))`.

- [ ] **Step 3: Render the line-item grid in the panel**

After the scalar `<dl>` is built in `fields-container-${workitemid}` (~593-640), append a grid per table:

```javascript
const tables = window.__tableByWorkitem[workitemid] || [];
tables.forEach((t, ti) => {
  const wrap = document.createElement('div');
  wrap.className = 'src-table-grid';
  const title = t.title ? `<div class="src-table-title">${t.title}</div>` : '';
  const head = (t.columns || []).map(c => `<th>${c}</th>`).join('');
  const body = (t.rows || []).map((row, ri) => {
    const tds = row.map((c, ci) => {
      const hasLoc = !!(c.locations && c.locations.length);
      const page = hasLoc ? c.locations[0].page : '';
      return `<td class="${hasLoc ? 'src-cell-loc' : ''}" data-wid="${workitemid}"
        data-key="t${ti}r${ri}c${ci}" data-page="${page}">${c.value ?? ''}</td>`;
    }).join('');
    return `<tr>${tds}</tr>`;
  }).join('');
  wrap.innerHTML = `${title}<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  fieldsContainer.appendChild(wrap);
});
```

- [ ] **Step 4: Wire click-to-locate for cells**

Extend the existing field-row click handler (delegated, ~2018) to also match `td.src-cell-loc`: read `data-wid/data-key/data-page`, open the lightbox at `data-page`, and pulse the box whose `key === data-key` (the locate path already pulses by key — pass the cell key through the same `openModalAtPage(wid, page, pulseKey)` used by scalar rows).

- [ ] **Step 5: CSS — distinct cell hue + grid**

```css
/* static/css/source-highlight.css */
.src-box--cell { /* distinct hue from scalar .src-box; keep confidence border */
  outline-color: #7c3aed;            /* violet, vs the scalar amber/green */
  background: rgba(124, 58, 237, .10);
}
.src-table-grid { margin-top: .75rem; }
.src-table-grid .src-table-title { font-weight: 600; font-size: .8rem; margin-bottom: .25rem; }
.src-table-grid table { width: 100%; border-collapse: collapse; font-size: .8rem; }
.src-table-grid th, .src-table-grid td { border: 1px solid var(--nx-border, #e5e7eb); padding: 2px 6px; text-align: left; }
.src-table-grid td.src-cell-loc { cursor: pointer; }
.src-table-grid td.src-cell-loc:hover { background: rgba(124, 58, 237, .08); }
```

- [ ] **Step 6: Restart dev server + manual check**

Jinja caches the JS partial; restart before testing. Run `nx -u -b --loginas:<user-with-detail-perms>`, open a workitem with table media, toggle Show sources, confirm cell boxes + grid + click-to-locate. Screenshot to `var/screenshots/`.

- [ ] **Step 7: Commit**

```bash
git add templates/js/_workitems_overview_js.html static/css/source-highlight.css
SQL_SYNC_SKIP=1 git commit -m "feat(workitems): table cell boxes + line-item grid in Show sources"
```

---

### Task 6: i18n

**Files:** `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po`

- [ ] **Step 1: Mark new strings** — wrap any new literal UI copy (e.g. a `Line items` heading if added) in `{{ _('...') }}`. (The grid uses Octopus-provided column names + values, which are data, not translatable.)
- [ ] **Step 2: Extract** — `pybabel extract -F babel.cfg -o messages.pot .`
- [ ] **Step 3: Update** — `pybabel update -i messages.pot -d translations`
- [ ] **Step 4: Translate** new msgids non-fuzzy in de/fr/it (`.po` files).
- [ ] **Step 5: Compile** — `pybabel compile -d translations`
- [ ] **Step 6: Verify** — `C:/dev/nexora/venv/Scripts/python.exe -m pytest tests/unit/test_translations.py -q` → PASS.
- [ ] **Step 7: Commit** — `git add messages.pot translations && SQL_SYNC_SKIP=1 git commit -m "chore(i18n): translate table-highlight strings (de/fr/it)"`

---

### Task 7: e2e + docs

**Files:** `tests/e2e/test_workitem_table_highlight.py`, `CHANGELOG.md`, `CLAUDE.md`

- [ ] **Step 1: Write the e2e** mirroring `tests/e2e/test_workitem_source_highlight.py`: stub/seed media-info with a `table_sources` fixture, open workitem → toggle Show sources → assert a `.src-box--cell` renders → click a `td.src-cell-loc` → assert lightbox opens at the right page and the cell box pulses.
- [ ] **Step 2: Reset test DB then run e2e** — `C:/dev/nexora/venv/Scripts/python.exe scripts/test_db_reset.py` then `... -m pytest tests/e2e/test_workitem_table_highlight.py -q` → PASS.
- [ ] **Step 3: CHANGELOG** — add under `[Unreleased] → Added`: table/line-item source highlighting.
- [ ] **Step 4: CLAUDE.md** — extend the workitems doc-viewer note: cells are fetched via `with_tables=True` (only the media-info path), parsed by `nx_lib/table_locations.py`, returned as `table_sources`, rendered as violet cell boxes + a line-item grid; reuses the same perms.
- [ ] **Step 5: Commit** — `git add tests/e2e/test_workitem_table_highlight.py CHANGELOG.md CLAUDE.md && SQL_SYNC_SKIP=1 git commit -m "test+docs(workitems): e2e table highlight + changelog/CLAUDE"`

---

### Task 8: Full verification

- [ ] **Step 1: Unit suite** — `C:/dev/nexora/venv/Scripts/python.exe -m pytest tests/unit -q` → all green.
- [ ] **Step 2: Translation suite** — `... -m pytest tests/unit/test_translations.py -q` → green.
- [ ] **Step 3: Screenshots** — capture lightbox cell boxes + grid + a located pulse to `var/screenshots/table-highlight-*.png`; SendUserFile each (remote review).
- [ ] **Step 4: Leave for owner** — remote session: committed, NOT pushed. Final summary lists commits + the owner's merge-into-`feature/2.5.63` + push + PR steps, plus that this only needs the existing `workitems.details.view.*` perms (no migration).

---

## Self-Review

- **Spec coverage:** opt-in fetch (T3), parser (T2), media-info + suppression (T4), cell boxes + distinct hue + grid + click-to-locate (T5), graceful degradation (parser emits whatever grain exists; T5 renders whatever rects exist), perms reuse (T4, no new code), i18n (T6), unit+e2e (T2/T4/T7), spike (T1), payload risk measured (T1). Covered.
- **Placeholder scan:** test code is concrete against the expected shape; T1 explicitly gates fixture adjustment. No "TBD/handle edge cases".
- **Type consistency:** `table_sources` = `[{title, columns, rows:[[{col,value,locations:[{page,rect}],confidence?}]]}]` used identically in T2/T4/T5; box `kind:'cell'` ↔ `.src-box--cell` consistent; helper names (`rect_from_octo`, `confidence_of`, `count_image_media`, `items_of`, `num`) match between T2 step 1 and the parser.
