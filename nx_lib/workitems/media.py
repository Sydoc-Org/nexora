"""Media/document lookup extracted from ``nx_lib/views/workitems.py``. Pure
Python: no Flask, no ``session``/``request`` -- the caller (session UI or the
external API, both in ``nx_lib/views/``) resolves the workitem's client
domain, supplies its own Octo/cache callables, and applies its own
per-permission suppression on top of the returned payload.
"""


def wi_cache_key(prefix, workitem_id, domain):
    """Per-workitem cache key that includes the resolved client domain -- a bare
    id would let one client's cached document answer for another client's
    identically numbered workitem."""
    return f"{prefix}_{domain}_{workitem_id}"


def load_media_info(
    workitem_id,
    domain,
    *,
    get_workitemdata_param,
    get_extensions_urls_fields,
    cache,
):
    """Fetch-and-cache core of the detail panel: the FULL (pre-suppression)
    media_info payload for (workitem_id, domain), from cache or live Octo.
    Shared by the session UI (api_get_media_info, which applies its
    per-permission _suppress on top) and the external API detail endpoint
    (nx_lib/views/api_external.py, which applies its fixed no-sensitive
    policy). Returns None when the workitem/document can't be loaded --
    unknown id and runtime-backend failure are indistinguishable at this
    layer (get_workitemdata_param collapses both to None). Only ever writes
    the full with-tables shape under the media_info cache key (see the
    cache-poison warning in export_workitems_csv).

    ``get_workitemdata_param``/``get_extensions_urls_fields`` (nx_lib.octo)
    and ``cache`` (nx_lib.extensions, Flask-Caching) are injected by the
    caller rather than imported here, so this module stays Flask-free and the
    caller keeps its usual seam for monkeypatching them in tests."""
    _ck = wi_cache_key("media_info", workitem_id, domain)

    cached_info = cache.get(_ck)
    if cached_info:
        return cached_info

    returndata = get_workitemdata_param(workitem_id, domain)
    if not returndata:
        return None

    workitemdata, document_id = returndata
    doc = get_extensions_urls_fields(workitemdata, document_id, domain, with_tables=True)
    if doc is None:
        # Backend failure, not an empty document. Returning the usual shape here
        # would cache media_count=0 under the media_info key and leave the
        # viewer permanently blank for this workitem, with nothing shown to the
        # user. Flagged instead so the route can answer with an error status --
        # the detail panel already renders `couldNotLoadMedia` for a non-OK
        # response -- and deliberately NOT cached, so the next open retries.
        return {
            "workitem_id": workitem_id,
            "backend_error": True,
            "media_count": 0,
            "fields": {},
            "field_sources": [],
            "table_sources": [],
        }

    extensions, urls, fields, field_sources, table_sources = doc

    media_count = len(urls) if urls else 0

    if media_count > 0:
        cache.set(
            wi_cache_key("media_data", workitem_id, domain),
            {"extensions": extensions, "urls": urls},
        )

    response_data = {
        "workitem_id": workitem_id,
        "media_count": media_count,
        "fields": fields,
        "field_sources": field_sources,
        "table_sources": table_sources,
    }

    cache.set(_ck, response_data)
    return response_data
