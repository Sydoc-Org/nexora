"""Schema serialization for the Reporting AI assistant (Phase 1).

Turns the RO SQL targets' INFORMATION_SCHEMA and the curated source catalogs into
a compact text block for the prompt. Bounded by a character budget and a per-target
table cap; truncation is appended as a visible marker and logged so coverage limits
are never silent. Connection factories are injected so this is unit-testable without
a DB; the connection they yield is closed here so pooled RO connections never leak.
"""

import logging

logger = logging.getLogger(__name__)

DEFAULT_CHAR_BUDGET = 12000
MAX_TABLES_PER_TARGET = 60

_COLUMNS_SQL = (
    "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
    "FROM INFORMATION_SCHEMA.COLUMNS "
    "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
)


def serialize_target(target_name, conn_factory, *, max_tables=MAX_TABLES_PER_TARGET):
    """Serialize one RO target's columns grouped by table. `conn_factory()` -> a DBAPI
    connection (closed here); its cursor runs the INFORMATION_SCHEMA query.

    Returns (text, was_capped) where was_capped is True iff the per-target table cap
    fired (i.e. some tables were dropped from the serialization).
    """
    conn = conn_factory()
    try:
        cur = conn.cursor()
        cur.execute(_COLUMNS_SQL)
        rows = cur.fetchall()
    finally:
        conn.close()
    tables = {}
    for r in rows:
        key = f"{r.TABLE_SCHEMA}.{r.TABLE_NAME}"
        tables.setdefault(key, []).append(f"{r.COLUMN_NAME} {r.DATA_TYPE}")
    lines = [f"# Target: {target_name}"]
    was_capped = False
    for i, (tbl, cols) in enumerate(tables.items()):
        if i >= max_tables:
            dropped = len(tables) - max_tables
            noun = "table" if dropped == 1 else "tables"
            lines.append(f"  ... ({dropped} more {noun} truncated)")
            logger.info("ai_schema: target=%s truncated to %d tables", target_name, max_tables)
            was_capped = True
            break
        lines.append(f"TABLE {tbl}({', '.join(cols)})")
    return "\n".join(lines), was_capped


def _serialize_curated(curated):
    lines = []
    for src in curated or []:
        fields = ", ".join(
            f"{f.get('field')} {f.get('type', 'string')}"
            for f in src.get("fields", [])
            if f.get("field")
        )
        label = src.get("label") or "(unnamed)"
        # These curated (table-provider) sources live on databases run_sql cannot
        # reach (run_sql only targets the statistics/octopus RO engines). Spell that
        # out so the explain-data agent uses build_definition for them instead of
        # drafting `SELECT ... FROM <source>` against a run_sql target (→ 208).
        lines.append(
            f"# Curated source (builder-only — answer with build_definition; "
            f"NOT queryable with run_sql): {label}\nFIELDS({fields})"
        )
    return "\n".join(lines)


def serialize_sources_catalog(sources, *, char_budget=DEFAULT_CHAR_BUDGET):
    """Compact, bounded text block of the caller's accessible curated sources.

    `sources`: list of {id, label, fields:[{field,label,type,filterable,sortable}],
    processes:[ids]}. Each field renders as `key "Human Label":type (flags)` (the
    label is dropped when it equals the key). Returns (text, truncated_bool); on
    overflow the text is cut to the budget with a visible marker and the truncation
    is logged.
    """
    lines = []
    for s in sources or []:
        flags_fields = []
        for f in s.get("fields", []):
            flags = []
            if f.get("filterable"):
                flags.append("filterable")
            if f.get("sortable"):
                flags.append("sortable")
            flag_txt = f" ({', '.join(flags)})" if flags else ""
            field = f.get("field")
            label = f.get("label")
            # Show the human label next to the key so the model can map a NL
            # question to the right field, while the validator-checked KEY stays
            # the leading token. Omitted when the label is just the key (table
            # sources default label==field) to keep the catalog compact.
            label_txt = f' "{label}"' if label and label != field else ""
            flags_fields.append(f"{field}{label_txt}:{f.get('type', 'string')}{flag_txt}")
        lines.append(f'SOURCE {s.get("id")} "{s.get("label")}": ' + "; ".join(flags_fields))
        procs = s.get("processes") or []
        if procs:
            lines.append(f"  allowed scope.processes: {', '.join(map(str, procs))}")
    text = "\n".join(lines)
    if len(text) > char_budget:
        logger.info(
            "ai_schema: sources catalog truncated from %d to %d chars", len(text), char_budget
        )
        return text[:char_budget] + "\n... (catalog truncated)", True
    return text, False


def serialize_schema(*, targets, curated, char_budget=DEFAULT_CHAR_BUDGET):
    """Combine RO targets + curated catalogs into a budgeted text block.

    `targets`: {name: conn_factory}. `curated`: list of {label, fields:[{field,type}]}.
    Returns (text, truncated_bool). truncated_bool is True if the char budget cut the
    text *or* any per-target table cap dropped tables — both are coverage limits the
    caller surfaces to the user. On char overflow the text is cut and a visible marker
    appended; truncation is logged.
    """
    blocks = []
    target_capped = False
    for name, factory in (targets or {}).items():
        try:
            block, was_capped = serialize_target(name, factory)
        except Exception as e:  # a missing/unconfigured RO target degrades, not 500s
            logger.warning("ai_schema: target %s unavailable: %s", name, e)
            continue
        blocks.append(block)
        target_capped = target_capped or was_capped
    curated_block = _serialize_curated(curated)
    if curated_block:
        blocks.append(curated_block)
    text = "\n\n".join(b for b in blocks if b)
    if len(text) > char_budget:
        logger.info("ai_schema: schema truncated from %d to %d chars", len(text), char_budget)
        return text[:char_budget] + "\n... (schema truncated)", True
    return text, target_capped
