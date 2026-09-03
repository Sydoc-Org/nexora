"""Sensitive-field gating (#98 phase 2) extracted from
``nx_lib/views/workitems.py``. Pure Python: no Flask, no ``session``/
``request``. The permission check itself (``has_permission(...)``, which
reads ``session``) is Flask-coupled and stays in the view -- functions here
take the already-resolved boolean (``has_sensitive_perm``) as an explicit
argument instead, per the plan's D4.
"""

import re

from .. import mapping_config


def _norm_field_token(s):
    """Normalize a field name for cross-namespace matching: lowercase, strip
    everything but [a-z0-9] so 'Validation User' / 'validation_user' /
    'ValidationUser' all collapse to the same token."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def get_valid_search_columns():
    """Whitelist of field keys backing doc-field search, derived from the
    mapping_config field-key registry (#98). Bare lowercase keys -- the
    col_<field> internal-column convention was retired in task 6; callers
    compare/interpolate these directly. Caching (success-only, on a DB blip)
    lives in mapping_config.registry() itself."""
    return list(mapping_config.valid_field_keys())


def get_search_columns_for_processes(processes):
    """mapping_config field keys mapped for at least one of the given
    "client.process" entries -- the per-scope companion to
    get_valid_search_columns (which is table-wide). Bare lowercase keys (the
    col_ prefix was retired in task 6). Returns None when the lookup fails so
    callers can fail closed (external API contract); an empty input
    short-circuits to an empty set without a lookup."""
    if not processes:
        return set()
    return mapping_config.field_keys_for_processes(processes)


def strip_sensitive_fields(fields, blocked_tokens):
    """Copy of an Octo extraction ``fields`` dict (or any name->value mapping)
    with entries whose normalized key is blocked removed. Empty blocked set =>
    plain copy (never mutates the input, which may be a cached object)."""
    if not blocked_tokens:
        return dict(fields)
    return {k: v for k, v in fields.items() if _norm_field_token(k) not in blocked_tokens}


def drop_sensitive_options(search_options, blocked_keys):
    """Copy of the api_config_fields {proc: [{'value','label'}, ...]} map with
    options whose value (a doc-field FieldKey) is blocked removed."""
    if not blocked_keys:
        return dict(search_options)
    return {
        proc: [f for f in fields if (f.get("value") or "").lower() not in blocked_keys]
        for proc, fields in search_options.items()
    }


def get_sensitive_field_keys():
    """Lowercased FieldKeys flagged sensitive in the mapping_config label
    registry (#98 phase 2), or None when the lookup fails. Caching
    (success-only) now lives in mapping_config.registry() itself. Callers
    decide the failure posture: sensitive_blocked_keys below coerces None to
    set() (fail-open behind the caller's permission, the historical
    behaviour); the external API (nx_lib/views/api_external.py) fails CLOSED
    on None -- its contract is unconditional blocking with no permission
    fallback."""
    return mapping_config.sensitive_field_keys()


def get_sensitive_field_tokens():
    """Normalized name-tokens (FieldKey + all four language labels) of sensitive
    fields, for matching against Octo extraction field names shown in the detail
    panel / CSV export. None on any error; see get_sensitive_field_keys for the
    failure-posture contract."""
    lbls = mapping_config.labels()
    if lbls is None:
        return None
    tokens = set()
    for key, meta in lbls.items():
        if not meta.get("sensitive"):
            continue
        for val in (key, meta.get("en"), meta.get("de"), meta.get("fr"), meta.get("it")):
            t = _norm_field_token(val)
            if t:
                tokens.add(t)
    return tokens


def sensitive_blocked_keys(has_sensitive_perm):
    """FieldKeys the caller may not use (empty if ``has_sensitive_perm``).
    Coerces a failed lookup (None) to set() -- in-app fail-open, unchanged.
    ``has_sensitive_perm`` is the caller's
    ``workitems.filter.documentfields.sensitive`` permission, resolved by the
    Flask-aware caller (``has_permission(...)`` reads ``session``) and passed
    in explicitly so this module never touches session itself."""
    if has_sensitive_perm:
        return set()
    return get_sensitive_field_keys() or set()


def sensitive_blocked_tokens(has_sensitive_perm):
    """Octo name-tokens the caller may not see (empty if ``has_sensitive_perm``).
    Coerces a failed lookup (None) to set() -- in-app fail-open, unchanged.
    See sensitive_blocked_keys for the ``has_sensitive_perm`` contract."""
    if has_sensitive_perm:
        return set()
    return get_sensitive_field_tokens() or set()


def strip_sensitive_from_detail(data, blocked_tokens):
    """Copy of a get_media_info payload with sensitive extraction fields removed:
    the ``fields`` dict AND the ``field_sources`` list (so the highlight overlay
    can't leak the value/location either). Empty blocked set => plain copy."""
    if not blocked_tokens:
        return data
    d = dict(data)
    d["fields"] = strip_sensitive_fields(d.get("fields", {}) or {}, blocked_tokens)
    d["field_sources"] = [
        s
        for s in (d.get("field_sources") or [])
        if _norm_field_token(s.get("key", "")) not in blocked_tokens
    ]
    return d


def strip_export_fields(details_map, blocked_tokens):
    """In-place: drop sensitive field entries from every detail's fields dict
    before CSV headers/rows are built. No-op when blocked_tokens is empty."""
    if not blocked_tokens:
        return
    for detail in details_map.values():
        if detail.get("fields"):
            detail["fields"] = strip_sensitive_fields(detail["fields"], blocked_tokens)
