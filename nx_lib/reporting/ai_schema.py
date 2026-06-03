"""Schema serialization for the Reporting AI assistant (Phase 1).

Turns the RO SQL targets' INFORMATION_SCHEMA and the curated source catalogs into
a compact text block for the prompt. Bounded by a character budget and a per-target
table cap; truncation is appended as a visible marker and logged so coverage limits
are never silent. Cursor factories are injected so this is unit-testable without a DB.
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


def serialize_target(target_name, cursor_factory, *, max_tables=MAX_TABLES_PER_TARGET):
    """Serialize one RO target's columns grouped by table. `cursor_factory()` -> cursor."""
    cur = cursor_factory()
    cur.execute(_COLUMNS_SQL)
    tables = {}
    for r in cur.fetchall():
        key = f"{r.TABLE_SCHEMA}.{r.TABLE_NAME}"
        tables.setdefault(key, []).append(f"{r.COLUMN_NAME} {r.DATA_TYPE}")
    lines = [f"# Target: {target_name}"]
    for i, (tbl, cols) in enumerate(tables.items()):
        if i >= max_tables:
            lines.append(f"  ... ({len(tables) - max_tables} more tables truncated)")
            logger.info("ai_schema: target=%s truncated to %d tables", target_name, max_tables)
            break
        lines.append(f"TABLE {tbl}({', '.join(cols)})")
    return "\n".join(lines)


def _serialize_curated(curated):
    lines = []
    for src in curated or []:
        fields = ", ".join(
            f"{f.get('field')} {f.get('type', 'string')}" for f in src.get("fields", [])
        )
        lines.append(f"# Curated source: {src.get('label')}\nFIELDS({fields})")
    return "\n".join(lines)


def serialize_schema(*, targets, curated, char_budget=DEFAULT_CHAR_BUDGET):
    """Combine RO targets + curated catalogs into a budgeted text block.

    `targets`: {name: cursor_factory}. `curated`: list of {label, fields:[{field,type}]}.
    Returns (text, truncated_bool). On overflow, the text is cut to the budget and a
    visible marker appended; truncation is logged.
    """
    blocks = []
    for name, factory in (targets or {}).items():
        try:
            blocks.append(serialize_target(name, factory))
        except Exception as e:  # a missing/unconfigured RO target degrades, not 500s
            logger.warning("ai_schema: target %s unavailable: %s", name, e)
    curated_block = _serialize_curated(curated)
    if curated_block:
        blocks.append(curated_block)
    text = "\n\n".join(b for b in blocks if b)
    if len(text) > char_budget:
        logger.info("ai_schema: schema truncated from %d to %d chars", len(text), char_budget)
        return text[:char_budget] + "\n... (schema truncated)", True
    return text, False
