"""Template lint: static assets go through static_v(), not raw url_for('static').

nx_lib/__init__.py scopes a year-long Cache-Control to Flask's built-in
"static" endpoint only (final-review fix, post-#191 task 5) via an
after_request hook keyed on request.endpoint == "static" -- it does NOT set
the app-wide SEND_FILE_MAX_AGE_DEFAULT config, because that would apply to
every send_file()/send_from_directory() call in the app, not just /static.
That long cache is only safe because every asset URL in a template carries
the static_v() ?v=<mtime> cache-buster. A raw url_for('static', filename=...)
call has no cache-buster, so it would let a browser serve a stale asset past
the next deploy.

Every other send_file()/send_from_directory() call site (outside the "static"
endpoint) must set its own explicit, short-lived cache policy -- either an
explicit max_age= kwarg or an explicit Cache-Control header override -- so it
never silently inherits a long-lived, publicly-cacheable default.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "templates"
NX_LIB = REPO_ROOT / "nx_lib"

BAD_PATTERN = re.compile(r"""url_for\(\s*['"]static['"]""")

# send_file()/send_from_directory() call sites that are allowed to omit an
# explicit max_age= kwarg because they set Cache-Control on the response
# object themselves before returning it.
SEND_CALL_PATTERN = re.compile(r"\b(send_file|send_from_directory)\s*\(")


def _offenders():
    found = []
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        text = tpl.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if BAD_PATTERN.search(line):
                found.append(f"{tpl.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    return found


def test_no_raw_url_for_static_in_templates():
    offenders = _offenders()
    assert offenders == [], (
        "Raw url_for('static', ...) has no cache-buster, which is unsafe now that "
        "the /static endpoint gets a year-long Cache-Control (nx_lib/__init__.py). "
        "Use static_v(...) instead:\n" + "\n".join(offenders)
    )


def _send_file_call_sites():
    """Find every actual send_file()/send_from_directory() call in nx_lib/views
    (skipping comments), with a window of surrounding lines to check for an
    explicit cache policy."""
    sites = []
    views_dir = NX_LIB / "views"
    for pyfile in sorted(views_dir.rglob("*.py")):
        lines = pyfile.read_text(encoding="utf-8", errors="replace").splitlines()
        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if SEND_CALL_PATTERN.search(line):
                # A call can span a few lines (wrapped args) and the
                # Cache-Control override can land a line or two after the
                # call when it's applied to the returned response object.
                window = "\n".join(lines[max(0, lineno - 3) : lineno + 4])
                sites.append((f"{pyfile.relative_to(REPO_ROOT)}:{lineno}", window))
    return sites


def test_send_file_call_sites_set_explicit_cache_policy():
    """Every send_file()/send_from_directory() call outside the Flask static
    endpoint must set its own explicit cache policy (max_age= kwarg, or a
    Cache-Control header override on the response) -- see nx_lib/__init__.py's
    after_request hook, which only long-caches the "static" endpoint. Without
    this, a call site would silently fall back to Flask's SEND_FILE_MAX_AGE_DEFAULT
    (unset / None), which is fine by default but easy to accidentally widen
    app-wide again without anyone noticing the blast radius.
    """
    offenders = []
    for location, window in _send_file_call_sites():
        has_max_age_kwarg = "max_age=" in window
        has_cache_control_override = "Cache-Control" in window
        if not (has_max_age_kwarg or has_cache_control_override):
            offenders.append(location)
    assert offenders == [], (
        "send_file()/send_from_directory() call site has no explicit cache policy "
        "(max_age= kwarg or a Cache-Control header override). Flask's built-in "
        "/static route gets its long cache from nx_lib/__init__.py's after_request "
        "hook -- every other call site must set its own short-lived policy "
        "explicitly:\n" + "\n".join(offenders)
    )
