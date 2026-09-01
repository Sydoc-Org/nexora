"""Pure-logic tests for the What's New helpers (#169)."""

import re
from unittest.mock import MagicMock, patch

from nx_lib import user_cache
from nx_lib.whats_new import (
    RELEASES,
    _ver,
    has_unseen,
    load_seen_version,
    mark_seen,
    visible_releases,
)


def test_releases_data_is_well_formed():
    """Curation-time guardrails: a malformed release dict must fail CI, not
    silently mis-render or kill the badge logic."""
    assert RELEASES, "RELEASES must never be empty once the page exists"
    versions = [_ver(rel["version"]) for rel in RELEASES]
    assert all(v != (0,) for v in versions), "unparsable version string"
    assert versions == sorted(versions, reverse=True), "releases must be newest-first"
    assert len(set(versions)) == len(versions), "duplicate release version"
    for rel in RELEASES:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", rel["date"]), rel["date"]
        assert rel["entries"], f"release {rel['version']} has no entries"
        for e in rel["entries"]:
            assert str(e["title"]).strip() and str(e["body"]).strip()
            assert e["perm"] is None or re.fullmatch(r"[a-z0-9_.]+", e["perm"]), e["perm"]
            assert e["icon"].strip() and not e["icon"].startswith("fa-"), e["icon"]


def test_ver_ordering():
    assert _ver("3.1") > _ver("2.5.64")
    assert _ver("2.5.64") > _ver("2.5.9")
    assert _ver(None) == (0,)
    assert _ver("garbage") == (0,)


def test_visible_releases_filters_by_permission():
    rels = visible_releases(lambda code: False)
    # Ungated entries (perm None) must survive for everyone.
    assert all(e["perm"] is None for r in rels for e in r["entries"])
    all_rels = visible_releases(lambda code: True)
    assert sum(len(r["entries"]) for r in all_rels) == sum(len(r["entries"]) for r in RELEASES)


def test_visible_releases_drops_empty_releases():
    only_admin = visible_releases(lambda code: code == "admin.status.view")
    for rel in only_admin:
        assert rel["entries"]


def _mock_conn(seen_version):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (seen_version,) if seen_version is not None else None
    return conn


def test_load_seen_version_is_cached(monkeypatch):
    """A second call within the TTL must not hit the engine at all."""
    user_cache.clear()
    monkeypatch.setenv("NEXORA_USER_CACHE_TTL", "30")
    with patch("nx_lib.whats_new.engine_nexora_db.raw_connection") as raw_conn:
        raw_conn.return_value = _mock_conn("3.1")
        assert load_seen_version(99) == "3.1"
        assert load_seen_version(99) == "3.1"
        assert raw_conn.call_count == 1  # second call served from the TTL cache


def test_mark_seen_busts_the_cache(monkeypatch, app):
    """mark_seen's UPDATE must invalidate the cached seen-version so the very
    next read reflects the new value instead of the stale cached one."""
    user_cache.clear()
    monkeypatch.setenv("NEXORA_USER_CACHE_TTL", "30")
    with patch("nx_lib.whats_new.engine_nexora_db.raw_connection") as raw_conn:
        raw_conn.return_value = _mock_conn("3.1")
        assert load_seen_version(99) == "3.1"
        assert raw_conn.call_count == 1

        raw_conn.return_value = _mock_conn("3.2.3")
        with app.test_request_context("/whats_new"):
            mark_seen(99)

        assert load_seen_version(99) == "3.2.3"
        assert raw_conn.call_count == 3  # mark_seen's UPDATE + the reloaded SELECT


def test_has_unseen():
    newest = RELEASES[0]["version"]
    assert has_unseen(None, lambda code: True)  # never seen -> badge
    assert not has_unseen(newest, lambda code: True)  # up to date -> no badge
    assert has_unseen("2.5.64", lambda code: True)  # older -> badge
    # A user who can see no gated entries still has the ungated ones.
    assert has_unseen(None, lambda code: False)
