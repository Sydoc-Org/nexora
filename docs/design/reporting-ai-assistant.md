# Design — AI assistant in the Reporting page

> **Status:** Phase 1 and Phase 2 implemented (see §12 for phase status).
> **Author:** initial draft via Claude Code, 2026-06-03.
> **Scope:** an in-page AI that turns natural language into *helpful, smart*
> statistics — building reports for you, and writing SQL you can run or
> copy-paste — without weakening the reporting module's existing safety model.
> **Audience:** Sydoc internal dev team.

This is a **design doc**, not an implementation plan. It lays out the surfaces,
architecture tiers, provider tradeoffs, governance, and the semantic/metrics
layer so we can agree on *scope* before anything is built.

---

## 1. Goal & guiding principle

Users want to ask, in plain language —

- *"average handling time per process for Generali last quarter"*
- *"top 10 users by workitem volume this month, with a month-over-month delta"*
- *"give me the SQL for PDQM rejections grouped by subcategory"*

— and get back either a **ready-to-run report** (grid/chart/pivot), **runnable
or copy-pasteable SQL**, or a **plain-language answer with numbers**.

**Guiding principle: the LLM proposes; our existing rails dispose.**
We already built the hard, security-critical part of "let people query the
warehouse safely":

| Existing asset | File / object | Role for AI |
|---|---|---|
| sqlglot AST gate (`validate_select`, `wrap_with_cap`) | `nx_lib/reporting/sandbox.py` | **Authority** over any SQL the model emits |
| Read-only `db_datareader` logins | `engine_statistics_ro`, `engine_octo_ro` (`nx_lib/db.py`) | Execution can never mutate data |
| Per-run audit | `dbo.ReportingSqlAudit` | Every AI query is logged |
| First-use acknowledgment | `dbo.ReportingSqlAck` | Consent UX reused |
| Whitelist report-definition validator | `/api/reporting/run`, `nx_lib/reporting/table_query.py` | A **SQL-free** safe surface |
| Source registry + field catalogs | `dbo.ReportingSources`, `merge_sources` | Schema grounding for the model |
| Permission family | `reporting.*` | Gate the AI like everything else |

The AI is therefore a **query-drafting UI**, never a trusted database client.
Nothing the model returns is executed without passing the *same* gate a human's
SQL passes today. This single decision removes most of the risk surface.

---

## 2. The two safe output surfaces

Every AI feature reduces to producing one of two artifacts. Both already have a
trusted validator in the codebase.

### Surface A — NL → **report definition** (SQL-free, safest) ✅ implemented (2026-06-03)

The model emits the **v1 report-definition JSON** (`source`, `columns`,
`filters`, `sort`, `groupBy`, `scope`, `rowLimit`). It then flows through the
*unchanged* `/api/reporting/run` path:

- The server validates every column / filter field / sort field / scope entry
  against the source's field catalog — **off-catalog ⇒ rejected**.
- `reporting.scope.process.*` row-scoping still applies (no data leak).
- No raw SQL is produced; no `reporting.sql.run` needed.
- **Field grounding:** the catalog text shows each field as `key "Human Label":type`
  (label omitted when it equals the key). The model is told to put the **exact key**
  in every `field` (the validator checks keys), using the quoted label only to pick
  the right field and as a column `header`. This stops docprocessing — whose keys are
  internal Statconfig codes, not the human labels the model would otherwise guess —
  from drafting label-named fields the validator rejects.

**Best for:** non-technical users, scoped sources (Generali / Octopus curated),
"just build me the report." **Limit:** only what the builder can express.

### Surface B — NL → **T-SQL** (powerful, for complex stats)

The model emits T-SQL that flows through the *unchanged* `/api/reporting/sql/run`
path: `validate_select` (sqlglot gate) → `wrap_with_cap` → RO engine → statement
timeout → `ReportingSqlAudit`. The UI **always shows the SQL first**:

- **Copy** (copy-paste), **Insert into SQL editor** (review then run via the
  existing ack/gate/run), or **Run** (gated).

**Best for:** window functions, percentiles, cohort/retention, time-bucketing,
anything beyond the builder. **Gate:** behind `reporting.sql.run`, which is
already documented as having no row-scoping — so AI-SQL inherits that property
and must be granted as deliberately as SQL access is today.

> **Design rule:** prefer Surface A whenever the question fits the builder;
> fall back to Surface B for genuine analytics. A small classifier (or the
> agent itself) decides which surface to use per question.

---

## 3. Architecture tiers

Four tiers of increasing capability and cost. They compose — a later tier
includes the earlier ones.

### Tier 1 — Single-shot text-to-SQL/definition
Schema + question in the prompt → one draft → our gate → show/run.
- **Pros:** trivial to build, cheap, ~1 API call.
- **Cons:** brittle on ambiguous questions and domain jargon; no recovery from
  its own mistakes.
- **Use as:** the literal MVP.

### Tier 2 — **Agentic tool-loop (recommended core)**
The model is given tools and iterates until it has a validated answer:

```
tools = [
  list_sources(),                       # ReportingSources catalogs
  get_schema(source|target),            # columns, types, descriptions, FKs
  sample_values(column, k)              # distinct sample (PII-filtered) — optional
  validate_sql(sql) -> {ok, error}      # sqlglot gate + (optional) SET SHOWPLAN/parse
  run_sql(sql) -> rows                  # RO engine, capped, audited
  build_definition(json) -> {ok,error}  # whitelist validator (Surface A)
  compute_stats(rows, spec) -> result   # deterministic pandas/scipy (see §10)
]
```

Loop: inspect schema → draft → **`validate_sql` (dry-run)** → on error, feed the
error back and **self-repair** (max N retries) → run → return result + a
plain-language explanation of what it did.

- **Pros:** this is what makes it feel *reliable* rather than a party trick; the
  self-repair loop catches most hallucinated columns/joins before the user sees
  anything; multi-step questions work.
- **Cons:** more API round-trips (cost/latency); needs careful tool design and a
  hard iteration cap.
- **Use as:** the real product spine.

### Tier 3 — + RAG / domain grounding
Retrieve, per question, the most relevant: field-catalog entries, **column
descriptions**, a **business glossary** ("workitem", "PDQM", SLA, "process"),
and **previously-saved reports** as worked examples. Inject only what's relevant
instead of dumping the whole schema.
- **Pros:** big accuracy jump on *your* terminology; keeps prompts small.
- **Cons:** needs an embedding store and curation of the glossary.
- **Embedding store options:** (a) SQL Server 2025 native `VECTOR` type if/when
  available on the warehouse; (b) a plain `dbo.ReportingAiEmbeddings` table with
  cosine in Python; (c) an external vector store (heavier — probably unwarranted).

### Tier 4 — + Semantic / metrics layer (BI-grade)
Define canonical **metrics** and **dimensions** once (db- or YAML-backed):
`metric: avg_handling_time = AVG(...)`, `dimension: process`, allowed grains,
joins. NL → *semantic query* → safe SQL generated from the semantic model.
- **Pros:** eliminates hallucinated joins/aggregations; consistent numbers
  across questions; the "single source of truth" that makes execs trust BI AI.
- **Cons:** real upfront modelling work; needs ownership.
- **Use as:** the destination if this becomes a primary analytics surface.

**Recommendation:** ship Tier 1 as MVP, build toward **Tier 2** as the core,
add **Tier 3** for accuracy, and treat **Tier 4** as a strategic follow-on only
if adoption justifies the modelling investment.

---

## 4. Provider options & data egress

The API key lives **server-side** — the browser never calls the model, the
Flask server does (server→provider). Consequences: **no CSP/`connect-src`
change**, the key stays out of the client, and we control exactly what is sent.

| Provider | Strengths | Watch-outs | Fit |
|---|---|---|---|
| **Claude API (Sonnet 4.x / Opus)** | Excellent at SQL & tool-use; we're already an Anthropic shop | Data leaves the tenant → needs zero-retention/enterprise terms | Great for quality |
| **Azure OpenAI** | Stays inside the Azure tenant; aligns with our MS Graph/Azure footprint; enterprise data-handling | Slightly more setup; model parity varies | **Likely the compliance default** for an internal portal |
| **Local (Ollama + SQL-tuned model)** | No data egress at all | Lower SQL quality; infra to run/maintain | Only if data truly can't leave the building |

### What actually leaves the building (egress classification)
Be explicit about this — it's the crux of approval.

| Data class | Sent to model? | Default |
|---|---|---|
| The user's natural-language question | Yes | Always |
| Schema **metadata** (table/column names, types, descriptions, glossary) | Yes | Always (PII columns flagged/omitted) |
| **Sample values** for disambiguation | Optional | **Off by default**; PII-filtered if on |
| **Result rows** ("explain these numbers", chart suggestion) | Optional | **Off by default**; gated by `reporting.ai.explain_data` |

Default posture: **schema-only, no data egress.** Sending rows back to the model
is a separate, explicitly-granted capability.

---

## 5. Components in nexora terms

```
nx_lib/reporting/ai.py            NEW — provider client, prompt assembly,
                                  schema serializer (from ReportingSources +
                                  INFORMATION_SCHEMA of RO targets), tool
                                  dispatch + self-repair loop
nx_lib/reporting/ai_tools.py      NEW — the tool implementations (wrap existing
                                  validate_select / run / table_query)
nx_lib/reporting/semantic.py      NEW (Tier 4) — metric/dimension model → SQL
nx_lib/views/reporting.py         + POST /api/reporting/ai/ask  (NL → {definition|sql|answer})
                                  + POST /api/reporting/ai/explain (gated, sends rows)
                                  (execution REUSES /api/reporting/sql/run + /run)
templates/js/_reporting_ai_js.html  NEW — the "Ask AI" panel (vanilla JS, matches
                                  the existing inline-partial pattern)
sql/_migrations/NexoraDB/00NN_*   dbo.ReportingAiAudit; reporting.ai.* perms;
                                  (Tier 3/4) embeddings + semantic-model tables
env/*.env(.example)               AI_PROVIDER, ANTHROPIC_API_KEY |
                                  AZURE_OPENAI_ENDPOINT/KEY/DEPLOYMENT,
                                  AI model id, max-tokens/turn caps
```

Nothing in the **runtime execution** path is new: `validate_select`,
`wrap_with_cap`, the RO engines, `ReportingSqlAudit`, and the whitelist
definition validator are all reused as-is. The AI module only *produces
candidates* and *orchestrates* calls to them.

---

## 6. Permissions & audit

New grantable permissions (admins seeded), consistent with the `reporting.*`
family:

| Perm | Allows |
|---|---|
| `reporting.ai.use` | Ask the assistant; receive **Surface A** definitions + explanations (no SQL) |
| `reporting.ai.sql` | Receive/run **Surface B** SQL — **implies** `reporting.sql.run` |
| `reporting.ai.explain_data` | Allow result **rows** to be sent to the model (data egress) |

New audit table `dbo.ReportingAiAudit` (or an `origin` + `prompt` column added to
`ReportingSqlAudit`): `{user, prompt, surface, generated_sql_or_definition,
model, tokens_in/out, gate_verdict, rows_returned, ms, created_at}`. Every AI
interaction that touches data is auditable end to end.

`Status` vocabulary (the column is open `NVARCHAR(16)`, no CHECK constraint):
`ok` (provider answered), `error` (provider call raised), `blocked` (throttled by
`AI_DAILY_LIMIT` before any provider call), `misconfig` (provider misconfigured —
the route 503s). Only `ok`/`error` count toward the daily cap, so `blocked` and
`misconfig` never compound or burn a user's quota.

---

## 7. Security model & failure handling

- **Execution safety:** unchanged — RO logins + sqlglot gate + statement timeout
  + `TOP(cap)` wrap. The model cannot do anything a human with `reporting.sql.run`
  can't already do.
- **Row-scoping caveat:** Surface B (SQL) bypasses `reporting.scope.process.*`,
  exactly like the existing SQL sandbox. So `reporting.ai.sql` must be granted as
  deliberately as SQL access. Surface A keeps scoping. Document this prominently.
- **Prompt injection:** free-text DB values (e.g. a comment column) returned to
  the model could contain "ignore your instructions" payloads. Harmless for
  execution (RO + gate), but treat model output as **proposals only** — never let
  model text trigger side effects beyond a gated run. Keep `explain_data` opt-in.
- **PII minimisation:** mark PII columns in the catalog; omit them from schema
  sent to the model and from any sampling, unless explicitly needed and granted.
- **Cost / abuse controls:** per-user token budget and a hard agent-iteration
  cap; `flask_limiter` on `/api/reporting/ai/*`; cache the serialized schema; use
  a smaller/cheaper model for surface-classification and a stronger one for hard
  SQL.
- **Determinism for stats:** heavy analytics run in the **`compute_stats`** tool
  (pandas/scipy) over the RO result, not "in the LLM's head" — reproducible and
  cheap. Good for distributions, correlations, percentiles, simple forecasts.

---

## 8. Accuracy strategy

1. **Ground in the catalogs you already maintain** (`ReportingSources` fields +
   descriptions) — not the raw DB. High accuracy without exposing everything.
2. **Few-shot** with ~5–10 canonical Q→SQL / Q→definition pairs for the Sydoc
   domain (PDQM, workitems, processes).
3. **Dry-run before show:** always `validate_sql` (sqlglot) and optionally a
   parse/`SET SHOWPLAN_XML ON` no-exec plan; self-repair on failure.
4. **Sanity feedback:** 0 rows → suggest loosening filters; huge result → suggest
   an aggregation; type mismatch → explain and offer a fix.
5. **Show the work:** the SQL/definition is always visible and editable — the
   user stays in control and learns the schema.

---

## 9. UX integration

- A third toggle next to **Table / SQL**: **Ask AI** (gated by `reporting.ai.use`).
- A prompt box + conversational follow-ups ("now break it down by month", "only
  Generali", "as a chart"). Streamed responses; visible tool steps for trust.
- Result actions, one click each: **Run**, **Copy SQL**, **Insert into SQL
  editor**, **Open in builder** (fills the wells from a Surface-A definition),
  **Make a chart** (reuse Chart.js), **Save as report**, **Schedule** (reuse the
  existing dialog).
- Transparency first: SQL/definition shown *before* anything runs; "Explain this
  query" / "Why these rows?" affordances.
- i18n: all new strings via `{{ _('…') }}` / `gettext`, de/fr/it (the
  `test_translations.py` gate already enforces coverage).

---

## 10. Deterministic statistics tool (`compute_stats`)

LLMs are weak/inconsistent at arithmetic over many rows. So "complex statistics"
should be computed deterministically:

- The model decides *what* stat to compute and on *which* columns; the
  **`compute_stats`** tool runs it with pandas/scipy/statsmodels over the RO
  result set (already row-capped).
- Covers: descriptive stats, group-bys, percentiles/quantiles, correlations,
  distributions, simple time-series (rolling, seasonality), naive forecasts.
- Output is exact and reproducible; the model only *narrates* it. Keeps tokens
  low and numbers trustworthy.

---

## 11. Build vs buy

- **Build** (recommended): we own the rails; the AI layer is "candidate
  generation + orchestration," which is modest. Maximum control over egress and
  audit.
- **Borrow** for Tier 3: **Vanna.ai** (open-source, RAG text-to-SQL, BYO-LLM) can
  accelerate the retrieval/grounding piece — still wrapped in our gate.
- **Avoid:** Power BI / Fabric Copilot. We're *replacing* Power BI; re-coupling
  to it for the AI would undo that.

---

## 12. Phased roadmap

| Phase | Deliverable | Reuses | Rough effort | Status |
|---|---|---|---|---|
| **1 — MVP** | "Ask AI" → SQL **into the editor only** (no auto-run) + 1-line explanation; server-side provider call; schema from RO `INFORMATION_SCHEMA` + catalogs; `reporting.ai.use/sql`; `ReportingAiAudit` | gate, ack, run, audit | ~days | ✅ done (2026-06-03) |
| **2 — Builder + charts** | NL → report-definition (auto-fills wells; whitelist-safe; no SQL perm) + "suggest a chart" | `/run`, Chart.js | ~days | ✅ done (2026-06-03) |
| **3 — Agentic + stats + RAG** | Tier-2 tool-loop with self-repair, `compute_stats`, "explain results" (gated), follow-up conversation, glossary RAG | embeddings table | ~1–2 wks | planned |
| **4 — Semantic layer** | Canonical metrics/dimensions → trustworthy, consistent numbers | semantic.py | strategic, larger | planned |

**Phase-1 acceptance:** a user with `reporting.ai.sql` types a question, gets
valid T-SQL in the editor that passes `validate_select`, can run it via the
existing gated path, and the interaction is in `ReportingAiAudit`. No new
execution path; no data egress beyond the question + schema metadata.

**Phase-2 acceptance:** a user with `reporting.ai.use` (no SQL perm needed)
types a question, the server returns a validated v1 report definition, **Open in
builder** fills the wells, the user runs it via the existing `/api/reporting/run`
path (row-scoping and whitelist intact), and the interaction is in
`ReportingAiAudit` with `Surface='definition'`. An optional `chartHint` enables
**Make a chart** in one click. No new permission, table, or migration.

---

## 13. Open questions (decide before planning)

1. **Provider:** Azure OpenAI (tenant-resident, compliance default) vs Claude API
   (quality, zero-retention terms)? This gates the env/secrets shape.
2. **Data egress:** is sending **result rows** to the model ever acceptable
   (for "explain these numbers")? If no, drop `reporting.ai.explain_data` and
   keep everything schema-only.
3. **Audience:** primarily SQL-capable users (lead with Surface B) or
   everyone (lead with Surface A / builder auto-fill)?
4. **Scope of sources:** all registered sources/targets, or start with one
   (e.g. Statistics) to bound the schema and prove accuracy?
5. **Glossary ownership:** who curates the business definitions that make Tier 3
   accurate?

---

## 14. Risks

- **Trust erosion from wrong numbers** → mitigated by always showing SQL,
  dry-run validation, deterministic `compute_stats`, and (Tier 4) a semantic
  layer.
- **Data governance** → server-side key, egress classification, schema-only
  default, PII omission, full audit.
- **Cost creep** → token budgets, model tiering, schema caching, iteration caps.
- **Latency** of the agentic loop → cap turns, stream, cache schema, classify to
  the cheapest viable surface.

---

## See also

- `docs/howto/reporting.md` — the reporting page, sources, SQL sandbox, perms.
- `nx_lib/reporting/sandbox.py` — the sqlglot gate the AI must route through.
- `nx_lib/reporting/table_query.py` — whitelist-safe `table` provider (Surface A).
- CLAUDE.md → "reporting.*" — the permission family this extends.
