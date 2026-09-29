"""What a permission code actually does, derived rather than described.

``dbo.Permission.Description`` is one 200-character sentence written by hand,
so it drifts the moment a route moves and it can never say *where* a code is
enforced. Everything here is read back out of the running app and the source
tree instead, so it cannot disagree with the code:

- :func:`routes_index` walks ``url_map`` and reads the ``required_permissions``
  tuple that ``require_permission`` / ``require_any_permission`` already leave
  on every guarded view (``nx_lib/security.py``), giving the exact endpoints a
  code opens and which of them are linkable pages;
- :func:`usage_index` scans the templates and the Python package for permission
  literals, so a code's UI affordances (the buttons a template renders only
  when ``has_permission`` says so) are listed with file and line.

Both indexes are built once per process and cached: the route map is fixed
after startup, and the source tree is fixed for a deploy. :func:`invalidate`
exists for the tests.

Flask-free apart from the ``url_map`` argument, so the scanning half is
importable and testable on its own.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .security import _ACTIONS, _SCOPES, _split_code

# The repo root -- nx_lib/permission_docs.py -> nx_lib -> root.
_ROOT = Path(__file__).resolve().parent.parent

# Where a permission literal can meaningfully appear. `static/js` is included
# because the static JS partials (#191) carry affordance checks too.
_SCAN_DIRS = (("templates", "*.html"), ("nx_lib", "*.py"), ("static/js", "*.js"))

# A quoted permission code, in either quote style. Deliberately the grammar
# from PERMISSION_CODE_RE rather than "any dotted string": it keeps reporting
# source codes and process names out of the index.
_LITERAL_RE = re.compile(
    r"""['"]("""
    r"""[a-z]+(?:\.[a-z]+)?(?:\.[A-Za-z0-9_]+)*"""
    r"""\.(?:""" + "|".join(_ACTIONS) + r""")"""
    r"""(?:\.(?:""" + "|".join(s for s in _SCOPES if s) + r"""))?"""
    r""")['"]"""
)

# Lines that merely *define* the vocabulary rather than enforce a permission.
_NOISE_FILES = ("nx_lib/permission_docs.py",)

# Templates rarely call has_permission directly -- they read the flags
# page_visibility() hands them ("{% if page_visibility.adminTenantsPagePerm %}"),
# so a literal scan alone reports "used nowhere in the UI" for exactly the
# codes that gate a page. This picks the key -> code mapping out of
# page_visibility()'s own body so the indirection is followed, not guessed.
_VISIBILITY_RE = re.compile(r'"(\w+)":\s*has_permission\(\s*"([^"]+)"\s*\)')
_VISIBILITY_SOURCE = "nx_lib/security.py"


@lru_cache(maxsize=1)
def visibility_keys() -> dict[str, str]:
    """``page_visibility()`` flag name -> the permission code behind it."""
    try:
        text = (_ROOT / _VISIBILITY_SOURCE).read_text(encoding="utf-8")
    except OSError:
        return {}
    start = text.find("def page_visibility()")
    if start < 0:
        return {}
    body = text[start : text.find("\ndef ", start + 1)]
    return {m.group(1): m.group(2) for m in _VISIBILITY_RE.finditer(body)}


def _rel(path: Path) -> str:
    return path.relative_to(_ROOT).as_posix()


@lru_cache(maxsize=1)
def usage_index() -> dict[str, list[dict]]:
    """code -> [{file, line, kind, snippet}], every place the literal appears.

    One pass over the tree rather than a grep per code: the page asks for one
    code at a time, but the scan costs the same either way and the result is
    cached for the process.
    """
    index: dict[str, list[dict]] = {}
    flags = visibility_keys()
    for folder, pattern in _SCAN_DIRS:
        base = _ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob(pattern)):
            rel = _rel(path)
            if rel in _NOISE_FILES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "." not in text:
                continue
            kind = "template" if rel.startswith("templates/") else "code"
            for lineno, line in enumerate(text.splitlines(), start=1):
                hits = {m.group(1) for m in _LITERAL_RE.finditer(line)}
                if rel != _VISIBILITY_SOURCE:
                    hits |= {code for key, code in flags.items() if key in line}
                for code in hits:
                    index.setdefault(code, []).append(
                        {
                            "file": rel,
                            "line": lineno,
                            "kind": kind,
                            "snippet": line.strip()[:160],
                        }
                    )
    return index


def routes_index(url_map, view_functions) -> dict[str, list[dict]]:
    """code -> [{endpoint, rule, methods, page, args}] for every guarded route.

    ``page`` marks a route a reader can actually open from here: a GET rule
    that ``url_for`` can build without arguments. Not cached on its own --
    :func:`describe` caches the whole answer, and the tests build small maps.
    """
    index: dict[str, list[dict]] = {}
    for rule in url_map.iter_rules():
        view = view_functions.get(rule.endpoint)
        codes = getattr(view, "required_permissions", None)
        if not codes:
            continue
        methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})
        entry = {
            "endpoint": rule.endpoint,
            "rule": str(rule),
            "methods": methods,
            "args": sorted(rule.arguments),
            "page": "GET" in methods and not rule.arguments and not str(rule).startswith("/api/"),
            # A route guarded by require_any_permission opens for any one of
            # its codes; say so rather than implying this one is required.
            "any_of": sorted(codes) if len(codes) > 1 else [],
        }
        for code in codes:
            index.setdefault(code, []).append(entry)
    for entries in index.values():
        entries.sort(key=lambda e: (not e["page"], e["rule"]))
    return index


def parse(code: str) -> dict:
    """The grammar breakdown of a code: area, object, action, scope."""
    area, obj, action, scope = _split_code(code)
    return {
        "area": area,
        "object": obj,
        # "" for an area-level code such as admin.view, where object == area.
        "object_label": obj[len(area) + 1 :] if obj != area else "",
        "action": action,
        "scope": scope,
        "gate_candidates": list(
            dict.fromkeys(c for c in (f"{obj}.view", f"{area}.view") if c != code)
        ),
    }


def screenshot_for(code: str) -> str | None:
    """The captured screenshot for this code, as a path under ``static/``.

    Captured by ``scripts/capture-permission-shots.py``; absent is the normal
    case (only page-gating codes have one), so callers render the slot only
    when this returns a path.
    """
    base = _ROOT / "static" / "img" / "permissions"
    for ext in ("jpg", "png"):
        if (base / f"{code}.{ext}").is_file():
            return f"img/permissions/{code}.{ext}"
    return None


def describe(code: str, url_map=None, view_functions=None) -> dict:
    """Everything derivable about one code, for the permission detail page."""
    usages = usage_index().get(code, [])
    routes = (
        routes_index(url_map, view_functions).get(code, [])
        if url_map is not None and view_functions is not None
        else []
    )
    route_files = {r["endpoint"] for r in routes}
    return {
        "code": code,
        "grammar": parse(code),
        "routes": routes,
        # Template hits are the UI affordances; code hits outside the guarded
        # views are the checks a route makes on its own.
        "ui_usages": [u for u in usages if u["kind"] == "template"],
        "code_usages": [u for u in usages if u["kind"] == "code"],
        "unused": not routes and not usages,
        "endpoints": sorted(route_files),
        "screenshot": screenshot_for(code),
    }


def invalidate() -> None:
    """Drop the cached scans (tests; a running deploy never needs it)."""
    usage_index.cache_clear()
    visibility_keys.cache_clear()
