r"""The workitems URL carries only what differs from the server's defaults (#269).

The filter serialiser used to append every form field unconditionally, so an
unfiltered page produced twelve query params of which seven were empty strings
and four were defaults:

    ?prcfW=all&search=&stage=&status=&startDate=&endDate=&doccomb=and
     &docfield=&docop=contains&docvalue=&perPage=40&page=1

Two properties have to hold for trimming them to be safe, and both are checked
here because both are easy to break silently:

1. The JS defaults must match the server's actual defaults. If they drift, the
   URL omits a param whose server-side default is something else, and the page
   silently filters differently from what the address bar says.
2. Doc-field params must be dropped a whole row at a time. query.py reads them
   with getlist() and pairs them positionally --
   zip(docfields, docvalues, strict=False) -- so dropping one empty member of a
   row pairs the wrong field with the wrong value.

Behaviour was verified in a browser against the real extracted function: idle
form -> no params; perPage=100 and page=3 kept; a filled doc row emits all four
members; an empty second row is skipped whole; two filled rows stay index
aligned.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JS = REPO / "static" / "js" / "workitems_overview.js"
QUERY_PY = REPO / "nx_lib" / "workitems" / "query.py"
VIEWS_PY = REPO / "nx_lib" / "views" / "workitems.py"


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def _js_defaults() -> dict:
    m = re.search(r"const FILTER_DEFAULTS = \{([^}]*)\}", _js())
    assert m, "FILTER_DEFAULTS not found"
    return dict(re.findall(r"(\w+)\s*:\s*'([^']*)'", m.group(1)))


def test_the_serialiser_exists():
    assert "function buildFilterParams(" in _js()


def test_empty_values_are_dropped():
    assert "if (el.value === '') continue;" in _js()


def test_defaults_are_dropped():
    js = _js()
    assert "FILTER_DEFAULTS[el.name] === el.value" in js


def test_page_one_is_dropped():
    assert "if (page > 1) params.set('page', page);" in _js()


def test_js_perpage_default_matches_the_server():
    """query.py: per_page = int(args.get("perPage", 40))"""
    src = QUERY_PY.read_text(encoding="utf-8")
    m = re.search(r"""args\.get\(\s*["']perPage["']\s*,\s*(\d+)""", src)
    assert m, "could not find the server's perPage default"
    assert _js_defaults()["perPage"] == m.group(1), (
        f"JS says perPage default {_js_defaults()['perPage']!r}, server says "
        f"{m.group(1)!r} -- the URL would omit a value the server does not assume"
    )


def test_js_prcfw_default_matches_the_server():
    """views/workitems.py: process_name = request.args.get("prcfW", "all")"""
    src = VIEWS_PY.read_text(encoding="utf-8")
    m = re.search(r"""args\.get\(\s*["']prcfW["']\s*,\s*["']([^"']*)["']""", src)
    assert m, "could not find the server's prcfW default"
    assert _js_defaults()["prcfW"] == m.group(1)


def test_server_page_default_is_one():
    """The JS drops page when it is 1, so the server had better assume 1."""
    src = QUERY_PY.read_text(encoding="utf-8")
    assert re.search(r"""args\.get\(\s*["']page["']\s*,\s*1""", src), (
        "server no longer defaults page to 1; dropping page=1 from the URL "
        "would change which page loads"
    )


def test_doc_filter_rows_are_all_or_nothing():
    """The flat pass must skip anything inside a .doc-filter-row, and a
    separate pass must emit all four members per row."""
    js = _js()
    assert "el.closest('.doc-filter-row')" in js, (
        "the flat loop no longer skips doc-filter fields; dropping one empty "
        "member of a row misaligns getlist() pairing in query.py"
    )
    assert "document.querySelectorAll('.doc-filter-row')" in js
    assert "['doccomb', 'docfield', 'docop', 'docvalue']" in js


def test_the_positional_pairing_this_protects_still_exists():
    """If query.py stops zipping these positionally, the row-at-a-time rule
    above is no longer load-bearing and this file should be revisited."""
    src = QUERY_PY.read_text(encoding="utf-8")
    assert 'getlist("docfield")' in src
    assert 'getlist("docvalue")' in src
    assert "zip(docfields, docvalues" in src
