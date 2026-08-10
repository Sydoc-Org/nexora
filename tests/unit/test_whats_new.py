"""Pure-logic tests for the What's New helpers (#169)."""

import re

from nx_lib.whats_new import RELEASES, _ver, has_unseen, visible_releases


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


def test_has_unseen():
    newest = RELEASES[0]["version"]
    assert has_unseen(None, lambda code: True)  # never seen -> badge
    assert not has_unseen(newest, lambda code: True)  # up to date -> no badge
    assert has_unseen("2.5.64", lambda code: True)  # older -> badge
    # A user who can see no gated entries still has the ungated ones.
    assert has_unseen(None, lambda code: False)
