"""Field config (search_options/labels) and the doc-value search DSL
(#98/#148) extracted from ``nx_lib/views/workitems.py``. Pure Python: no
Flask, no ``session``/``request`` -- callers pass in whatever session/
permission-derived state (``allowed_processes``, ``current_lang``) they need
resolved.
"""

import hashlib

from .. import mapping_config

# Languages a FieldLabels row carries (mapping_config.labels()'s per-key meta
# dict), in the order _build_field_config falls back through.
_LABEL_LANGS = ("en", "de", "fr", "it")


def _build_field_config(allowed_processes, current_lang):
    """search_options ({ProcessName: [{'value','label'}, ...]}) + labels
    (FieldKey -> localized label) pair shared by api_config_fields and
    api_workitems_page_init, read from the mapping_config registry (#98
    phase 2) instead of a live legacy-table introspection. A registry load
    failure degrades both to {} exactly like the legacy per-cell SELECT used
    to on a DB error."""
    target_lang = current_lang if current_lang in _LABEL_LANGS else "en"
    lbls = mapping_config.labels() or {}
    db_labels_map = {key: (meta.get(target_lang) or meta.get("en")) for key, meta in lbls.items()}

    process_fields = {}
    reg = mapping_config.registry()
    if reg is not None:
        for m in reg.mappings:
            if m.process not in allowed_processes:
                continue
            nice_label = db_labels_map.get(m.field_key, m.field_key.replace("_", " ").title())
            process_fields.setdefault(m.process, {})[m.field_key] = {
                "value": m.field_key,
                "label": nice_label,
            }

    search_options = {}
    for process, fields_by_key in process_fields.items():
        search_options[process] = sorted(fields_by_key.values(), key=lambda x: x["label"])

    return search_options, db_labels_map


# Whitelisted doc-value search operators (issue #148): op key -> (SQL Server
# comparator, param builder). `=`/`<>` are real comparisons (CI under the
# DATABASE_DEFAULT collation); the LIKE family keeps the historical
# no-wildcard-escaping behavior. Unknown/missing keys fall back to "contains".
DOCFIELD_OPS = {
    "contains": ("LIKE", lambda v: f"%{v}%"),
    "ncontains": ("NOT LIKE", lambda v: f"%{v}%"),
    "eq": ("=", lambda v: v),
    "neq": ("<>", lambda v: v),
    "startswith": ("LIKE", lambda v: f"{v}%"),
    "endswith": ("LIKE", lambda v: f"%{v}"),
}


def _docfield_op(docops, i):
    """The whitelisted operator key for pair ``i`` ('contains' fallback)."""
    op = (docops[i] if i < len(docops) else "").lower().strip()
    return op if op in DOCFIELD_OPS else "contains"


# Type buckets for the sargable predicate builder below (#98 Task 12).
# Values MUST match ``ColumnType``/``IdColumnType`` exactly as seeded by
# scripts/seed_column_types.py (migration 0076) -- lowercase
# INFORMATION_SCHEMA.COLUMNS values on the SQL Server side (e.g. 'nvarchar',
# 'int'). A bucket that doesn't match the seeded strings silently disables
# the sargable path (falls through to the CAST fallback below -- safe, just
# not faster), so DO NOT "helpfully" add casing/synonym variants without
# checking a live sample first.
_TEXT_TYPES = {"varchar", "nvarchar", "char", "nchar"}
_INT_TYPES = {"int", "bigint", "smallint", "tinyint", "integer"}


def _docfield_predicate(alias, column, column_type, op_key, value):
    """Build a sargable WHERE fragment for a default-leg doc-field predicate
    (#98 Task 12), given the ``ColumnType`` metadata seeded onto
    ``FieldMapping`` (migration 0076). Returns ``(sql, params)`` -- ``sql``
    uses ``?`` placeholders, ``params`` the ordered bind values.

    - TEXT type (``_TEXT_TYPES``): bare column comparison, no CAST. ``eq``
      becomes a seekable ``col = ?``; the LIKE-family ops stay a scan but
      drop the CAST/COLLATE overhead.
    - INT type (``_INT_TYPES``) + ``eq``/``neq``: native int bind, no CAST --
      SEEKABLE. A non-numeric value can never equal an int column, so this
      is resolved at the predicate level rather than hitting the DB:
      ``eq`` -> ``"1=0"`` (can't match -- fails closed, no scan); ``neq`` ->
      ``"1=1"`` (vacuously true: nothing unparseable can fail to differ from
      every int value, so the negation always holds -- this is a predicate-
      level truth, NOT a relaxation of the allow-set fail-closed contract
      used elsewhere in this file).
    - Everything else (INT type + a LIKE-family op, unmapped/unknown type,
      or ``column_type is None``): the legacy, always-correct
      ``CAST(...) AS NVARCHAR(MAX) COLLATE DATABASE_DEFAULT`` fallback.
    """
    op_sql, op_param = DOCFIELD_OPS[op_key]
    col_ref = f"{alias}.{column}"

    if column_type in _INT_TYPES and op_key in ("eq", "neq"):
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            return ("1=0" if op_key == "eq" else "1=1", [])
        return (f"{col_ref} {op_sql} ?", [int_value])

    if column_type in _TEXT_TYPES:
        return (f"{col_ref} {op_sql} ?", [op_param(value)])

    safe_col = f"CAST({col_ref} AS NVARCHAR(MAX))"
    return (f"{safe_col} COLLATE DATABASE_DEFAULT {op_sql} ?", [op_param(value)])


def _docfield_comb(doccombs, i):
    """The AND/OR combinator joining pair ``i`` to the pairs before it
    ('and' fallback; the first pair's value is ignored by the fold)."""
    comb = (doccombs[i] if i < len(doccombs) else "").lower().strip()
    return comb if comb in ("and", "or") else "and"


def _docfield_pairs_normalized(
    docfields, docvalues, docops, doccombs, valid_db_columns, blocked_docfields
):
    """The ``(field_keys, value, op, comb)`` tuples that actually drive a
    leg's pair-fold (#98 Task 13 cache key input) -- mirrors the per-pair
    ``continue`` guards each leg's resolution loop applies (empty value,
    unknown field, sensitive-blocked field), so two requests that resolve
    identically hash identically.

    ``field_keys`` is the RESOLVED sorted tuple of target field keys, not the
    raw ``docfield`` string: for an explicit field it is that one key; for a
    value-first pair (no field picked, #148) it is every permitted
    non-sensitive column, i.e. ``valid_db_columns - blocked_docfields``. Using
    the resolved set (rather than the empty string every value-first pair
    would otherwise normalize to) is what makes sensitive-field filtering
    actually key-scoped: two callers with different sensitive-field
    permissions searching the same bare value would otherwise both normalize
    to the SAME raw-field pair and collide on one cache entry, letting a
    lower-privilege caller inherit a higher-privilege caller's allow-set --
    an allow-set that can include workitem ids matched ONLY via a sensitive
    column the lower-privilege caller must never be able to infer the
    contents of. Keying on the resolved column set instead makes any
    permission difference a genuinely different key. Sensitive-field
    filtering happens here, BEFORE any cache key is built, so a blocked pair
    never contributes to the key.
    """
    pairs = []
    for i, (docfield, docvalue) in enumerate(zip(docfields, docvalues, strict=False)):
        docfield = (docfield or "").lower().strip()
        docvalue = (docvalue or "").strip()
        if not docvalue:
            continue
        if docfield:
            if docfield not in valid_db_columns or docfield in blocked_docfields:
                continue
            field_keys = (docfield,)
        else:
            field_keys = tuple(sorted(c for c in valid_db_columns if c not in blocked_docfields))
            if not field_keys:
                continue
        pairs.append((field_keys, docvalue, _docfield_op(docops, i), _docfield_comb(doccombs, i)))
    return tuple(pairs)


def _docfield_ids_cache_key(leg, target_processes, pairs_normalized):
    """Cache key for a leg's resolved allow-set (#98 Task 13). ``leg`` is
    'default' / 'ms02'. Callers must pair this with the ('v', result) sentinel
    when storing, so a legitimately-empty resolved set is distinguishable
    from a cache miss, and must NEVER cache.set on an error/None path."""
    return (
        f"docfield_ids_{leg}_"
        + hashlib.sha1(repr((sorted(target_processes), pairs_normalized)).encode()).hexdigest()
    )
