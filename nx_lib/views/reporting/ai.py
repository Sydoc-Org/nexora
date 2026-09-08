"""Reporting AI cluster — Surfaces A-D (ask/build/agent/caption).

Split out of ``nx_lib/views/reporting/__init__.py`` (beautify-phase-2a, Task 1):
the four ``/api/reporting/ai/*`` routes plus their private helpers (provider
config, schema/catalog grounding text, definition validation/normalization,
audit logging, the daily-cap check). The sources/metrics registry helpers and
the live-SQL sandbox helpers these functions call now live on ``_shared.py``
(Task 2), with two exceptions imported directly from their own cluster module
(``_accessible_sql_targets`` from ``run.py``, ``_accessible_curated_sources``
from ``catalog.py``) — none of those modules import back from ``ai.py`` or
from this package's ``__init__.py``, so the imports are eager at module top,
same as every sibling submodule. Because these are plain ``from X import
name`` bindings, a test that wants to stub one of them out must patch it at
its point of use — ``nx_lib.views.reporting.ai.<name>`` — not on ``_shared``,
``run``, or ``catalog``; patching the definition module leaves this module's
already-bound name untouched.
"""

import datetime
import json
import os
import time

from flask import Response, current_app, jsonify, request, session, stream_with_context
from flask_babel import gettext as _

from ...db import engine_nexora_db
from ...extensions import limiter
from ...i18n import get_locale
from ...reporting.ai import (
    _AGENT_EXPLAIN_SUFFIX,
    _AGENT_SYSTEM,
    CAPTION_MAX_ROWS,
    CONTINUE_BUDGET_S,
    CONTINUE_MAX_TURNS,
    EFFORT_AGENT,
    EFFORT_CHOICES,
    MAX_CONTINUE_ATTEMPTS,
    AiError,
    ask_agentic,
    ask_agentic_iter,
    report_context_text,
    stage_preview,
)
from ...reporting.ai import _make_agent_step as make_agent_step
from ...reporting.ai import ask as ai_ask
from ...reporting.ai import ask_definition as ai_ask_definition
from ...reporting.ai import caption as ai_caption
from ...reporting.ai_schema import serialize_schema, serialize_sources_catalog
from ...reporting.ai_tools import RUN_DEFINITION_ROW_CAP, TOOL_SPECS, ToolRegistry
from ...reporting.catalog import fetch_docprocessing_catalog
from ...reporting.runner import execute_definition
from ...reporting.schema import (
    ReportDefinitionError,
    coerce_definition,
    validate_report_definition,
)
from ...reporting.semantic import drop_columns_shadowing_distinct_metrics
from ...reporting.sources import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, accessible
from ...reporting.table_query import table_source_catalog
from ...reporting.tokens import date_fields_from_catalog
from ...security import has_permission, require_permission
from ._shared import (
    _SQL_TARGETS,
    _accessible_metrics,
    _allowed_processes,
    _audit_sql,
    _authorize_sql_target,
    _effective_sources,
    _get_effective_source,
    _has_acked,
    _load_db_metrics,
    _load_field_col_maps,
    _load_process_configs,
    _metrics_for_source,
    _run_sql,
)
from .catalog import _accessible_curated_sources
from .run import _accessible_sql_targets


def _ai_config():
    """Resolve AI provider settings from env. provider 'none' => unconfigured (503)."""
    provider = (os.environ.get("AI_PROVIDER") or "none").lower()
    if provider == "anthropic":
        return {
            "provider": "anthropic",
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "model": os.environ.get("AI_MODEL", "claude-sonnet-4-6"),
            "url": os.environ.get("ANTHROPIC_API_URL"),
        }
    if provider == "azure":
        return {
            "provider": "azure",
            "api_key": os.environ.get("AZURE_OPENAI_KEY"),
            "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", ""),
            "endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT"),
            "deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
            "api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        }
    return {"provider": "none", "api_key": None}


def _ai_schema_text():
    """Build the schema grounding text from accessible RO targets + curated catalogs + metrics."""
    targets = _accessible_sql_targets()
    perms = set(session.get("permissions", []))
    curated = [
        {"label": s.get("label"), "fields": table_source_catalog(s.get("columns"))}
        for s in accessible(_effective_sources(), perms)
        if s.get("kind") == "curated" and s.get("provider") not in (None, "docprocessing")
    ]
    metrics = _accessible_metrics()
    # Mark the Statconfig tables as per-process partial views, so the agent stops
    # answering company-wide questions from whichever single one it found in the
    # flat INFORMATION_SCHEMA dump (issue #128). Statconfig being unavailable just
    # drops the block — never a 500.
    partial_tables: dict = {}
    try:
        allowed = _allowed_processes()
        field_maps = _load_field_col_maps(allowed)
        for cfg in _load_process_configs(allowed):
            if not cfg.get("table"):
                continue
            entry = partial_tables.setdefault(
                cfg["table"],
                {
                    "processes": [],
                    "import_col": cfg.get("import_col"),
                    "export_col": cfg.get("export_col"),
                    "fields": field_maps.get(cfg["process"]) or {},
                },
            )
            entry["processes"].append(cfg["process"])
    except Exception as e:
        current_app.logger.warning(f"reporting.ai schema: Statconfig unavailable: {e}")
    text, truncated = serialize_schema(
        targets=targets,
        curated=curated,
        metrics=metrics or None,
        partial_tables=partial_tables,
    )
    if truncated:
        current_app.logger.info("reporting.ai schema truncated for user=%s", session.get("userid"))
    return text


def _ai_catalog_text():
    """Bounded catalog text for Surface A from the caller's accessible curated sources."""
    text, truncated = serialize_sources_catalog(_accessible_curated_sources())
    if truncated:
        current_app.logger.info("reporting.ai catalog truncated for user=%s", session.get("userid"))
    return text


def _validate_definition_for_user(definition):
    """Validate a model-drafted definition against its source catalog (Surface-A gate).

    Returns (ok, error_message). Reuses the exact validator + source resolution
    that /api/reporting/run uses, so an accepted definition is guaranteed runnable.
    """
    if not isinstance(definition, dict):
        return False, "definition must be an object"
    try:
        source = _get_effective_source(definition.get("source"))
        if source is None or source.get("kind") != "curated":
            return False, "unknown or unsupported source"
        if not has_permission(source["permission"]):
            return False, "not authorized for this source"
        provider = source.get("provider") or "docprocessing"
        if provider == "docprocessing":
            allowed = _allowed_processes()
            catalog = fetch_docprocessing_catalog(allowed, str(get_locale()))
        else:
            catalog = table_source_catalog(source.get("columns"))
        catalog_fields = {f["field"] for f in catalog}
        filterable = {f["field"] for f in catalog if f["filterable"]}
        sortable = {f["field"] for f in catalog if f["sortable"]}
        # Mirror _prepare_run's validator args exactly: without metric_codes and
        # grainable_fields an AI draft using canonical metrics or a date grain
        # would bounce here despite being runnable.
        grainable = {f["field"] for f in catalog if f.get("grainable")}
        source_metrics = _metrics_for_source(source["id"])
        # Repair common small-model near-misses in place (labels-for-keys, missing
        # schemaVersion/title) so an otherwise-correct AI draft is accepted, not
        # bounced. Whitelist-safe: only resolves labels that map to a real field.
        # Mutating `definition` here propagates to what the caller returns/applies
        # (Surface A's result.definition; the agent's build_definition trace args).
        coerce_definition(
            definition,
            catalog,
            default_title=source.get("label"),
            default_row_limit=DEFAULT_ROW_LIMIT,
            max_row_limit=MAX_ROW_LIMIT,
        )
        # A count_distinct metric grouped by its own base field always yields
        # 1 per row — drop the shadowing column instead of bouncing the draft.
        drop_columns_shadowing_distinct_metrics(definition, source_metrics)
        to_validate = {k: v for k, v in definition.items() if k != "chartHint"}
        validate_report_definition(
            to_validate,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields=grainable,
            date_fields=date_fields_from_catalog(catalog),
        )
        return True, None
    except (ReportDefinitionError, PermissionError) as e:
        return False, str(e) or e.__class__.__name__
    except Exception as e:  # resolution failure degrades to "invalid", not 500
        current_app.logger.warning(f"reporting.ai build validation error: {e}")
        return False, "could not validate the drafted report"


def _normalize_definition(definition):
    """Fill the full builder shape so the frontend applyDefinition() consumes it as-is."""
    definition.setdefault("groupBy", [])
    definition.setdefault("subtitle", None)
    definition.setdefault("filters", [])
    definition.setdefault("sort", [])
    definition.setdefault("scope", {"clients": [], "processes": []})
    definition["sql"] = None
    definition["sqlTarget"] = None
    return definition


def _audit_ai(
    userid,
    username,
    prompt,
    surface,
    generated_sql,
    provider,
    model,
    tokens_in,
    tokens_out,
    gate_verdict,
    status,
    duration_ms,
):
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ReportingAiAudit (UserID, Username, Prompt, Surface, "
                "GeneratedSql, Provider, Model, TokensIn, TokensOut, GateVerdict, "
                "Status, DurationMs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    userid,
                    username,
                    prompt,
                    surface,
                    generated_sql,
                    provider,
                    model,
                    tokens_in,
                    tokens_out,
                    gate_verdict,
                    status,
                    duration_ms,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"reporting ai audit insert failed: {e}")
    current_app.logger.info(
        f"reporting.ai surface={surface} user={userid} provider={provider} "
        f"verdict={gate_verdict} status={status} ms={duration_ms}"
    )


def _ai_daily_limit():
    """Per-user/day cap on AI asks. 0 (or unset/invalid) = unlimited (disabled)."""
    try:
        return max(0, int(os.environ.get("AI_DAILY_LIMIT", "0")))
    except (TypeError, ValueError):
        return 0


def _ai_asks_today(userid):
    """Count this user's AI provider calls (ok|error) since UTC midnight.

    Only rows that represent an actual provider call count toward the cap;
    'blocked' throttle rows are excluded so a hit cap never compounds itself.
    """
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM ReportingAiAudit "
            "WHERE UserID = ? AND Status IN ('ok', 'error') "
            "AND CreatedAt >= CAST(SYSUTCDATETIME() AS date)",
            (userid,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


@require_permission("reporting.ai.use")
@limiter.limit("10 per minute")
def api_ai_ask():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": _("A question is required")}), 400
    # Phase 1 produces Surface B (runnable T-SQL); that requires reporting.ai.sql.
    if not has_permission("reporting.ai.sql.use"):
        return jsonify({"error": _("Not authorized to receive AI-drafted SQL")}), 403

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    # Cost/abuse control: a per-user/day cap, enforced BEFORE any provider call
    # (so a throttled ask costs no tokens). 0 disables it. The block is audited.
    limit = _ai_daily_limit()
    if limit > 0 and _ai_asks_today(userid) >= limit:
        current_app.logger.info(
            f"reporting.ai.ask blocked: user={userid} reached daily limit {limit}"
        )
        _audit_ai(
            userid,
            username,
            question,
            "sql",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "blocked",
            0,
        )
        return (
            jsonify(
                {
                    "error": _(
                        "You have reached the daily AI request limit (%(limit)s). "
                        "Please try again tomorrow.",
                        limit=limit,
                    )
                }
            ),
            429,
        )
    schema_text = _ai_schema_text()
    start = time.monotonic()
    try:
        result = ai_ask(
            question,
            schema_text,
            provider=cfg["provider"],
            model=cfg.get("model"),
            api_key=cfg["api_key"],
            endpoint=cfg.get("endpoint"),
            deployment=cfg.get("deployment"),
            api_version=cfg.get("api_version", "2024-10-21"),
            url=cfg.get("url"),
        )
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/ask config error: {e}")
        # Misconfig leaves a trace too, but as 'misconfig' (not 'error') so a broken
        # provider never burns the user's daily quota (_ai_asks_today counts ok|error).
        _audit_ai(
            userid,
            username,
            question,
            "sql",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "misconfig",
            int((time.monotonic() - start) * 1000),
        )
        return jsonify({"error": _("The AI assistant is not configured")}), 503
    except Exception as e:
        current_app.logger.error(f"/api/reporting/ai/ask provider error: {e}")
        _audit_ai(
            userid,
            username,
            question,
            "sql",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "error",
            int((time.monotonic() - start) * 1000),
        )
        return jsonify({"error": _("Eddard could not answer right now")}), 502

    duration_ms = int((time.monotonic() - start) * 1000)
    _audit_ai(
        userid,
        username,
        question,
        "sql",
        result.sql,
        result.provider,
        result.model,
        result.tokens_in,
        result.tokens_out,
        result.gate_verdict,
        "ok",
        duration_ms,
    )
    return jsonify(
        {
            "sql": result.sql,
            "explanation": result.explanation,
            "valid": result.valid,
            "target": "statistics",  # default editor target; user can switch
            "model": result.model,
        }
    )


@require_permission("reporting.ai.use")
@limiter.limit("10 per minute")
def api_ai_build():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": _("A question is required")}), 400

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    limit = _ai_daily_limit()
    if limit > 0 and _ai_asks_today(userid) >= limit:
        _audit_ai(
            userid,
            username,
            question,
            "definition",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "blocked",
            0,
        )
        return jsonify(
            {
                "error": _(
                    "You have reached the daily AI request limit (%(limit)s). "
                    "Please try again tomorrow.",
                    limit=limit,
                )
            }
        ), 429

    # Refine context (optional): prompt grounding ONLY — never executed, never
    # trusted. The model's output still passes _validate_definition_for_user,
    # so a crafted prior definition cannot widen access; its risk class equals
    # free text in `question`. Size caps keep the prompt bounded.
    prior_question = body.get("priorQuestion")
    prior_definition = body.get("priorDefinition")
    if prior_question is not None and (
        not isinstance(prior_question, str) or len(prior_question) > 2000
    ):
        return jsonify({"error": _("Invalid refine context")}), 400
    if prior_definition is not None:
        if not isinstance(prior_definition, dict):
            return jsonify({"error": _("Invalid refine context")}), 400
        try:
            _pd_json = json.dumps(prior_definition)
        except (RecursionError, ValueError):
            return jsonify({"error": _("Invalid refine context")}), 400
        if len(_pd_json) > 20000:
            return jsonify({"error": _("Invalid refine context")}), 400

    catalog_text = _ai_catalog_text()
    start = time.monotonic()
    prior_error = None
    result = None
    valid = False
    for _attempt in range(2):  # initial draft + one bounded self-repair retry
        try:
            result = ai_ask_definition(
                question,
                catalog_text,
                provider=cfg["provider"],
                model=cfg.get("model"),
                api_key=cfg["api_key"],
                endpoint=cfg.get("endpoint"),
                deployment=cfg.get("deployment"),
                api_version=cfg.get("api_version", "2024-10-21"),
                url=cfg.get("url"),
                prior_error=prior_error,
                today=datetime.date.today().isoformat(),
                prior_question=prior_question or None,
                prior_definition=prior_definition or None,
            )
        except AiError as e:
            current_app.logger.warning(f"/api/reporting/ai/build config error: {e}")
            # 'misconfig' (not 'error') so a broken provider never counts against the
            # user's daily cap (_ai_asks_today counts only ok|error).
            _audit_ai(
                userid,
                username,
                question,
                "definition",
                None,
                cfg.get("provider"),
                cfg.get("model"),
                None,
                None,
                "na",
                "misconfig",
                int((time.monotonic() - start) * 1000),
            )
            return jsonify({"error": _("The AI assistant is not configured")}), 503
        except Exception as e:
            current_app.logger.error(f"/api/reporting/ai/build provider error: {e}")
            _audit_ai(
                userid,
                username,
                question,
                "definition",
                None,
                cfg.get("provider"),
                cfg.get("model"),
                None,
                None,
                "na",
                "error",
                int((time.monotonic() - start) * 1000),
            )
            return jsonify({"error": _("Eddard could not answer right now")}), 502
        valid, prior_error = _validate_definition_for_user(result.definition)
        if valid:
            break

    # Every loop iteration either returns early (on an exception) or assigns
    # `result`, so reaching here means the last iteration assigned it.
    assert result is not None
    duration_ms = int((time.monotonic() - start) * 1000)
    definition = _normalize_definition(result.definition) if result.definition else None
    _audit_ai(
        userid,
        username,
        question,
        "definition",
        json.dumps(definition) if definition else None,
        result.provider,
        result.model,
        result.tokens_in,
        result.tokens_out,
        "valid" if valid else "invalid",
        "ok",
        duration_ms,
    )
    return jsonify(
        {
            "definition": definition,
            "explanation": result.explanation,
            "valid": valid,
            "error": None if valid else (prior_error or _("Could not build a valid report")),
        }
    )


def _extract_agent_artifacts(tool_trace):
    """Pull the last validated definition / SQL out of the loop's tool trace.

    A build_definition OR run_definition call that returned ok=True carries a
    runnable definition in its args (run_definition validates the same way before
    executing); a validate_sql ok=True carries gate-approved SQL. These let the UI
    offer one-click 'Open in builder' / 'Insert SQL' just like Surfaces A/B.
    """
    definition, sql = None, None
    for step in tool_trace:
        if not (step.get("result") or {}).get("ok"):
            continue
        if step.get("name") in ("build_definition", "run_definition"):
            d = (step.get("args") or {}).get("definition")
            if isinstance(d, dict):
                definition = _normalize_definition(dict(d))
        elif step.get("name") == "validate_sql":
            sql = (step.get("args") or {}).get("sql")
    return definition, sql


@require_permission("reporting.ai.use")
@limiter.limit("10 per minute")
def api_ai_agent():
    """Surface C — the Tier-2 agentic loop (Phase 3d).

    A self-repairing drafter: the model uses data-free tools (build_definition,
    and validate_sql when the caller holds reporting.ai.sql.use) to produce a
    validated artifact, grounded in the source catalog / SQL schema passed in the
    prompt. Egress stays schema-only — run_sql / compute_stats (whose results
    would flow back to the model) are Phase 3e, behind reporting.ai.explain.use.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": _("A question is required")}), 400

    raw_history = body.get("history")
    if raw_history is not None and not isinstance(raw_history, list):
        return jsonify({"error": _("Invalid history")}), 400
    history = [
        {"role": h["role"], "content": h["content"]}
        for h in raw_history or []
        if (
            isinstance(h, dict)
            and h.get("role") in ("user", "assistant")
            and isinstance(h.get("content"), str)
            and h["content"].strip()
        )
    ]
    history = history[-8:]
    while history and sum(len(h["content"]) for h in history) > 12000:
        history.pop(0)

    # Issue #153: "Continue" past a max_turns/budget dead-end re-runs the same
    # question with raised caps rather than resuming the loop mid-flight (the
    # transcript isn't persisted). continueAttempt is clamped, not rejected
    # out of range, so a stale/tampered client value can't grant more than the
    # ceiling.
    try:
        continue_attempt = int(body.get("continueAttempt") or 0)
    except (TypeError, ValueError):
        continue_attempt = 0
    continue_attempt = max(0, min(continue_attempt, MAX_CONTINUE_ATTEMPTS))

    # Composer effort picker. An unknown level falls back to the loop default
    # rather than 400 - a stale or tampered client must not be able to break a
    # question, and _effort_body drops it again if the model cannot honour it.
    effort = body.get("effort")
    if effort not in EFFORT_CHOICES:
        effort = EFFORT_AGENT
    agent_max_turns = CONTINUE_MAX_TURNS if continue_attempt else None
    agent_budget_s = CONTINUE_BUDGET_S if continue_attempt else None

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    limit = _ai_daily_limit()
    if limit > 0 and _ai_asks_today(userid) >= limit:
        _audit_ai(
            userid,
            username,
            question,
            "agent",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "blocked",
            0,
        )
        return jsonify(
            {
                "error": _(
                    "You have reached the daily AI request limit (%(limit)s). "
                    "Please try again tomorrow.",
                    limit=limit,
                )
            }
        ), 429

    # Tool binding follows the caller's permissions. build_definition is always
    # data-free. validate_sql (also data-free — a gate check) needs reporting.ai.sql.
    # run_sql / compute_stats feed real result rows/stats back to the model, so they
    # are bound ONLY with reporting.ai.explain.use (Phase 3e data-egress grant) AND
    # reporting.sql.run (the live-SQL gate). Without explain.use the loop stays
    # schema-only: no result rows ever reach the model.
    # The client sends the active builder source only as prompt grounding. It is a
    # UI default, not the question's subject: a curated table-provider source (e.g.
    # Generali on GeneraliDB) has no RO SQL target, but the grounding marks such
    # sources builder-only and the system prompt steers run_sql away from them —
    # the data tools stay bound so questions about run_sql-able sources still get
    # real numbers even while the builder happens to sit on a curated source.
    active_source = None
    source_id = (body.get("source") or "").strip()
    if source_id:
        active_source = _get_effective_source(source_id)
    source_is_builder_only = bool(
        active_source
        and active_source.get("kind") == "curated"
        and (active_source.get("provider") or "docprocessing") != "docprocessing"
    )

    has_sql = has_permission("reporting.ai.sql.use")
    explain = has_permission("reporting.ai.explain.use") and has_permission("reporting.sql.run")
    tool_names = {"build_definition"}
    if has_sql:
        tool_names.add("validate_sql")
    if explain:
        tool_names.update({"run_sql", "compute_stats", "run_definition"})
    tools = [t for t in TOOL_SPECS if t["name"] in tool_names]

    run_definition_bound = None
    if explain:

        def run_definition_bound(definition):
            """Run a v1 definition for real and hand back its rows, so the agent
            can quote actual numbers instead of stopping at "definition built,
            not run". Same repair/validate pass as build_definition (a near-miss
            draft is coerced, not bounced), then the exact query the interactive
            builder would run. Capped so one runaway (ungrouped) definition can't
            blow the tool-result context — grouped/anchored reports are naturally
            small (a handful of buckets)."""
            ok, error = _validate_definition_for_user(definition)
            if not ok:
                raise ReportDefinitionError(error or "invalid definition")
            perms = set(session.get("permissions") or [])
            columns, rows = execute_definition(definition, perms, userid, username, get_locale())
            return columns, rows[:RUN_DEFINITION_ROW_CAP]

    run_sql_bound = None
    if explain:

        def run_sql_bound(target, sql):
            """Enforce the same gates api_sql_run applies before touching _run_sql.

            Mirrors api_sql_run's exact composition/order: ack check first, then
            per-target authorization (_authorize_sql_target). D-RUNSQL: binding
            run_sql on reporting.ai.explain.use + reporting.sql.run is not itself
            proof the caller may use THIS target, nor that they've acked the
            sandbox terms — those are checked here, same as the HTTP route.
            Both failures raise (audited with a distinct status first);
            ToolRegistry.call() catches any tool exception and turns it into a
            {"ok": False, "error": ...} result, so this never raises through to a
            500 on /api/reporting/ai/agent — the agent gets a relayable error.
            """
            sql_text = sql if isinstance(sql, str) else ""
            if not _has_acked(userid):
                _audit_sql(userid, username, target, sql_text, None, "refused_ack", None)
                raise PermissionError("Acknowledgment required before running SQL")
            try:
                _authorize_sql_target(target)
            except PermissionError as e:
                _audit_sql(userid, username, target, sql_text, None, "refused_auth", None)
                raise PermissionError(f"Not authorized for SQL target {target!r}") from e
            return _run_sql(target, sql, userid=userid, username=username)

    registry = ToolRegistry(
        run_sql=run_sql_bound,
        validate_definition=_validate_definition_for_user,
        run_definition=run_definition_bound,
    )

    grounding = (
        f"Today's date is {datetime.date.today().isoformat()}.\n\n"
        f"Available report sources and fields:\n{_ai_catalog_text()}"
    )
    if has_sql or explain:
        grounding += f"\n\nSQL schema (for validate_sql / run_sql):\n{_ai_schema_text()}"
        grounding += (
            '\nrun_sql "target" argument MUST be one of: '
            + ", ".join(sorted(_SQL_TARGETS))
            + ". Any other value is rejected."
        )
    if active_source:
        grounding += (
            f'\n\nThe user\'s selected source is "{active_source.get("label")}" '
            f'(id {active_source.get("id")}); "this source" in the question means it. '
            "It is only a UI default — when the question neither says \"this source\" "
            "nor names it, choose the best-fitting source from the catalog instead "
            "(for counting/aggregation questions, one that lists metrics)."
        )
        if source_is_builder_only:
            grounding += (
                " It is builder-only — answer it with build_definition; run_sql cannot " "reach it."
            )
    # "Ask Eddard about this report": the Results tab attaches the report on
    # screen. Definition summary is schema-level; the row fact sheet is data
    # egress and rides only on reporting.ai.explain.use, like the auto-caption.
    report = body.get("report")
    if isinstance(report, dict) and isinstance(report.get("definition"), dict):
        rep_source = _get_effective_source(str(report["definition"].get("source") or ""))
        if rep_source is not None and has_permission(rep_source.get("permission", "")):
            rep_text = report_context_text(
                report,
                metrics=_load_db_metrics(),
                source_label=rep_source.get("label"),
                include_rows=has_permission("reporting.ai.explain.use"),
            )
            if rep_text:
                grounding += "\n\n" + rep_text
    initial = f"{grounding}\n\nQuestion: {question}"
    system_prompt = _AGENT_SYSTEM + (_AGENT_EXPLAIN_SUFFIX if explain else "")

    loop_kwargs = {}
    if agent_max_turns is not None:
        loop_kwargs["max_turns"] = agent_max_turns
    if agent_budget_s is not None:
        loop_kwargs["budget_s"] = agent_budget_s

    start = time.monotonic()

    def _finish(result):
        """Audit a completed loop and shape its response payload.

        Shared by both delivery modes: the plain JSON response and the NDJSON
        progress stream's final `done` line.
        """
        duration_ms = int((time.monotonic() - start) * 1000)
        definition, sql = _extract_agent_artifacts(result.tool_trace)
        _audit_ai(
            userid,
            username,
            question,
            "agent",
            json.dumps(
                {
                    "answer": result.answer,
                    "tools": [t["name"] for t in result.tool_trace],
                    "explainData": explain,
                }
            )[:4000],
            cfg.get("provider"),
            cfg.get("model"),
            result.tokens_in,
            result.tokens_out,
            result.stopped_reason,
            "ok",
            duration_ms,
        )
        # Issue #127: never ship an empty answer — the chat panel would render
        # a blank bubble. The audit above keeps the raw (empty) answer; only
        # the user-facing payload gets the fallback. The in-loop nudge
        # (ask_agentic_iter) already retried once, so this is the last resort:
        # point at whatever artifact the loop did produce, or admit defeat.
        answer = (result.answer or "").strip()
        if not answer:
            if definition is not None and sql:
                answer = _(
                    "I couldn't write a summary this time, but I did produce a "
                    "report draft and a validated SQL query — use the actions "
                    "below to open them."
                )
            elif definition is not None:
                answer = _(
                    "I couldn't write a summary this time, but I did produce a "
                    "report draft — use “Open report” below to run it."
                )
            elif sql:
                answer = _(
                    "I couldn't write a summary this time, but I did draft a SQL "
                    "query — use the actions below to review it."
                )
            else:
                answer = _(
                    "I couldn't complete this request. Please try rephrasing the "
                    "question or narrowing it down."
                )
        return {
            "answer": answer,
            "definition": definition,
            "sql": sql,
            "toolTrace": result.tool_trace,
            "turns": result.turns,
            "stoppedReason": result.stopped_reason,
            "explainData": explain,
            "continueAttempt": continue_attempt,
            "canContinue": (
                result.stopped_reason in ("max_turns", "budget")
                and continue_attempt < MAX_CONTINUE_ATTEMPTS
            ),
        }

    def _audit_failure(status):
        _audit_ai(
            userid,
            username,
            question,
            "agent",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            status,
            int((time.monotonic() - start) * 1000),
        )

    try:
        step = make_agent_step(
            system=system_prompt,
            tools=tools,
            provider=cfg["provider"],
            model=cfg.get("model"),
            api_key=cfg["api_key"],
            endpoint=cfg.get("endpoint"),
            deployment=cfg.get("deployment"),
            api_version=cfg.get("api_version", "2024-10-21"),
            url=cfg.get("url"),
            effort=effort,
        )
        # Streaming mode: the client asked to watch the loop work. NDJSON, one
        # object per line — {"phase": ...} progress events as they happen, then
        # exactly one {"done": true, ...} line carrying the same payload the
        # plain-JSON mode returns. Headers are already sent by then, so a
        # mid-stream failure rides in that final line instead of an HTTP status.
        if body.get("stream"):

            def emit():
                result = None
                try:
                    for event in ask_agentic_iter(
                        initial,
                        registry=registry,
                        agent_step=step,
                        history=history,
                        **loop_kwargs,
                    ):
                        if "result" in event:
                            result = event["result"]
                            break
                        if event.get("phase") == "tool_result":
                            # Raw tool output never reaches the client from a
                            # progress line -- distill it into the tiny
                            # build-stage preview (real title/total/series for
                            # Eddard's mock report) or drop it.
                            preview = stage_preview(
                                event.get("name"), event.get("args"), event.get("output")
                            )
                            if preview:
                                yield json.dumps({"phase": "preview", **preview}) + "\n"
                            continue
                        yield json.dumps(event) + "\n"
                except Exception as e:
                    current_app.logger.error(f"/api/reporting/ai/agent provider error: {e}")
                    _audit_failure("error")
                    yield (
                        json.dumps(
                            {
                                "done": True,
                                "error": _("Eddard could not answer right now"),
                            }
                        )
                        + "\n"
                    )
                    return
                yield json.dumps({"done": True, **_finish(result)}) + "\n"

            return Response(
                stream_with_context(emit()),
                mimetype="application/x-ndjson",
                headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
            )

        result = ask_agentic(
            initial, registry=registry, agent_step=step, history=history, **loop_kwargs
        )
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/agent config error: {e}")
        _audit_failure("misconfig")
        return jsonify({"error": _("The AI assistant is not configured")}), 503
    except Exception as e:
        current_app.logger.error(f"/api/reporting/ai/agent provider error: {e}")
        _audit_failure("error")
        return jsonify({"error": _("Eddard could not answer right now")}), 502

    return jsonify(_finish(result))


def _caption_columns(raw):
    """Normalize a client-supplied column list to [{field, header}] dicts.

    Mirrors api_export_grid's column normalization: bare strings are accepted
    too (field == header == str(c)) so a caller need not always ship the full
    {field, header} shape.
    """
    out = []
    for c in raw:
        if isinstance(c, dict):
            header = c.get("header") or c.get("field") or ""
            out.append({"field": c.get("field") or header, "header": header})
        else:
            out.append({"field": str(c), "header": str(c)})
    return out


@require_permission("reporting.ai.explain.use")
@limiter.limit("10 per minute")
def api_ai_caption():
    """Surface D — a 1-2 sentence auto-caption over a result grid (Task 12).

    Unlike ask/build/agent, this surface's egress is NOT schema-only: `rows`
    are the actual values a Simple/Advanced result is displaying, so it is
    gated by reporting.ai.explain.use (the data-egress grant) rather than the
    weaker reporting.ai.use. It still counts toward the shared daily AI cap and
    is rate limited like the other AI endpoints. Rows never reach the model
    raw: caption() reduces the WHOLE grid to a fact sheet
    (nx_lib/reporting/caption_facts) — CAPTION_MAX_ROWS only bounds the request
    payload. Fired by fireCaption() (Task 13): the Simple tab after every
    successful run render, the Advanced tab on chart mount.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    raw_columns = body.get("columns")
    rows = body.get("rows")
    if not isinstance(raw_columns, list) or not raw_columns or not isinstance(rows, list):
        return jsonify({"error": _("columns and rows are required")}), 400
    columns = _caption_columns(raw_columns)
    rows = [list(r) if isinstance(r, list | tuple) else [r] for r in rows[:CAPTION_MAX_ROWS]]
    title = (body.get("title") or "").strip() or None
    date_label = (body.get("dateLabel") or "").strip() or None
    # Client-side facts about the grid the model can't see (partial current
    # bucket, NULL = no snapshot); bounded like title.
    notes = str(body.get("notes") or "").strip()[:400] or None
    # Level measures (backlog): the fact sheet headlines their latest value
    # instead of summing buckets. Names only, bounded.
    raw_levels = body.get("levelFields")
    level_fields = (
        tuple(str(x)[:100] for x in raw_levels[:20] if isinstance(x, str))
        if isinstance(raw_levels, list)
        else ()
    )

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    limit = _ai_daily_limit()
    if limit > 0 and _ai_asks_today(userid) >= limit:
        _audit_ai(
            userid,
            username,
            title or "",
            "caption",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "blocked",
            0,
        )
        return jsonify(
            {
                "error": _(
                    "You have reached the daily AI request limit (%(limit)s). "
                    "Please try again tomorrow.",
                    limit=limit,
                )
            }
        ), 429

    start = time.monotonic()
    try:
        result = ai_caption(
            columns,
            rows,
            title,
            date_label,
            notes=notes,
            level_fields=level_fields,
            locale=str(get_locale()),
            cfg=cfg,
        )
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/caption config error: {e}")
        _audit_ai(
            userid,
            username,
            title or "",
            "caption",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "misconfig",
            int((time.monotonic() - start) * 1000),
        )
        return jsonify({"error": _("The AI assistant is not configured")}), 503
    except Exception as e:
        current_app.logger.error(f"/api/reporting/ai/caption provider error: {e}")
        _audit_ai(
            userid,
            username,
            title or "",
            "caption",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "error",
            int((time.monotonic() - start) * 1000),
        )
        return jsonify({"error": _("Eddard could not answer right now")}), 502

    duration_ms = int((time.monotonic() - start) * 1000)
    _audit_ai(
        userid,
        username,
        title or "",
        "caption",
        None,
        result.provider,
        result.model,
        result.tokens_in,
        result.tokens_out,
        "na",
        "ok",
        duration_ms,
    )
    return jsonify({"caption": result.caption})


def register_routes(app):
    app.add_url_rule(
        "/api/reporting/ai/ask",
        endpoint="reporting_ai_ask",
        view_func=api_ai_ask,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/ai/build",
        endpoint="reporting_ai_build",
        view_func=api_ai_build,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/ai/agent",
        endpoint="reporting_ai_agent",
        view_func=api_ai_agent,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/ai/caption",
        endpoint="reporting_ai_caption",
        view_func=api_ai_caption,
        methods=["POST"],
    )
