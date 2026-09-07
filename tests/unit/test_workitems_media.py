"""Unit tests for nx_lib.workitems.media -- pure Python, no Flask/session/
request, no database: Octo and the cache are injected by the caller."""

from nx_lib.workitems.media import load_media_info, wi_cache_key


class _FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=None):
        self.store[key] = value


def test_wi_cache_key_includes_domain():
    assert wi_cache_key("media_info", 42, "d.example.com") == "media_info_d.example.com_42"


def test_load_media_info_cache_hit_skips_octo():
    cache = _FakeCache()
    cache.store[wi_cache_key("media_info", 42, "d.example.com")] = {"cached": True}

    def _must_not_run(*a, **k):
        raise AssertionError("Octo must not be called on a cache hit")

    result = load_media_info(
        42,
        "d.example.com",
        get_workitemdata_param=_must_not_run,
        get_extensions_urls_fields=_must_not_run,
        cache=cache,
    )
    assert result == {"cached": True}


def test_load_media_info_returns_none_when_workitem_unresolvable():
    cache = _FakeCache()
    result = load_media_info(
        42,
        "d.example.com",
        get_workitemdata_param=lambda wid, domain: None,
        get_extensions_urls_fields=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not run without workitem data")
        ),
        cache=cache,
    )
    assert result is None


def test_load_media_info_fetches_with_tables_and_caches_full_payload():
    cache = _FakeCache()
    calls = {}

    def _get_extensions_urls_fields(workitemdata, document_id, domain, with_tables=False):
        calls["with_tables"] = with_tables
        return (
            [".pdf"],
            ["https://example.com/a.pdf"],
            {"Amount": "42"},
            [{"key": "Amount", "value": "42", "locations": []}],
            [{"rows": []}],
        )

    result = load_media_info(
        42,
        "d.example.com",
        get_workitemdata_param=lambda wid, domain: ("wdata", "doc-42"),
        get_extensions_urls_fields=_get_extensions_urls_fields,
        cache=cache,
    )

    assert calls["with_tables"] is True  # detail panel always needs the source overlay
    assert result["media_count"] == 1
    assert result["fields"] == {"Amount": "42"}
    assert result["table_sources"] == [{"rows": []}]

    # Written to both the media_info AND media_data cache keys.
    assert cache.store[wi_cache_key("media_info", 42, "d.example.com")] == result
    assert cache.store[wi_cache_key("media_data", 42, "d.example.com")] == {
        "extensions": [".pdf"],
        "urls": ["https://example.com/a.pdf"],
    }


def test_load_media_info_zero_media_does_not_write_media_data_key():
    cache = _FakeCache()

    def _get_extensions_urls_fields(workitemdata, document_id, domain, with_tables=False):
        return [], [], {}, [], []

    load_media_info(
        42,
        "d.example.com",
        get_workitemdata_param=lambda wid, domain: ("wdata", "doc-42"),
        get_extensions_urls_fields=_get_extensions_urls_fields,
        cache=cache,
    )
    assert wi_cache_key("media_data", 42, "d.example.com") not in cache.store
