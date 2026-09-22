"""Which three pages the phone tab bar shows, and which one is lit.

Flask-free and pure, so the rules below are unit-testable without a request.
``nx_lib/hooks.py`` calls :func:`tabbar_window` once per render and hands the
result to ``templates/_header.html``, which only loops over it.

This lives in Python rather than in the template because two of the three
rules are genuinely fiddly, and a Jinja expression that needs a paragraph of
comment to explain is a rule nobody can change safely later.

**Rule 1 -- which tenant?** The one whose page you are *on*, found by matching
``active_page``. Not the session's ``tenant_scope``: that is only written by
routes calling ``apply_tenant_scope`` (the dashboard, workitems, and the
generated ``tenant_page`` route). A tenant whose pages are *custom* routes --
Generali's ``/generali/documents`` and friends -- never touches it, so on one
of those pages the scope still names whichever tenant you were in before, and
keying the bar off it showed the wrong tenant's pages. Matching the active
page needs no session state, survives a bookmark or a typed URL, and cannot
disagree with what is on screen.

**The ambiguity that makes rule 1 non-trivial.** A registry page carries an
``active`` value and an ``endpoint``. Where they differ the match is
unambiguous. Where they are equal the same ``active_page`` can be claimed by
more than one tenant -- the seeded sydoc and MS02 "workitems" pages both point
at the shared ``workitems_overview`` endpoint, so on ``/workitems`` there is
no way to tell from the page alone whose workitems you are looking at. So:
claimed once -> that tenant; claimed more than once -> fall back to the
tenant the viewer belongs to, and if that does not decide it, to no tenant at
all rather than a guess. Generali's endpoints are unique to Generali, which is
why its pages resolve even though their ``active`` equals their ``endpoint``.

**Rule 2 -- the window.** Three slots over the whole list, the active page in
the middle, clamped at both ends. Generali has eight pages; showing the first
three meant five of them lit nothing, and ``static/js/swipe_nav.js`` locates
itself by the active slot, so swiping did nothing on those five. Centring also
means the three rendered slots *are* ``[previous, active, next]`` -- which is
why the carousel needs no track, no transform and no JavaScript at all.

No wrap at the ends (#368): arriving back at the first view from the last
reads as having gone the wrong way, with nothing to say you looped.
"""

from __future__ import annotations

SLOTS = 3


def _is_active(page: dict, active_page: str) -> bool:
    """Does this registry page describe the page currently on screen?

    ``active`` falls back to ``endpoint`` the same way ``_tenant_nav_page``
    builds it, so a page dict missing ``active`` (list/crud pages have no
    such key) simply never matches -- those are matched by key instead, see
    :func:`tabbar_window`.
    """
    return bool(active_page) and page.get("active") == active_page


def _matches(nav: list[dict], active_page: str) -> list[tuple[dict, int]]:
    """Every (tenant, page index) whose page claims ``active_page``."""
    found = []
    for tenant in nav or []:
        for i, page in enumerate(tenant.get("pages") or []):
            if _is_active(page, active_page) or (
                page.get("page_type") != "custom"
                and active_page == f"tenant_{tenant.get('code')}_{page.get('key')}"
            ):
                found.append((tenant, i))
    return found


def _pick(nav, active_page, own_tenant, remembered, solo):
    """(tenant, active index) for the bar, or (None, -1)."""
    hits = _matches(nav, active_page)
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # Ambiguous: the same active_page is claimed by more than one tenant
        # (a shared endpoint such as workitems_overview). Let the viewer's own
        # tenant break the tie; refuse to guess if it cannot.
        for tenant, i in hits:
            if tenant.get("code") == own_tenant:
                return tenant, i
        return None, -1

    # Nothing on screen matched. Fall back to a tenant whose pages are still
    # the right list to offer: their own portal, or the one they picked.
    if solo and nav:
        return nav[0], -1
    if remembered and nav:
        for tenant in nav:
            if tenant.get("code") == remembered:
                return tenant, -1
    return None, -1


def window_start(active: int, total: int, slots: int = SLOTS) -> int:
    """First index of a ``slots``-wide window centred on ``active``.

    Clamped at both ends, so the first window is the first ``slots`` pages and
    the last is the final ``slots``. ``active < 0`` (nothing on screen matched,
    e.g. a profile or admin sub-page) starts at 0 -- the bar then looks exactly
    as it always did, and swipe_nav.js already declines to move with no active
    slot. A list shorter than the window is not a special case.
    """
    if active < 0:
        return 0
    return max(0, min(active - (slots - 1) // 2, max(0, total - slots)))


def tabbar_window(nav, active_page, own_tenant=None, remembered=None, solo=False, slots=SLOTS):
    """The bar's page slots: ``[(page, is_active), ...]``, or ``[]``.

    ``[]`` means "no tenant applies" and the template falls back to the Global
    entries, which is what a sydoc staff member sees on ``/reporting``.
    """
    tenant, active = _pick(nav, active_page or "", own_tenant, remembered, solo)
    if tenant is None:
        return []
    pages = tenant.get("pages") or []
    if not pages:
        return []
    start = window_start(active, len(pages), slots)
    return [(p, start + i == active) for i, p in enumerate(pages[start : start + slots])]
