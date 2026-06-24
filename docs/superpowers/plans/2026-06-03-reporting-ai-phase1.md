# Reporting AI Assistant — Phase 1 (NL → SQL into the editor) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Ask AI" mode to the Reporting page that turns a natural-language question into **runnable T-SQL placed in the existing SQL editor** (no auto-run), with a one-line explanation — routing every model output through the *unchanged* sqlglot gate + ack + RO-engine run path, and auditing every interaction.

**Architecture:** The LLM only *drafts* SQL; nexora's existing rails dispose. A new server-side, provider-agnostic AI client (`nx_lib/reporting/ai.py`, called via `requests` — no vendor SDK) assembles a prompt from a bounded, cached schema serialization (`nx_lib/reporting/ai_schema.py`) built from the RO targets' `INFORMATION_SCHEMA` plus the curated source catalogs the caller can already see. A new gated route `POST /api/reporting/ai/ask` returns `{sql, explanation, valid}` (schema-only egress — never result rows), self-validates the draft through `sandbox.validate_select`, and writes a row to `dbo.ReportingAiAudit`. The frontend adds an "Ask AI" panel whose only action is **Insert into SQL editor**, after which the user runs it through the *existing* `reporting.sql.run` gated path. No new execution path is introduced.

**Tech Stack:** Flask (Jinja + vanilla-JS inline partials), `requests` (provider HTTP), `sqlglot` (already the gate), pyodbc/SQLAlchemy raw connections, SQL Server migrations via `scripts/db-migrate.py`, pytest, Flask-Babel (de/fr/it).

---

## Provider decision (ups/downs) — to resolve before/while building

The build is **provider-agnostic** (`AI_PROVIDER` switch), so this plan is **not blocked** on the choice — but the credential/compliance call should be made before turning it on in PROD. The owner asked for the tradeoffs:

| | **Azure OpenAI** | **Claude API (Anthropic)** | **Provider-agnostic shell (this plan's default)** |
|---|---|---|---|
| **Data residency** | ✅ Stays in your Azure tenant; aligns with the existing MS Graph/Azure footprint. Easiest compliance story for an internal Sydoc portal. | ⚠️ Question + schema metadata leave the tenant. Needs zero-retention / enterprise terms (Anthropic offers these, but it's a procurement step). | ✅ Neither key required to build/test; egress is **schema-only** regardless of provider. |
| **SQL / tool-use quality** | ✅ Good (GPT-4o / o-series). | ✅✅ Excellent at T-SQL and tool-use; we're already an Anthropic shop (Claude Code). Best raw drafting quality. | n/a — quality is whatever you wire. |
| **Setup cost** | ⚠️ Provision an Azure OpenAI resource + deployment; manage endpoint/key/deployment/api-version. | ✅ One API key. | ✅ Both clients stubbed; flip `AI_PROVIDER` when a key exists. |
| **Ongoing** | Billed via Azure; model availability/parity varies by region. | Billed via Anthropic; simplest API surface. | — |
| **Recommendation** | **Likely the compliance default** for go-live. | **Best quality**; viable if zero-retention terms are acceptable. | **Build on this**, default `AI_PROVIDER=none` (endpoint 503s like an unconfigured RO source) until the owner picks and provisions a key. |

**Plan's stance:** implement both client paths behind `AI_PROVIDER`; ship with `AI_PROVIDER=none` so nothing calls out until the owner sets `AI_PROVIDER=azure` (+ `AZURE_OPENAI_*`) or `AI_PROVIDER=anthropic` (+ `ANTHROPIC_API_KEY`). The egress contract is identical either way: **the NL question + schema metadata only; never result rows** (Phase 1 has no `explain_data`).

---

## Phase-1 scope (from `docs/design/reporting-ai-assistant.md` §12 + the owner's decisions)

**In scope**
- "Ask AI" mode → **T-SQL into the SQL editor only** (no auto-run) + a 1-line explanation.
- **Server-side** provider call (browser never calls the model → **no CSP `connect-src` change**).
- Schema grounding from the **RO targets'** `INFORMATION_SCHEMA` **and** the curated source catalogs — across **all registered sources the caller can access** (owner's choice), bounded by a char budget + per-target cap, cached, with truncation **logged** (no silent caps).
- New perms `reporting.ai.use` (ask) and `reporting.ai.sql` (receive SQL; granted alongside `reporting.sql.run`), seeded to admin profiles.
- New audit table `dbo.ReportingAiAudit`.
- Reuses, unchanged: `validate_select`/`wrap_with_cap` (gate), `dbo.ReportingSqlAck` (ack), `/api/reporting/sql/run` (gated run), the RO engines.

**Out of scope (later phases)** — Surface A (NL → report-definition / builder auto-fill, Phase 2); the agentic tool-loop + self-repair, `compute_stats`, RAG/glossary, "explain these rows" / data egress (`reporting.ai.explain_data`), the semantic layer (Phases 3–4).

**Phase-1 acceptance:** a user with `reporting.ai.use` + `reporting.ai.sql` types a question, receives T-SQL that **passes `validate_select`** in the editor, can run it via the existing gated path, and the interaction is recorded in `dbo.ReportingAiAudit`. No new execution path; **no data egress beyond the question + schema metadata.**

---

## File structure

**Create**
- `nx_lib/reporting/ai.py` — provider-agnostic client: prompt assembly, `AI_PROVIDER` dispatch (`_call_anthropic` / `_call_azure`), response parsing, and **self-validation** of the drafted SQL through `sandbox.validate_select`. DB-free; HTTP transport injectable for tests.
- `nx_lib/reporting/ai_schema.py` — `serialize_schema(...)`: build a bounded, cached schema text from RO `INFORMATION_SCHEMA` + curated catalogs. Cursor/engine injectable for tests.
- `templates/js/_reporting_ai_js.html` — vanilla-JS "Ask AI" panel logic (matches the existing inline-partial pattern).
- `sql/_migrations/NexoraDB/0013_create_reporting_ai_audit.sql` — `dbo.ReportingAiAudit`.
- `sql/_migrations/NexoraDB/0014_seed_reporting_ai_permissions.sql` — `reporting.ai.use` + `reporting.ai.sql`, seeded to admin profiles.
- `tests/unit/test_reporting_ai.py`
- `tests/unit/test_reporting_ai_schema.py`
- `tests/integration/test_reporting_ai_routes.py`

**Modify**
- `nx_lib/views/reporting.py` — add `api_ai_ask`, the `_audit_ai` helper, an `_accessible_sql_targets()` helper, and register `POST /api/reporting/ai/ask`. Pass an `ai_enabled` flag to the template.
- `templates/reporting.html` — add the gated **Ask AI** mode button + the Ask-AI panel; include `_reporting_ai_js.html`.
- `static/css/reporting.css` — panel styles (+ a `.rp-anim` hook so the existing Motion layer can animate it).
- `env/INT.env.example`, `env/PROD.env.example`, `env/STAGING.env.example`, `env/TEST.env.example` — `AI_*` keys (sanitised).
- `CHANGELOG.md`, `docs/howto/reporting.md`, `CLAUDE.md` — doc the new perms/route/env/table.
- `messages.pot` + `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`) — new UI strings.

**No change needed**
- `requirements.txt` — `requests` + `sqlglot` already present; Phase 1 adds **no** dependency.
- `.github/workflows/deploy.yml` — all new runtime files are under `nx_lib/`, `templates/`, `static/`; new files under `sql/_migrations/` and `docs/` follow existing handling. No new top-level runtime artifact.
- CSP in `nx_lib/config.py` — server-side provider call; no `connect-src`/`script-src` change.

---

## Task 1: DB migration — `ReportingAiAudit` table + `reporting.ai.*` permissions

**Files:**
- Create: `sql/_migrations/NexoraDB/0013_create_reporting_ai_audit.sql`
- Create: `sql/_migrations/NexoraDB/0014_seed_reporting_ai_permissions.sql`

SQL migrations are verified by applying to INT and smoke-querying (the pre-commit `sql-migrate-int` hook auto-applies on commit; here we apply explicitly first).

- [ ] **Step 1: Write the audit-table migration**

`sql/_migrations/NexoraDB/0013_create_reporting_ai_audit.sql`:

```sql
-- 0013_create_reporting_ai_audit.sql
-- Phase 1 AI assistant: audit log of every NL->SQL interaction. Schema-only
-- egress (the prompt + generated SQL are recorded; never result rows). Idempotent.
IF OBJECT_ID(N'dbo.ReportingAiAudit', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingAiAudit (
        Id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportingAiAudit PRIMARY KEY,
        UserID        INT NULL,
        Username      NVARCHAR(100) NULL,
        Prompt        NVARCHAR(MAX) NOT NULL,
        Surface       NVARCHAR(16) NOT NULL,   -- sql (Phase 1 only)
        GeneratedSql  NVARCHAR(MAX) NULL,
        Model         NVARCHAR(100) NULL,
        Provider      NVARCHAR(32) NULL,
        TokensIn      INT NULL,
        TokensOut     INT NULL,
        GateVerdict   NVARCHAR(16) NULL,       -- valid | invalid | na
        Status        NVARCHAR(16) NOT NULL,   -- ok | error
        DurationMs    INT NULL,
        CreatedAt     DATETIME2 NOT NULL
                      CONSTRAINT DF_ReportingAiAudit_CreatedAt DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_ReportingAiAudit_User ON dbo.ReportingAiAudit(UserID, CreatedAt);
END;
GO
```

- [ ] **Step 2: Write the permission-seed migration**

`sql/_migrations/NexoraDB/0014_seed_reporting_ai_permissions.sql` (mirrors `0007`/`0008` exactly — seed to every profile that already grants `admin.view` with Effect 'A'; remain grantable; idempotent):

```sql
-- 0014_seed_reporting_ai_permissions.sql
-- Phase 1 AI assistant permissions:
--   reporting.ai.use  -- ask the assistant
--   reporting.ai.sql  -- receive runnable T-SQL (grant alongside reporting.sql.run)
-- Both seeded to every access profile that already grants admin.view (Effect 'A'),
-- so admins/owner have them out of the box. Grantable per-user. Idempotent.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.ai.use', 'Reporting: use the AI assistant (NL questions)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'reporting.ai.use');
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.ai.sql', 'Reporting: receive AI-drafted read-only T-SQL (grant with reporting.sql.run)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'reporting.ai.sql');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code IN ('reporting.ai.use', 'reporting.ai.sql')
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
```

- [ ] **Step 3: Apply to INT and verify**

Run:
```bash
python scripts/db-migrate.py --env INT
```
Expected: reports `0013_...` and `0014_...` applied (or, if already run while prototyping in SSMS, use `python scripts/db-migrate.py --env INT --mark-applied` first — see CLAUDE.md).

Smoke-check in SSMS or via a quick query that the table and perms exist:
```sql
SELECT COUNT(*) FROM dbo.ReportingAiAudit;                 -- 0, table exists
SELECT Code FROM dbo.Permission WHERE Code LIKE 'reporting.ai.%';  -- 2 rows
```
Expected: table returns 0; permission query returns `reporting.ai.use`, `reporting.ai.sql`.

- [ ] **Step 4: Commit**

```bash
git add sql/_migrations/NexoraDB/0013_create_reporting_ai_audit.sql \
        sql/_migrations/NexoraDB/0014_seed_reporting_ai_permissions.sql
git commit -m "feat(reporting): ReportingAiAudit table + reporting.ai.* perms (AI Phase 1)"
```
(The pre-commit `sql-sync-check` re-dumps per-object DDL; let it.)

---

## Task 2: Provider-agnostic AI client (`nx_lib/reporting/ai.py`)

Pure module: assemble the prompt, dispatch to the configured provider over an **injectable HTTP transport**, parse the JSON answer, and **self-validate** the SQL through the existing gate. No Flask, no DB.

**Files:**
- Create: `nx_lib/reporting/ai.py`
- Test: `tests/unit/test_reporting_ai.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_reporting_ai.py`:

```python
"""Unit tests for the provider-agnostic reporting AI client (no DB, no network)."""
import json

import pytest

from nx_lib.reporting import ai


def _fake_transport(payload):
    """Return a transport() that yields a canned provider HTTP JSON body."""
    def transport(url, headers, body, timeout):
        return payload
    return transport


def test_ask_anthropic_extracts_sql_and_validates():
    # Anthropic /v1/messages response shape: content[].text + usage.
    answer = {"sql": "SELECT TOP (10) Name FROM dbo.Foo", "explanation": "Top 10 names."}
    body = {
        "content": [{"type": "text", "text": json.dumps(answer)}],
        "usage": {"input_tokens": 120, "output_tokens": 30},
    }
    res = ai.ask(
        "first 10 names", "TABLE dbo.Foo(Name nvarchar)",
        provider="anthropic", model="claude-sonnet-4-6", api_key="k",
        transport=_fake_transport(body),
    )
    assert res.sql == "SELECT TOP (10) Name FROM dbo.Foo"
    assert res.explanation == "Top 10 names."
    assert res.valid is True
    assert res.gate_verdict == "valid"
    assert res.tokens_in == 120 and res.tokens_out == 30
    assert res.model == "claude-sonnet-4-6"


def test_ask_azure_response_shape():
    answer = {"sql": "SELECT 1 AS X", "explanation": "constant"}
    body = {
        "choices": [{"message": {"content": json.dumps(answer)}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 8},
    }
    res = ai.ask(
        "give me one", "(* no schema *)",
        provider="azure", model="gpt-4o", api_key="k",
        endpoint="https://x.openai.azure.com", deployment="gpt-4o",
        transport=_fake_transport(body),
    )
    assert res.sql == "SELECT 1 AS X"
    assert res.valid is True
    assert res.tokens_in == 50 and res.tokens_out == 8


def test_ask_marks_invalid_when_model_emits_non_select():
    answer = {"sql": "DROP TABLE dbo.Foo", "explanation": "oops"}
    body = {"content": [{"type": "text", "text": json.dumps(answer)}], "usage": {}}
    res = ai.ask(
        "drop it", "TABLE dbo.Foo(Name)",
        provider="anthropic", model="m", api_key="k",
        transport=_fake_transport(body),
    )
    assert res.valid is False
    assert res.gate_verdict == "invalid"
    assert res.sql == "DROP TABLE dbo.Foo"   # still returned so the user sees it


def test_ask_falls_back_to_fenced_block_when_not_json():
    text = "Here you go:\n```sql\nSELECT 2 AS Y\n```\nThat returns 2."
    body = {"content": [{"type": "text", "text": text}], "usage": {}}
    res = ai.ask(
        "two", "(* none *)", provider="anthropic", model="m", api_key="k",
        transport=_fake_transport(body),
    )
    assert res.sql == "SELECT 2 AS Y"
    assert res.valid is True


def test_ask_unknown_provider_raises():
    with pytest.raises(ai.AiError):
        ai.ask("q", "s", provider="bogus", model="m", api_key="k",
                transport=_fake_transport({}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_reporting_ai.py -o addopts="" -p no:cacheprovider -q`
Expected: FAIL — `ModuleNotFoundError: nx_lib.reporting.ai` (or `AttributeError: ask`).

- [ ] **Step 3: Implement `nx_lib/reporting/ai.py`**

```python
"""Provider-agnostic AI client for the Reporting assistant (Phase 1: NL -> T-SQL).

Pure and network-isolated for tests: the HTTP transport is injectable. The model
only *drafts* SQL; this module self-validates the draft through the existing
sqlglot gate (`sandbox.validate_select`) so the caller knows whether it is a
single read-only query before it ever reaches a database. Egress is schema-only:
the prompt carries the user's question + schema metadata, never result rows.
"""

import json
import re
from dataclasses import dataclass

import requests

from .sandbox import SqlSandboxError, validate_select

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TIMEOUT_S = 30

_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.+?)```", re.IGNORECASE | re.DOTALL)

_SYSTEM = (
    "You are a careful Microsoft SQL Server (T-SQL) analyst for an internal "
    "reporting tool. Given a database schema and a question, return ONE read-only "
    "SELECT query that answers it. Rules: SELECT/WITH only; never INSERT, UPDATE, "
    "DELETE, MERGE, EXEC, or DDL; use only tables/columns present in the schema; "
    "prefer TOP (n) to bound large results. Respond with STRICT JSON: "
    '{"sql": "<the query>", "explanation": "<one sentence>"}. No prose outside JSON.'
)


class AiError(RuntimeError):
    """Raised when the AI client is misconfigured or the provider call fails."""


@dataclass
class AiResult:
    sql: str
    explanation: str
    valid: bool
    gate_verdict: str          # "valid" | "invalid"
    model: str
    provider: str
    tokens_in: int | None
    tokens_out: int | None


def _http_post(url, headers, body, timeout):
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _user_prompt(question, schema_text):
    return (
        f"Database schema (names/types/descriptions only):\n{schema_text}\n\n"
        f"Question: {question}\n\n"
        'Return STRICT JSON {"sql": ..., "explanation": ...}.'
    )


def _call_anthropic(question, schema_text, *, model, api_key, url, max_tokens, timeout, transport):
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": _user_prompt(question, schema_text)}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    data = transport(url or DEFAULT_ANTHROPIC_URL, headers, body, timeout)
    parts = data.get("content") or []
    text = "".join(p.get("text", "") for p in parts if p.get("type", "text") == "text")
    usage = data.get("usage") or {}
    return text, usage.get("input_tokens"), usage.get("output_tokens")


def _call_azure(question, schema_text, *, model, api_key, endpoint, deployment,
                api_version, max_tokens, timeout, transport):
    if not endpoint or not deployment:
        raise AiError("Azure OpenAI requires endpoint and deployment")
    url = (
        f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        f"/chat/completions?api-version={api_version}"
    )
    body = {
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _user_prompt(question, schema_text)},
        ],
    }
    headers = {"api-key": api_key, "content-type": "application/json"}
    data = transport(url, headers, body, timeout)
    choices = data.get("choices") or [{}]
    text = (choices[0].get("message") or {}).get("content", "")
    usage = data.get("usage") or {}
    return text, usage.get("prompt_tokens"), usage.get("completion_tokens")


def _extract(text):
    """Pull (sql, explanation) from the model text: JSON first, then a fenced block."""
    text = (text or "").strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("sql"):
            return str(obj["sql"]).strip(), str(obj.get("explanation", "")).strip()
    except (ValueError, TypeError):
        pass
    m = _SQL_FENCE.search(text)
    if m:
        return m.group(1).strip(), ""
    return text, ""


def ask(question, schema_text, *, provider, model, api_key,
        endpoint=None, deployment=None, api_version="2024-10-21",
        url=None, max_tokens=DEFAULT_MAX_TOKENS, timeout=DEFAULT_TIMEOUT_S,
        transport=_http_post):
    """Draft one read-only SELECT for `question`. Returns an AiResult.

    Network is reached only through `transport` (injected in tests). The drafted
    SQL is validated through the sqlglot gate; an invalid draft is still returned
    (so the user can see/fix it) but flagged valid=False.
    """
    if not api_key:
        raise AiError("AI provider API key is not configured")
    provider = (provider or "").lower()
    if provider == "anthropic":
        text, tin, tout = _call_anthropic(
            question, schema_text, model=model, api_key=api_key, url=url,
            max_tokens=max_tokens, timeout=timeout, transport=transport,
        )
    elif provider == "azure":
        text, tin, tout = _call_azure(
            question, schema_text, model=model, api_key=api_key, endpoint=endpoint,
            deployment=deployment, api_version=api_version, max_tokens=max_tokens,
            timeout=timeout, transport=transport,
        )
    else:
        raise AiError(f"unknown AI provider: {provider!r}")

    sql, explanation = _extract(text)
    try:
        validate_select(sql)
        valid, verdict = True, "valid"
    except SqlSandboxError:
        valid, verdict = False, "invalid"
    return AiResult(
        sql=sql, explanation=explanation, valid=valid, gate_verdict=verdict,
        model=model, provider=provider, tokens_in=tin, tokens_out=tout,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_reporting_ai.py -o addopts="" -p no:cacheprovider -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai.py
git commit -m "feat(reporting): provider-agnostic AI client with self-validating NL->SQL"
```

---

## Task 3: Bounded, cached schema serializer (`nx_lib/reporting/ai_schema.py`)

Build the schema text the prompt grounds on, from the RO targets' `INFORMATION_SCHEMA.COLUMNS` plus curated catalogs — bounded by a char budget and a per-target object cap, **logging** when it truncates (no silent caps). Cursor factory injected for tests.

**Files:**
- Create: `nx_lib/reporting/ai_schema.py`
- Test: `tests/unit/test_reporting_ai_schema.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_reporting_ai_schema.py`:

```python
"""Unit tests for AI schema serialization (DB injected as a fake cursor)."""
from nx_lib.reporting import ai_schema


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def execute(self, sql, *params):
        self.executed = sql
        return self

    def fetchall(self):
        return self._rows


def _rows(*triples):
    # (TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE)
    return [type("R", (), dict(TABLE_SCHEMA=s, TABLE_NAME=t, COLUMN_NAME=c, DATA_TYPE=d))()
            for (s, t, c, d) in triples]


def test_serialize_target_groups_columns_by_table():
    cur = _FakeCursor(_rows(
        ("dbo", "Workitems", "Id", "int"),
        ("dbo", "Workitems", "Status", "nvarchar"),
        ("dbo", "Users", "UserId", "int"),
    ))
    text = ai_schema.serialize_target("statistics", lambda: cur)
    assert "dbo.Workitems" in text and "Id int" in text and "Status nvarchar" in text
    assert "dbo.Users" in text and "UserId int" in text


def test_serialize_schema_respects_char_budget_and_logs(monkeypatch, caplog):
    cur = _FakeCursor(_rows(*[("dbo", f"T{i}", "C", "int") for i in range(200)]))
    text, truncated = ai_schema.serialize_schema(
        targets={"statistics": (lambda: cur)},
        curated=[],
        char_budget=200,
    )
    assert len(text) <= 400  # budget + a small truncation marker
    assert truncated is True
    assert "truncated" in text.lower()


def test_serialize_schema_includes_curated_catalogs():
    curated = [{"label": "Generali — PDQM", "fields": [
        {"field": "Process", "type": "string"}, {"field": "Outcome", "type": "string"}]}]
    text, _ = ai_schema.serialize_schema(targets={}, curated=curated, char_budget=10000)
    assert "Generali" in text and "Process" in text and "Outcome" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_reporting_ai_schema.py -o addopts="" -p no:cacheprovider -q`
Expected: FAIL — `ModuleNotFoundError: nx_lib.reporting.ai_schema`.

- [ ] **Step 3: Implement `nx_lib/reporting/ai_schema.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_reporting_ai_schema.py -o addopts="" -p no:cacheprovider -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai_schema.py tests/unit/test_reporting_ai_schema.py
git commit -m "feat(reporting): bounded, logged schema serializer for the AI assistant"
```

---

## Task 4: Route `POST /api/reporting/ai/ask` + audit + config wiring

Wire the client + serializer behind a gated route. Reads `AI_*` from env (default `AI_PROVIDER=none` → **503**, mirroring an unconfigured RO source). Audits every interaction. **Never sends result rows.**

**Files:**
- Modify: `nx_lib/views/reporting.py` (imports near line 38–72; helpers near the other `_audit_*`/`_authorize_*` near lines 160–200; route after `api_sql_ack` ~line 564; registration in `register_routes` ~line 1336; template flag in `reporting()` ~line 437)
- Test: `tests/integration/test_reporting_ai_routes.py`

- [ ] **Step 1: Write the failing integration tests**

`tests/integration/test_reporting_ai_routes.py` (follow the existing `tests/integration/test_reporting_routes.py` fixtures — `user_client` is logged in; patch perms + `ai.ask` so no network/DB-RO is needed):

```python
"""Integration tests for POST /api/reporting/ai/ask (perm gating + happy path)."""
from unittest.mock import patch

from nx_lib.reporting.ai import AiResult


def _result(sql="SELECT TOP (5) Id FROM dbo.Foo", valid=True):
    return AiResult(sql=sql, explanation="five ids", valid=valid,
                    gate_verdict="valid" if valid else "invalid",
                    model="m", provider="anthropic", tokens_in=10, tokens_out=5)


def test_ai_ask_requires_use_permission(user_client):
    with patch("nx_lib.views.reporting.has_permission", return_value=False):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "hi"})
    assert resp.status_code == 403


def test_ai_ask_503_when_provider_unconfigured(user_client):
    with patch("nx_lib.views.reporting.has_permission", return_value=True), \
         patch("nx_lib.views.reporting._ai_config",
               return_value={"provider": "none", "api_key": None}):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "hi"})
    assert resp.status_code == 503


def test_ai_ask_happy_path_returns_sql_and_audits(user_client):
    with patch("nx_lib.views.reporting.has_permission", return_value=True), \
         patch("nx_lib.views.reporting._ai_config",
               return_value={"provider": "anthropic", "api_key": "k", "model": "m"}), \
         patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"), \
         patch("nx_lib.views.reporting.ai_ask", return_value=_result()) as ask, \
         patch("nx_lib.views.reporting._audit_ai") as audit:
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sql"].startswith("SELECT TOP (5)")
    assert data["valid"] is True
    assert "rows" not in data            # schema-only egress; never returns data
    ask.assert_called_once()
    audit.assert_called_once()


def test_ai_ask_rejects_empty_question(user_client):
    with patch("nx_lib.views.reporting.has_permission", return_value=True), \
         patch("nx_lib.views.reporting._ai_config",
               return_value={"provider": "anthropic", "api_key": "k", "model": "m"}):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "   "})
    assert resp.status_code == 400
```

> If `tests/integration/test_reporting_ai_routes.py` needs a `user_client` fixture, reuse the one in `tests/integration/test_reporting_routes.py` (move it to `tests/integration/conftest.py` if not already shared — check first; do not duplicate).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/integration/test_reporting_ai_routes.py -o addopts="" -p no:cacheprovider -q`
Expected: FAIL — route 404 (not registered) / `AttributeError` on the patched names.

- [ ] **Step 3: Add imports to `nx_lib/views/reporting.py`**

After the existing `from ..reporting.sandbox import ...` (line 51) add:
```python
from ..reporting.ai import AiError, AiResult  # noqa: F401  (AiResult used by tests)
from ..reporting.ai import ask as ai_ask
from ..reporting.ai_schema import serialize_schema
```
Add `import os` to the stdlib imports at the top (with `json`, `re`, `time`).

- [ ] **Step 4: Add the config + schema-text + audit helpers**

Place near the other helpers (after `_audit_sql`, ~line 200):

```python
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


def _accessible_sql_targets():
    """RO SQL targets the caller may use (gated like the SQL sandbox)."""
    out = {}
    for target, engine in _SQL_TARGET_ENGINES.items():
        perm = _SQL_TARGET_PERMISSION.get(target)
        if perm and not has_permission(perm):
            continue
        if engine is None:
            continue
        out[target] = (lambda e=engine: e.raw_connection().cursor())
    return out


def _ai_schema_text():
    """Build the schema grounding text from accessible RO targets + curated catalogs."""
    targets = _accessible_sql_targets()
    perms = set(session.get("permissions", []))
    curated = []
    for s in accessible(_effective_sources(), perms):
        if s.get("kind") == "curated" and s.get("provider") not in (None, "docprocessing"):
            curated.append({"label": s.get("label"),
                            "fields": table_source_catalog(s.get("columns"))})
    text, truncated = serialize_schema(targets=targets, curated=curated)
    if truncated:
        current_app.logger.info("reporting.ai schema truncated for user=%s", session.get("userid"))
    return text


def _audit_ai(userid, username, prompt, surface, generated_sql, provider, model,
              tokens_in, tokens_out, gate_verdict, status, duration_ms):
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ReportingAiAudit (UserID, Username, Prompt, Surface, "
                "GeneratedSql, Provider, Model, TokensIn, TokensOut, GateVerdict, "
                "Status, DurationMs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (userid, username, prompt, surface, generated_sql, provider, model,
                 tokens_in, tokens_out, gate_verdict, status, duration_ms),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"reporting ai audit insert failed: {e}")
    current_app.logger.info(
        f"reporting.ai.ask user={userid} provider={provider} verdict={gate_verdict} "
        f"status={status} ms={duration_ms}"
    )
```

- [ ] **Step 5: Add the route handler**

After `api_sql_ack` (~line 564):

```python
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
    if not has_permission("reporting.ai.sql"):
        return jsonify({"error": _("Not authorized to receive AI-drafted SQL")}), 403

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    schema_text = _ai_schema_text()
    start = time.monotonic()
    try:
        result = ai_ask(
            question, schema_text,
            provider=cfg["provider"], model=cfg.get("model"), api_key=cfg["api_key"],
            endpoint=cfg.get("endpoint"), deployment=cfg.get("deployment"),
            api_version=cfg.get("api_version", "2024-10-21"), url=cfg.get("url"),
        )
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/ask config error: {e}")
        return jsonify({"error": _("The AI assistant is not configured")}), 503
    except Exception as e:
        current_app.logger.error(f"/api/reporting/ai/ask provider error: {e}")
        _audit_ai(userid, username, question, "sql", None, cfg.get("provider"),
                  cfg.get("model"), None, None, "na", "error",
                  int((time.monotonic() - start) * 1000))
        return jsonify({"error": _("The AI assistant could not answer right now")}), 502

    duration_ms = int((time.monotonic() - start) * 1000)
    _audit_ai(userid, username, question, "sql", result.sql, result.provider,
              result.model, result.tokens_in, result.tokens_out,
              result.gate_verdict, "ok", duration_ms)
    return jsonify({
        "sql": result.sql,
        "explanation": result.explanation,
        "valid": result.valid,
        "target": "statistics",     # default editor target; user can switch
        "model": result.model,
    })
```

- [ ] **Step 6: Register the route and pass the template flag**

In `register_routes` after the `reporting_sql_ack` rule (~line 1336):
```python
    app.add_url_rule(
        "/api/reporting/ai/ask",
        endpoint="reporting_ai_ask",
        view_func=api_ai_ask,
        methods=["POST"],
    )
```
In `reporting()` (~line 437) add an `ai_enabled` flag to the `render_template` kwargs:
```python
        ai_enabled=has_permission("reporting.ai.use"),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/integration/test_reporting_ai_routes.py -o addopts="" -p no:cacheprovider -q`
Expected: PASS (4 tests).

- [ ] **Step 8: Run the full reporting unit+integration sweep (no regressions)**

Run: `python -m pytest tests/unit/test_reporting_*.py tests/integration/test_reporting_routes.py tests/integration/test_reporting_ai_routes.py -o addopts="" -p no:cacheprovider -q`
Expected: PASS (existing + new).

- [ ] **Step 9: Commit**

```bash
git add nx_lib/views/reporting.py tests/integration/test_reporting_ai_routes.py
git commit -m "feat(reporting): POST /api/reporting/ai/ask — gated, audited, schema-only NL->SQL"
```

---

## Task 5: Frontend — "Ask AI" mode button + panel + JS partial + CSS

Add a third mode button next to **Table / SQL** (gated by `ai_enabled`), a prompt panel whose only action is **Insert into SQL editor** (then the user runs via the existing gated path), plus **Copy**. The existing Motion layer animates it via a `.rp-anim` hook. No behavioural change to existing testids.

**Files:**
- Modify: `templates/reporting.html` (mode toggle ~line 43–46; panel after `#rpSqlPanel` ~line 83; include after `_reporting_anim_js.html` ~line 170)
- Create: `templates/js/_reporting_ai_js.html`
- Modify: `static/css/reporting.css`

Frontend is verified manually/e2e (Task 7 note), not unit-tested.

- [ ] **Step 1: Add the gated mode button**

In `templates/reporting.html`, inside `.reporting-mode-toggle` (after the SQL button, line 45):
```html
          {% if ai_enabled %}
          <button id="rpModeAi" data-testid="reporting-mode-ai">{{ _("Ask AI") }}</button>
          {% endif %}
```

- [ ] **Step 2: Add the Ask-AI panel**

After the `#rpSqlPanel` block (after line 83), add:
```html
      {% if ai_enabled %}
      <div id="rpAiPanel" class="reporting-ai-panel rp-anim-ai" hidden data-testid="reporting-ai-panel">
        <div class="reporting-ai-bar">
          <input id="rpAiPrompt" class="reporting-ai-prompt"
                 placeholder="{{ _('Ask in plain language — e.g. “top 10 processes by volume this month”') }}"
                 data-testid="reporting-ai-prompt">
          <button id="rpAiAsk" class="reporting-btn reporting-btn-primary"
                  data-testid="reporting-ai-ask">{{ _("Ask") }}</button>
        </div>
        <p class="reporting-ai-hint">{{ _("The assistant drafts read-only SQL from the database schema. It never sees result data. Review the SQL, then run it yourself.") }}</p>
        <div id="rpAiResult" class="reporting-ai-result" hidden data-testid="reporting-ai-result">
          <pre id="rpAiSql" class="reporting-ai-sql" data-testid="reporting-ai-sql"></pre>
          <p id="rpAiExplain" class="reporting-ai-explain"></p>
          <p id="rpAiInvalid" class="reporting-ai-invalid" hidden>{{ _("⚠ The drafted SQL did not pass the read-only check — review it before running.") }}</p>
          <div class="reporting-ai-actions">
            <button id="rpAiInsert" class="reporting-btn" data-testid="reporting-ai-insert">{{ _("Insert into SQL editor") }}</button>
            <button id="rpAiCopy" class="reporting-link" data-testid="reporting-ai-copy">{{ _("Copy") }}</button>
          </div>
        </div>
        <p id="rpAiError" class="reporting-ai-error" hidden data-testid="reporting-ai-error"></p>
      </div>
      {% endif %}
```

- [ ] **Step 3: Include the JS partial**

After `{% include 'js/_reporting_anim_js.html' %}` (line 170):
```html
  {% if ai_enabled %}
  {% include 'js/_reporting_ai_js.html' %}
  {% endif %}
```

- [ ] **Step 4: Create `templates/js/_reporting_ai_js.html`**

```html
<script>
(function () {
  "use strict";
  var modeAi = document.getElementById("rpModeAi");
  var panel = document.getElementById("rpAiPanel");
  if (!modeAi || !panel) return;

  var modeTable = document.getElementById("rpModeTable");
  var modeSql = document.getElementById("rpModeSql");
  var sqlPanel = document.getElementById("rpSqlPanel");
  var sqlEditor = document.getElementById("rpSqlEditor");
  var promptEl = document.getElementById("rpAiPrompt");
  var askBtn = document.getElementById("rpAiAsk");
  var resultEl = document.getElementById("rpAiResult");
  var sqlEl = document.getElementById("rpAiSql");
  var explainEl = document.getElementById("rpAiExplain");
  var invalidEl = document.getElementById("rpAiInvalid");
  var insertBtn = document.getElementById("rpAiInsert");
  var copyBtn = document.getElementById("rpAiCopy");
  var errorEl = document.getElementById("rpAiError");
  var lastSql = "";

  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }

  function showAiMode() {
    [modeTable, modeSql, modeAi].forEach(function (b) { if (b) b.classList.remove("active"); });
    modeAi.classList.add("active");
    if (sqlPanel) sqlPanel.hidden = true;
    panel.hidden = false;
  }
  modeAi.addEventListener("click", showAiMode);

  function ask() {
    var question = (promptEl.value || "").trim();
    if (!question) { promptEl.focus(); return; }
    askBtn.disabled = true;
    errorEl.hidden = true;
    fetch("/api/reporting/ai/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ question: question })
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
    }).then(function (res) {
      askBtn.disabled = false;
      if (!res.ok) {
        errorEl.textContent = (res.data && res.data.error) || "Error";
        errorEl.hidden = false;
        resultEl.hidden = true;
        return;
      }
      lastSql = res.data.sql || "";
      sqlEl.textContent = lastSql;
      explainEl.textContent = res.data.explanation || "";
      invalidEl.hidden = res.data.valid !== false;
      resultEl.hidden = false;
    }).catch(function () {
      askBtn.disabled = false;
      errorEl.textContent = "Network error";
      errorEl.hidden = false;
    });
  }
  askBtn.addEventListener("click", ask);
  promptEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); ask(); }
  });

  insertBtn.addEventListener("click", function () {
    if (!lastSql || !sqlEditor || !modeSql) return;
    sqlEditor.value = lastSql;
    modeSql.click();                 // switch to SQL mode via the existing handler
    sqlEditor.focus();
  });
  copyBtn.addEventListener("click", function () {
    if (navigator.clipboard && lastSql) navigator.clipboard.writeText(lastSql);
  });
})();
</script>
```

> Confirm the CSRF token meta tag name used by the existing `_reporting_js.html` fetches (search it for `csrf`); match it exactly. If the page uses a different header/name, mirror it here.

- [ ] **Step 5: Add panel CSS**

Append to `static/css/reporting.css`:
```css
/* --- AI assistant panel (Phase 1) --- */
.reporting-ai-panel { padding: .75rem; border: 1px solid var(--rp-border, #d0d7de); border-radius: 6px; margin-bottom: .5rem; }
.reporting-ai-bar { display: flex; gap: .5rem; }
.reporting-ai-prompt { flex: 1; padding: .4rem .6rem; }
.reporting-ai-hint { font-size: .8rem; color: #57606a; margin: .4rem 0 0; }
.reporting-ai-result { margin-top: .6rem; }
.reporting-ai-sql { background: #f6f8fa; padding: .6rem; border-radius: 6px; white-space: pre-wrap; overflow-x: auto; }
.reporting-ai-explain { font-size: .85rem; color: #24292f; }
.reporting-ai-invalid { color: #9a6700; font-size: .85rem; }
.reporting-ai-error { color: #cf222e; font-size: .85rem; }
.reporting-ai-actions { display: flex; gap: .5rem; align-items: center; margin-top: .4rem; }
/* Motion entrance hook: hidden only when animations are on (mirrors .rp-anim cols) */
.rp-anim .rp-anim-ai:not([hidden]) { opacity: 0; }
@media (prefers-reduced-motion: reduce) { .rp-anim .rp-anim-ai:not([hidden]) { opacity: 1; } }
```

- [ ] **Step 6: Restart the dev server and verify in a browser** (Jinja templates are cached for the process lifetime)

Run:
```powershell
& C:\dev\nexora\bin\nx.ps1 -d   # stop if running
& C:\dev\nexora\bin\nx.ps1 -u -b --loginas:ben.streich
```
Drive Playwright to `/reporting`: the **Ask AI** button shows (admin has `reporting.ai.use`); clicking it reveals the panel; with `AI_PROVIDER=none` the **Ask** action returns the "not configured" message (503) — that's the expected un-provisioned state. Save a screenshot to `var/screenshots/reporting_ai_panel.png`. (Live model responses require a provisioned key — see Task 7 verification.)

- [ ] **Step 7: Commit**

```bash
git add templates/reporting.html templates/js/_reporting_ai_js.html static/css/reporting.css
git commit -m "feat(reporting): Ask-AI panel — NL prompt -> SQL into the editor (frontend)"
```

---

## Task 6: Env templates + config documentation of the AI keys

**Files:**
- Modify: `env/INT.env.example`, `env/PROD.env.example`, `env/STAGING.env.example`, `env/TEST.env.example`

- [ ] **Step 1: Add the AI block to each `env/*.env.example`**

Append (sanitised — real keys live only in the un-committed `env/*.env`):
```ini
# --- Reporting AI assistant (Phase 1: NL -> SQL) ---
# AI_PROVIDER selects the model backend. Leave as "none" to disable the assistant
# (the /api/reporting/ai/ask route then returns 503, like an unconfigured RO source).
AI_PROVIDER=none
AI_MODEL=claude-sonnet-4-6
# Anthropic (AI_PROVIDER=anthropic):
ANTHROPIC_API_KEY=
# ANTHROPIC_API_URL=https://api.anthropic.com/v1/messages
# Azure OpenAI (AI_PROVIDER=azure):
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_KEY=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=2024-10-21
```

- [ ] **Step 2: Verify nothing reads a missing key at import**

Run: `python -c "import nx_lib.views.reporting"` (with `ENVIRONMENT=INT`)
Expected: no error (config reads happen per-request in `_ai_config`, not at import).

- [ ] **Step 3: Commit**

```bash
git add env/INT.env.example env/PROD.env.example env/STAGING.env.example env/TEST.env.example
git commit -m "docs(reporting): AI_* env keys in env example templates (AI Phase 1)"
```

---

## Task 7: Docs, CHANGELOG, CLAUDE.md, and translations

**Files:**
- Modify: `CHANGELOG.md`, `docs/howto/reporting.md`, `CLAUDE.md`
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

- [ ] **Step 1: CHANGELOG entry**

Under `## [Unreleased] → ### Added`:
```markdown
- **Reporting AI assistant (Phase 1):** an "Ask AI" mode that turns a natural-language
  question into read-only T-SQL placed in the SQL editor (no auto-run). Server-side,
  provider-agnostic (`AI_PROVIDER` = `anthropic` | `azure` | `none`); schema-only egress
  (the model never receives result rows); every interaction self-validated through the
  sqlglot gate and audited to `dbo.ReportingAiAudit`. New perms `reporting.ai.use` /
  `reporting.ai.sql`; route `POST /api/reporting/ai/ask`. Disabled until a provider key
  is configured.
```

- [ ] **Step 2: `docs/howto/reporting.md`** — add an "AI assistant (Phase 1)" subsection documenting the perms, route, the `AI_*` env vars, the schema-only egress guarantee, and that it's off until `AI_PROVIDER` is set. Link `docs/design/reporting-ai-assistant.md`.

- [ ] **Step 3: `CLAUDE.md`** — in the reporting `reporting.*` permission paragraph (Architectural conventions → Permissions), append the two new perms and the route, mirroring the existing prose:
```text
..., `reporting.ai.use` (use the AI assistant — NL questions) and `reporting.ai.sql`
(receive AI-drafted read-only T-SQL into the editor; grant alongside `reporting.sql.run`).
The assistant (`POST /api/reporting/ai/ask`, `nx_lib/reporting/ai.py` + `ai_schema.py`)
is server-side and provider-agnostic (`AI_PROVIDER`), sends only the question + schema
metadata (never result rows), self-validates every draft through the sqlglot gate, and
audits to `dbo.ReportingAiAudit`. See `docs/design/reporting-ai-assistant.md`.
```
Also add the `engine` note is unchanged; mention the `AI_*` env vars near the other reporting env vars.

- [ ] **Step 4: Extract + update + fill translations**

Run:
```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```
Edit `translations/{de,fr,it}/LC_MESSAGES/messages.po` — translate every new msgid (Ask AI, Ask, the prompt placeholder, the hint, "Insert into SQL editor", Copy, the invalid warning, and the route's flash/error strings: "A question is required", "Not authorized to receive AI-drafted SQL", "The AI assistant is not configured", "The AI assistant could not answer right now"). Mark non-fuzzy. Then:
```bash
pybabel compile -d translations
```

- [ ] **Step 5: Run the translation gate**

Run: `python -m pytest tests/test_translations.py -o addopts="" -p no:cacheprovider -q`
Expected: PASS (pot in sync; every msgid translated non-fuzzy in de/fr/it).

- [ ] **Step 6: Live verification with a provisioned key (optional, owner-gated)**

If a provider key is available in `env/INT.env`, set `AI_PROVIDER=anthropic` (or `azure` + the `AZURE_OPENAI_*`), restart (`nx -u -b --loginas:ben.streich`), open `/reporting → Ask AI`, ask *"top 10 processes by workitem count this month"*; confirm valid T-SQL appears, **Insert into SQL editor** populates `#rpSqlEditor` and switches to SQL mode, the gated run works, and a `dbo.ReportingAiAudit` row was written. Screenshot to `var/screenshots/reporting_ai_live.png`.

- [ ] **Step 7: Commit**

```bash
git add CHANGELOG.md docs/howto/reporting.md CLAUDE.md messages.pot translations/
git commit -m "docs(reporting): document AI assistant Phase 1 + de/fr/it translations"
```

---

## Final verification (before handoff/merge)

- [ ] Full reporting suite green:
  `python scripts/test_db_reset.py && python -m pytest tests/unit/test_reporting_*.py tests/integration/test_reporting_*.py -o addopts="" -p no:cacheprovider -q`
- [ ] Translation gate green: `python -m pytest tests/test_translations.py -o addopts="" -p no:cacheprovider -q`
- [ ] Lint: `python -m ruff check nx_lib/reporting/ai.py nx_lib/reporting/ai_schema.py nx_lib/views/reporting.py`
- [ ] Migrations applied to INT (Task 1) and per-object DDL re-dumped by the pre-commit hook.
- [ ] **Egress check (manual read):** confirm `api_ai_ask` and `ai.ask` never include result rows in the provider request — only the question + `_ai_schema_text()`.
- [ ] (Remote/commit-only this session — do **not** push or PR; the owner pushes after review.)

---

## Self-review (run against the spec — `docs/design/reporting-ai-assistant.md` §12 Phase 1)

**Spec coverage**
- NL → SQL into the editor only, no auto-run → Task 5 (Insert-into-editor is the only path; no run button in the panel). ✅
- 1-line explanation → `explanation` field, rendered in `#rpAiExplain`. ✅
- Server-side provider call (no CSP change) → Task 2 (`requests` server-side), Task 4 route. ✅
- Schema from RO `INFORMATION_SCHEMA` + catalogs, **all registered sources** → Task 3 + `_ai_schema_text()` (all accessible SQL targets + curated catalogs). ✅
- `reporting.ai.use` / `reporting.ai.sql` → Task 1 (seed) + Task 4 (enforce). ✅
- `ReportingAiAudit` → Task 1 (DDL) + Task 4 (`_audit_ai`). ✅
- Reuses gate/ack/run/audit; no new execution path → run still goes through the unchanged `/api/reporting/sql/run`; the panel never executes. ✅
- Acceptance (valid T-SQL via `validate_select`, gated run, audited, schema-only egress) → Tasks 2/4 + Final verification egress check. ✅

**Placeholder scan** — no "TBD/handle errors/similar to" left; all steps carry real code/commands. Two explicit *confirm-against-codebase* notes (shared `user_client` fixture; CSRF meta-tag name) are verification steps, not placeholders.

**Type/name consistency** — `AiResult` fields (`sql, explanation, valid, gate_verdict, model, provider, tokens_in, tokens_out`) are used consistently in Task 2 (definition), Task 4 (route + `_audit_ai` args), and Task 4 tests. Route name `reporting_ai_ask` / view `api_ai_ask` / import alias `ai_ask` are consistent. Env keys (`AI_PROVIDER`, `AI_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_API_URL`, `AZURE_OPENAI_ENDPOINT/KEY/DEPLOYMENT/API_VERSION`) match across Tasks 4/6/7.

**Open confirmations for the implementer (cheap, do at the step):**
1. The shared `user_client` fixture location (Task 4 note).
2. The exact CSRF token mechanism the existing reporting fetches use (Task 5 note) — match it.
3. That `dbo.Permission` / `dbo.AccessProfilePermission` / `admin.view` are the correct seed targets (confirmed against `0007`/`0008`).
