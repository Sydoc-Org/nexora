"""Live schema introspection for the Console's source visualizer.

One connection, three catalog queries (objects+columns, row counts, foreign
keys) turned into the payload `static/js/reporting_schema.js` renders as a
table list and an ER diagram. The connection is injected so this is unit
testable without a DB, and closed by the caller's `raw_connection()` wrapper
in the view.

ponytail: SQL Server only -- every engine behind a reporting source
(`_SQL_TARGET_ENGINES` + `_CURATED_ENGINES`) is SQL Server. If a Postgres
source (MS02) ever lands in the rail, branch on the engine dialect here.
"""

import logging

logger = logging.getLogger(__name__)

MAX_TABLES = 400

# Tables and views with their columns, PK flag riding along from the primary-key
# index. sys.* rather than INFORMATION_SCHEMA because the FK/PK/row-count joins
# below need object ids anyway.
_OBJECTS_SQL = """
SELECT s.name AS sch, o.name AS tbl, o.type AS otype,
       c.name AS col, ty.name AS typ, c.max_length AS maxlen,
       c.precision AS prec, c.scale AS scale_, c.is_nullable AS nullable,
       CASE WHEN ic.column_id IS NULL THEN 0 ELSE 1 END AS is_pk
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id = o.schema_id
JOIN sys.columns c ON c.object_id = o.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.indexes pk ON pk.object_id = o.object_id AND pk.is_primary_key = 1
LEFT JOIN sys.index_columns ic ON ic.object_id = o.object_id
                              AND ic.index_id = pk.index_id
                              AND ic.column_id = c.column_id
WHERE o.type IN ('U', 'V') AND o.is_ms_shipped = 0
ORDER BY s.name, o.name, c.column_id
"""

# Approximate row counts (heap/clustered partitions). sys.partitions needs no
# VIEW DATABASE STATE, unlike the dm_db_partition_stats DMV.
_ROWCOUNT_SQL = """
SELECT s.name AS sch, t.name AS tbl, SUM(p.rows) AS rowcnt
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
GROUP BY s.name, t.name
"""

_FK_SQL = """
SELECT fk.name AS fkname,
       ps.name AS from_sch, pt.name AS from_tbl, pc.name AS from_col,
       rs.name AS to_sch, rt.name AS to_tbl, rc.name AS to_col
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.tables pt ON pt.object_id = fkc.parent_object_id
JOIN sys.schemas ps ON ps.schema_id = pt.schema_id
JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id
                   AND pc.column_id = fkc.parent_column_id
JOIN sys.tables rt ON rt.object_id = fkc.referenced_object_id
JOIN sys.schemas rs ON rs.schema_id = rt.schema_id
JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id
                   AND rc.column_id = fkc.referenced_column_id
ORDER BY fk.name, fkc.constraint_column_id
"""

# What a view reads. A reporting source often points at a view (Generali's
# dbo.v_Documents), and the tables behind it are just as "used" as the view --
# without this a view-backed source draws a single lonely box.
_VIEW_DEPS_SQL = """
SELECT vs.name AS from_sch, v.name AS from_tbl, rs.name AS to_sch, ro.name AS to_tbl
FROM sys.sql_expression_dependencies d
JOIN sys.objects v ON v.object_id = d.referencing_id AND v.type = 'V'
JOIN sys.schemas vs ON vs.schema_id = v.schema_id
JOIN sys.objects ro ON ro.object_id = d.referenced_id AND ro.type IN ('U', 'V')
JOIN sys.schemas rs ON rs.schema_id = ro.schema_id
"""

_SIZED = {"varchar", "nvarchar", "char", "nchar", "varbinary", "binary"}
_SCALED = {"decimal", "numeric"}


def format_type(name, max_length, precision, scale):
    """'nvarchar(128)' / 'decimal(18,2)' / 'int' -- what SSMS shows."""
    name = (name or "").lower()
    if name in _SIZED:
        if max_length == -1:
            return f"{name}(max)"
        # nvarchar/nchar store 2 bytes per character.
        chars = max_length // 2 if name.startswith("n") else max_length
        return f"{name}({chars})"
    if name in _SCALED:
        return f"{name}({precision},{scale})"
    return name


def introspect(conn, *, max_tables=MAX_TABLES):
    """{db, tables, relations, truncated} for one already-open connection.

    `tables` are sorted by row count desc (biggest first is what people look
    for), each with its columns; `relations` groups multi-column foreign keys
    into a single edge. Over `max_tables` objects the list is cut and
    `truncated` reports how many were dropped -- never a silent cap.
    """
    cur = conn.cursor()
    cur.execute("SELECT DB_NAME()")
    row = cur.fetchone()
    db_name = row[0] if row else None

    cur.execute(_OBJECTS_SQL)
    tables: dict = {}
    for r in cur.fetchall():
        key = f"{r.sch}.{r.tbl}"
        t = tables.get(key)
        if t is None:
            t = tables[key] = {
                "schema": r.sch,
                "name": r.tbl,
                "kind": "view" if r.otype.strip() == "V" else "table",
                "rows": None,
                "columns": [],
            }
        t["columns"].append(
            {
                "name": r.col,
                "type": format_type(r.typ, r.maxlen, r.prec, r.scale_),
                "nullable": bool(r.nullable),
                "pk": bool(r.is_pk),
            }
        )

    cur.execute(_ROWCOUNT_SQL)
    for r in cur.fetchall():
        t = tables.get(f"{r.sch}.{r.tbl}")
        if t is not None:
            t["rows"] = int(r.rowcnt or 0)

    cur.execute(_FK_SQL)
    relations: dict = {}
    for r in cur.fetchall():
        src, dst = f"{r.from_sch}.{r.from_tbl}", f"{r.to_sch}.{r.to_tbl}"
        rel = relations.get(r.fkname)
        if rel is None:
            rel = relations[r.fkname] = {
                "name": r.fkname,
                "from": src,
                "to": dst,
                "fromColumns": [],
                "toColumns": [],
            }
        rel["fromColumns"].append(r.from_col)
        rel["toColumns"].append(r.to_col)
        rel["kind"] = "fk"

    # View -> table edges, same shape as an FK edge but with no columns: they
    # say "this view reads that table", which is what makes a view-backed
    # source's diagram more than one box.
    cur.execute(_VIEW_DEPS_SQL)
    for r in cur.fetchall():
        src, dst = f"{r.from_sch}.{r.from_tbl}", f"{r.to_sch}.{r.to_tbl}"
        if src == dst:
            continue
        relations.setdefault(
            f"view:{src}->{dst}",
            {
                "name": f"{src} → {dst}",
                "from": src,
                "to": dst,
                "fromColumns": [],
                "toColumns": [],
                "kind": "view",
            },
        )

    # Mark the FK columns on the table side so the list view can link out of a
    # column row without walking `relations` per render.
    by_key = tables
    for rel in relations.values():
        t = by_key.get(rel["from"])
        if not t:
            continue
        targets = dict(zip(rel["fromColumns"], rel["toColumns"], strict=False))
        for c in t["columns"]:
            if c["name"] in targets:
                c["fk"] = {"table": rel["to"], "column": targets[c["name"]]}

    ordered = sorted(
        tables.values(),
        key=lambda t: (-(t["rows"] or 0), t["schema"].lower(), t["name"].lower()),
    )
    truncated = 0
    if len(ordered) > max_tables:
        truncated = len(ordered) - max_tables
        ordered = ordered[:max_tables]
        logger.info("db_schema: %s truncated to %d tables", db_name, max_tables)
        kept = {f"{t['schema']}.{t['name']}" for t in ordered}
        relations = {k: r for k, r in relations.items() if r["from"] in kept and r["to"] in kept}

    return {
        "db": db_name,
        "tables": ordered,
        "relations": sorted(relations.values(), key=lambda r: r["name"] or ""),
        "truncated": truncated,
    }


# ---- "only what this source reads" ---------------------------------------

_QUOTES = '[]"`'


def bare_name(qualified):
    """'dbo.PriveraInvoice' / 'public."DossierStatistik"' -> 'priverainvoice' /
    'dossierstatistik'. Schema and quoting vary per registry row; the object
    name is what identifies a table across them."""
    name = str(qualified or "").strip()
    name = name.rsplit(".", 1)[-1]
    return name.strip(_QUOTES).strip().lower()


def filter_used(payload, used_names, *, expand_fk=True):
    """Narrow an introspect() payload to the tables the reporting layer reads.

    `used_names` are qualified names from the source registry (a source's
    BaseObject plus dbo.ProcessSources.TableName) -- matched on the bare object
    name, since the registries qualify them inconsistently. With `expand_fk`
    two things come along, so the diagram shows the neighbourhood a used table
    lives in instead of one lonely box: everything a used **view** reads
    (transitively -- a view's tables are as used as the view it feeds), then
    one hop across foreign keys from that set.

    A `used_names` that matches nothing in this database (the common case for
    a source whose queries are hand-written) falls back to dropping tables
    that hold no rows -- something is always better than an empty panel.

    Mutates and returns `payload`, adding `filter` ('used' | 'nonempty') and
    `hidden` (how many tables were dropped -- never a silent filter).
    """
    wanted = {bare_name(n) for n in (used_names or ()) if n}
    keys = [f"{t['schema']}.{t['name']}" for t in payload["tables"]]
    keep = {k for k in keys if bare_name(k) in wanted}
    mode = "used"
    if keep and expand_fk:
        changed = True
        while changed:
            changed = False
            for rel in payload["relations"]:
                if rel.get("kind") == "view" and rel["from"] in keep and rel["to"] not in keep:
                    keep.add(rel["to"])
                    changed = True
        seed = set(keep)
        for rel in payload["relations"]:
            if rel["from"] in seed or rel["to"] in seed:
                keep |= {rel["from"], rel["to"]}
        keep &= set(keys)
    if not keep:
        mode = "nonempty"
        # rows is None for views (no row count exists) -- keep those.
        keep = {
            k
            for k, t in zip(keys, payload["tables"], strict=True)
            if t["rows"] is None or t["rows"] > 0
        }
    before = len(payload["tables"])
    payload["tables"] = [t for k, t in zip(keys, payload["tables"], strict=True) if k in keep]
    payload["relations"] = [
        r for r in payload["relations"] if r["from"] in keep and r["to"] in keep
    ]
    payload["filter"] = mode
    payload["hidden"] = before - len(payload["tables"])
    return payload
