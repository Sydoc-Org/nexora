# Design — AI assistant in the Reporting page

> **Status:** Phase 1, Phase 2 and Phase 3 implemented — the agentic loop +
> deterministic stats engine + drafter route (3a–3d), and **Phase 3e** data
> egress (the `reporting.ai.explain.use` permission binds `run_sql` +
> `compute_stats` into the loop so the model narrates real numbers; off by
> default → schema-only). Glossary RAG (the other 3e item) remains planned
> (needs a curation owner). **2026-07-27 (Phase 5, "chat glow-up"):** the
> old three-sub-mode "Ask AI" tab (Build a report / Write SQL / Agent) and the
> Simple tab's own one-shot ask + Refine bar are **retired** — a single
> multi-turn **AI chat panel** (§2b) now fronts Surface C's agent endpoint on
> both tabs, threading up to 8 turns / 4000 chars of conversation history.
> The same release also shipped `reporting.ai.explain.use`-gated **auto
> captions** (a 1–2 sentence narration under any result, `Surface='caption'`
> in the audit table) as the actually-shipped Phase-3e narration surface for
> a *single already-fetched result* (distinct from the agent's live `run_sql`
> narration, which additionally needs `reporting.sql.run`), and a
> non-AI **comparison** feature (`compare` flag on `/api/reporting/run`,
> Simple-tab delta chips) — see `docs/howto/reporting.md` for both. See §12
> for phase status.
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
- **Coverage grounding (#128):** the RO-target block is a flat `INFORMATION_SCHEMA`
  dump, in which a per-process statistics table (`dbo.Compass_Invoice`) is
  indistinguishable from a company-wide fact table — so the agent answered "our
  volume" from whichever single table it found, worst case reporting a confident
  zero as if it were company-wide. `serialize_partial_tables` now prepends the
  `Statconfig` table→process map, marked as **partial** views and naming the
  curated source that unions them; `_AGENT_SYSTEM` makes the consequences binding
  (totals questions with no process named are company-wide ⇒ `build_definition`
  or an explicit UNION; every SQL answer states its coverage; zero from one
  partial table is zero *for that process*). Two details the eval proved
  necessary: the block declares itself **complete**, because the statistics DB
  also holds tables Statconfig never registered (`dbo.BFH_Statistic`,
  `dbo.DPSLicenseCounter` — both of which the agent had been answering from) that
  are outside the reporting universe entirely; and each line carries that table's
  import/export date columns, since they differ per table (`ExportDate` vs
  `ExportEM_dt`) and a UNION written without them fails on "invalid column name"
  instead. Statconfig being unavailable drops the block rather than failing the
  request.
- **Per-process field-column grounding (#154):** the date columns alone weren't
  enough — the agent still guessed the rest (page count, document type, user,
  barcode, …) when it UNIONed the partial tables in raw SQL, hitting `Invalid
  column name` in ~4 of 22 eval cases and often failing to recover. Each
  `serialize_partial_tables` line now also lists that table's SearchConfig
  `col_*` field columns — the same per-process `{field_key: column}` map
  `_load_field_col_maps` already builds for the `docprocessing` curated
  source — so raw SQL against these tables uses real column names instead of
  probing `INFORMATION_SCHEMA` or guessing.
- **Workitem-count semantics (#132):** the same block states that one row in a
  partial table **is** one workitem — `COUNT(*)`, `COUNT(WorkitemID)` and
  `COUNT(DISTINCT WorkitemID)` were verified equal on PROD, which is why the
  `workitem_count` metric is disabled (migration `0021`) and `doc_count`
  already answers "how many workitems". It also states that workitem ids are
  unique only *within* a process and collide across tables, so a cross-table
  `COUNT(DISTINCT WorkitemID)` under-counts. Without both facts the agent
  drafted exactly that query and reported its result as a company total.
- **Ambiguity disclosure (#132):** the agent may not ask the user questions
  (Surface C is single-shot), so when a question underdetermines the metric,
  the period type (calendar vs rolling) or the scope, `_AGENT_SYSTEM` requires
  it to open the answer with one sentence naming the reading it used and the
  main alternative — instead of silently picking one and presenting it as
  *the* numbers.
- **Mandatory caveats (#132):** a four-item checklist in `_AGENT_SYSTEM`
  (partial current period, small-n baselines, excluded/assumed rows, thin
  evidence for a trend or seasonality claim), to be stated in one sentence
  when any apply. Six eval cases produced technically-correct numbers that
  were misleading without exactly these.
- **No handing the question back (#132):** the agent must not present SQL it
  never executed as though it produced numbers, and must not stop with turns
  remaining to give the user instructions to run the query themselves — it
  retries from a different angle instead.
- **Date grounding:** today's date is injected into the user prompt and the agent
  grounding so relative time expressions ("last month", "this year") resolve to
  correct absolute date ranges, not training-data dates. The agent system prompt
  also instructs the model to use this date and not its training knowledge.
- **Relative-date token emission:** Surface A (`ask_definition` / `_SYSTEM_DEF`)
  and Surface C (`_AGENT_SYSTEM`) both teach the model to emit a token value
  (`{"token": "last_month"}`, `{"token": "last_n_days", "n": 30}`, etc.) rather
  than hard-coded date pairs when the question uses relative phrasing. Token
  values are schema, not user data, so they pass through egress unchanged.
  Resolution to a concrete date range happens server-side at run time.
- **Distinct/unique values:** the system prompts teach both surfaces that answering
  "different X" / "unique X" questions requires `columns: [X]` plus a count metric
  (which makes X a GROUP BY dimension), not bare columns (which would return
  duplicate rows, one per source document).
- **Humanized process labels:** each process id in `allowed scope.processes` is
  rendered with a derived human label in parentheses
  (e.g. `privera.03_Invoice_New ("privera Invoice New")`). The prompts instruct
  the model to match natural-language process names case-insensitively against both
  the id and the label, and to include all matches rather than guessing one.
  The egress guarantee is unchanged — the date is not user data; the process labels
  are derived from the process id alone (no DB lookup).
- **Tolerant repair (server-side safety net):** prompting alone is not enough for
  small models on curated **table** sources (CamelCase keys like `ForDate` vs. the
  label "Date"). Before validation, `schema.coerce_definition` repairs the draft
  **in place**: it resolves a `field` given as a human **label** back to its catalog
  **key** (columns, filters, sort, chart axes), backfills the column `header` with
  that label, and fills the obvious scalars (`schemaVersion`, `visualization`,
  a synthesized `title`, a default/clamped `rowLimit`). It is **whitelist-safe** — a
  label is only swapped when it maps to exactly one catalog field; an unknown value
  is left to be rejected — and a no-op for an already-valid draft. The same gate
  (`_validate_definition_for_user`) backs both Surface A and the agent's
  `build_definition` tool, so both benefit; the human builder path (`/run`) is
  untouched.
- **Distinct-count shadow-column guard:** when the validated definition contains a
  `count_distinct` metric and the `columns` list includes the metric's own base
  field (which would make the GROUP BY swallow the distinct count, returning
  trivially-1 aggregates), the validator **silently drops the shadowing column**
  from `columns` before the run. This is a mutating repair in the same spirit as
  `coerce_definition` — same contract, same whitelist-safety — applied only when
  the dropped column is definitively the `count_distinct` base field and the
  remaining columns still make a useful report. Applied to both Surface A and
  the agent's `build_definition` tool.
- **Gate error surfaced verbatim:** when `POST /api/reporting/ai/build` produces a
  definition that survives `coerce_definition` + the shadow-column guard but still
  fails `_validate_definition_for_user`, the JSON error response now carries the
  validator's message text directly so the Simple tab can display it to the user
  (rather than showing the model's explanation, which may contradict the actual
  failure reason).

**Best for:** non-technical users, scoped sources (Generali / Octopus curated),
"just build me the report." **Limit:** only what the builder can express.

#### AI refine (Surface A) — superseded by chat history (see §2b)

`POST /api/reporting/ai/build` can still receive `priorQuestion` and
`priorDefinition` in the request body (injected into the user-turn prompt so the
model can apply targeted changes rather than rebuilding from scratch; still fully
validated, `priorDefinition` is prompt context only, never executed directly) —
but as of the chat-panel glow-up (2026-07-27) no UI calls this endpoint or sends
that context any more. The Simple tab's one-shot ask + its dedicated **Refine**
bar are removed; conversational follow-ups on **any** surface now go through
Surface C's chat panel and its `history` param instead (§2b). This paragraph
documents `priorQuestion`/`priorDefinition` as a still-live but orphaned
capability of the `/ai/build` route, not a current user-facing flow.

### Surface B — NL → **T-SQL** (powerful, for complex stats)

The model emits T-SQL that flows through the *unchanged* `/api/reporting/sql/run`
path: `validate_select` (sqlglot gate) → `wrap_with_cap` → RO engine → statement
timeout → `ReportingSqlAudit`. The design called for the UI to **always show the
SQL first** with **Copy** / **Insert into SQL editor** / **Run** actions — that
was true of the original standalone "Write SQL" sub-mode, which (like Surface A's
own sub-mode) is retired as of the chat-panel glow-up; see §2b. `POST
/api/reporting/ai/ask` is unchanged and still callable, just not called by any
current template/JS.

**Best for:** window functions, percentiles, cohort/retention, time-bucketing,
anything beyond the builder. **Gate:** behind `reporting.sql.run`, which is
already documented as having no row-scoping — so AI-SQL inherits that property
and must be granted as deliberately as SQL access is today.

> **Design rule:** prefer Surface A whenever the question fits the builder;
> fall back to Surface B for genuine analytics. A small classifier (or the
> agent itself) decides which surface to use per question.

### Surface C — Agentic tool-loop (the shipped chat panel) ✅ implemented, now the only UI surface

`POST /api/reporting/ai/agent` is a Tier-2 agentic tool-loop (`ask_agentic` in
`nx_lib/reporting/ai.py`; see §3's Tier 2 for the general architecture) that
self-repairs across tool calls instead of drafting once. As of the 2026-07-27
chat-panel glow-up (`docs/superpowers/plans/2026-07-23-reporting-ai-chat-glow-up.md`)
this is not just "one of three surfaces" any more — it is the **only** AI
surface either tab's UI can reach. The old three-sub-mode "Ask AI" tab (Build a
report / Write SQL / Agent) and the Simple tab's separate one-shot ask + Refine
bar are gone; a single **"AI chat"** toggle on both tabs opens one docked
slide-over panel (`templates/js/_reporting_ai_js.html`, now the chat module,
`window.ReportingChat`) that always talks to this one endpoint.

**History contract (multi-turn conversation).** The request body gained a
`history` field: an array of `{role: "user"|"assistant", content}` entries, one
per prior turn. Server-side (`api_ai_agent` in `nx_lib/views/reporting/ai.py`):

- Anything not shaped like `{role: "user"|"assistant", content: <non-empty str>}`
  is dropped outright (`Invalid history` → 400 if `history` isn't a list at all).
- The kept entries are capped to the **last 8**, then trimmed further from the
  front while their combined `content` length exceeds **12000 characters** — a
  long conversation degrades to "recent turns only" rather than growing the
  prompt unboundedly. (Raised from an original 4000 in #178 A3 — see
  **artifact-carrying history** below for why plain answer text alone stopped
  being enough room.)
- History is **text-only**: no grounding, schema, or catalog text is ever
  threaded through it. The current turn's schema/date/process grounding is
  concatenated with the current `question` into a single `initial` message that
  is **always the final message in the request**, never mixed into `history` —
  so grounding text is sent once per turn, not once per turn *times* every prior
  turn still in the window. This is a deliberate token/cost boundary as much as
  a correctness one: multiplying a multi-KB catalog by 8 history entries would
  make follow-ups the expensive part of the conversation, not the cheap part.
- Tool binding (data-free vs. data-egress) is decided fresh per request from the
  caller's *current* permissions — a turn earlier in `history` cannot smuggle in
  access the caller doesn't hold right now.

**Artifact-carrying history (#178 A3).** A follow-up that only changes *how*
the previous answer is presented ("show it as a chart", "break that down by
process", "only this quarter") needs to keep operating on the **same**
source and query the previous turn actually produced — not have the model
re-derive (and potentially mis-derive, or silently switch source for) a new
one from its own prior English answer. So the client-side history entry it
records for each assistant turn is not just the answer text: whenever the
turn's response carried a `sql` and/or a `definition`, the client
(`templates/js/_reporting_ai_js.html`) appends a fenced block to that turn's
`content` before pushing it onto `history`:

```
<answer text>
[sql from this answer]
<sql, truncated to 1500 chars>
[report definition from this answer]
<definition JSON, truncated to 1200 chars>
```

Both markers are plain literal text inside an otherwise-ordinary history
`content` string — there is no structured side-channel for artifacts, by
design (§2b's "text-only" rule above still holds; this is *conversation*
text, not grounding text). The system prompt (`nx_lib/reporting/ai.py`,
English-only, model-facing — never gettext-wrap this) explicitly instructs
the model: on a presentation-only follow-up, stay on the source/data behind
the `[sql from this answer]` / `[report definition from this answer]`
context carried in `history` rather than switching sources. Truncating each
artifact (1500/1200 chars) rather than dropping it wholesale is why the
overall history character cap had to move from 4000 to 12000 — a couple of
turns' worth of SQL/definition text no longer fits in 4000 alongside the
answer prose and the 8-entry window.

**Live build-step ticker.** `POST /api/reporting/ai/agent` with `"stream": true` (see
`docs/howto/reporting.md` → **Agent endpoint contract → Live progress** for
the NDJSON wire format) emits `{"phase": "thinking"|"note"|"tool", ...}`
lines as the loop runs; the chat panel (`_reporting_ai_js.html`) turns these
into a two-part live status rather than a single rotating line (#178 A1):

- A **title line** — `"Asking the AI…"` initially, the model's own tool-turn
  preamble when `phase: "note"` carried one (truncated to 120 chars,
  rendered via `textContent` only — it is untrusted model output), or
  `"Thinking… (N)"` on `phase: "thinking"` turns after the first.
- A **growing ordered list of build steps**, one appended per `phase: "tool"`
  event, labeled from the tool name (`build_definition` → "Building the
  report…", `run_definition` → "Running the report…", `validate_sql` →
  "Checking the query…", `run_sql` → "Running the query…", `compute_stats` →
  "Crunching the numbers…", unknown tool names fall back to a generic
  "Working…"). The stream carries no explicit
  per-tool *completion* event, so the previous step is marked done the
  moment the *next* one starts (or never, if it was the last tool call
  before the final `done` line) — "the next thing starting" is the only
  completion signal there is.

**UI behavior:** see `docs/howto/reporting.md` → **AI assistant → AI chat
panel** for the toggle, panel, action-chip, and follow-up-chip behavior — that
is user-facing documentation and is not duplicated here.

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
| **Result rows** ("explain these numbers", chart suggestion) | Optional | **Off by default**; gated by `reporting.ai.explain.use` |

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
nx_lib/views/reporting/ai.py      + POST /api/reporting/ai/ask  (NL → {definition|sql|answer})
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

> This is the original pre-build sketch. What actually shipped differs in two
> ways worth knowing if you go looking for these names: there is no
> `POST /api/reporting/ai/explain` route — the data-egress narration path that
> shipped is (a) the agent's `run_sql`/`compute_stats` tool binding *inside*
> `POST /api/reporting/ai/agent` (§2b) for live queries, and (b)
> `POST /api/reporting/ai/caption` (Phase 5) for narrating an *already-fetched*
> result's rows, both gated by `reporting.ai.explain.use`. And
> `templates/js/_reporting_ai_js.html` is no longer an "Ask AI panel" with its
> own sub-modes — it's the chat module (`window.ReportingChat`) behind the
> single AI chat toggle (§2b).

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
| `reporting.ai.sql.use` | Receive/run **Surface B** SQL — **implies** `reporting.sql.run` |
| `reporting.ai.explain.use` | Allow result **rows** to be sent to the model (data egress). Gates two distinct things: **auto captions** on any result (alone — no live query, the rows already left the DB through the ordinary run) and, **combined with `reporting.sql.run`**, the chat agent's `run_sql`/`run_definition`/`compute_stats` tools (the model's own live read-only queries and definition runs). |

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
  exactly like the existing SQL sandbox. So `reporting.ai.sql.use` must be granted as
  deliberately as SQL access. Surface A keeps scoping. Document this prominently.
- **Prompt injection:** free-text DB values (e.g. a comment column) returned to
  the model could contain "ignore your instructions" payloads. Harmless for
  execution (RO + gate), but treat model output as **proposals only** — never let
  model text trigger side effects beyond a gated run. Keep `reporting.ai.explain.use` opt-in.
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

**As shipped (2026-08-06):** a single **"AI chat"** toggle in the masthead
(gated by `reporting.ai.use`, both tabs) opens one docked slide-over chat panel
— not the originally-envisioned third **Table / SQL / Ask AI** toggle with
separate sub-modes. That richer per-surface chrome (a `Run`/`Copy SQL` button
row, a distinct "Make a chart" action, a live `Explain this query` affordance)
was never built as separate UI; the panel instead exposes one small, consistent
action set per turn (**Open report**, **Insert into SQL editor**, **Show
query**, plus canned follow-up chips) — see `docs/howto/reporting.md` → **AI
assistant → AI chat panel** for the exact behavior. What *did* ship as
originally envisioned:

- **Conversational follow-ups** ("now break it down by month", "only Generali",
  "as a chart") — via the chat panel's `history` param (§2b), not a separate
  per-message streaming UI (turns are request/response, not token-streamed);
  each turn's produced SQL/definition rides along in `history` too (§2b
  **artifact-carrying history**), so a presentation-only follow-up stays on
  the same data instead of the model re-deriving it from its own prose.
- **Visible tool steps for trust** — the collapsed "How the agent worked" trace
  per turn, plus a **live build-step ticker** while a turn is in flight (§2b)
  narrating which tool the agent is currently running.
- **Open report** (opens an agent-produced definition straight into the
  Simple result view via `window.ReportingSimple.openDefinition()`, #178
  A4 — falls back to filling the Advanced builder wells if that seam isn't
  loaded), **Insert into SQL editor** (review then run via the existing
  sandbox).
- Transparency first: the tool trace and any SQL are always inspectable before
  the user acts on them.
- i18n: all new strings via `{{ _('…') }}` / `gettext`, de/fr/it (the
  `test_translations.py` gate enforces coverage).

Not built: a dedicated **Make a chart** one-click action from a chat turn (the
user reaches charting via **Open report** → the existing chart view), a
**Save as report** / **Schedule** action directly from the chat panel (same —
via **Open report**), and streamed (token-by-token) responses.

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
| **3a–3c — Agentic spine** | Tier-2 tool-loop (`ask_agentic`) with self-repair + turn cap; provider tool-calling (Azure + Anthropic); tool layer (`ai_tools.py`); deterministic stats engine (`stats.py`, stdlib) | gate, run, validator, audit | ~days | ✅ done (2026-06-03) |
| **3d — Drafter route + Agent UI** | `POST /api/reporting/ai/agent` (Surface C): self-repairing drafter; binds data-free tools by default (`build_definition`, `validate_sql`); returns a validated artifact + tool trace; audits `Surface='agent'`. Original **Agent sub-mode** UI: visible tool-step trace + follow-up conversation, one of three sub-modes on an "Ask AI" tab — **retired by Phase 5** below, which replaces the whole three-sub-mode tab with one chat panel over this same endpoint | the spine | ~days | ✅ done (2026-06-04); UI superseded 2026-07-27 |
| **3e — Data egress** | `run_sql` / `compute_stats` bound into the live loop behind **`reporting.ai.explain.use`** (migration `0015`; admins seeded; only effective with `reporting.sql.run`) so the model narrates real result numbers; off by default → schema-only. (Glossary RAG deferred — needs a curation owner) | new perm + migration | ~days | ✅ data egress done (2026-06-04); RAG planned |
| **4 — Semantic layer (Slice 1 — metrics)** | Canonical **metrics** (named server-side aggregations) in `dbo.ReportingMetrics`; definition `metrics` list → GROUP BY by `columns`; aggregate branch in both query builders; `/reporting/metrics` admin (`reporting.metrics.manage`, migration `0017`); builder Metrics well; metric catalog injected into the AI schema | `query.py`, `table_query.py`, `schema.py`, `ai_schema.py` | strategic, larger | ✅ Slice 1 done (2026-06-08); dimensions + locked `FilterJson` planned |
| **5 — Chat glow-up** | Retire the three-sub-mode "Ask AI" tab + Simple's one-shot ask/Refine bar in favor of one multi-turn **AI chat panel** (§2b) on both tabs, fronting Surface C via a new `history` param (8 turns / 4000 chars, text-only); **`POST /api/reporting/ai/caption`** — a `reporting.ai.explain.use`-gated 1–2 sentence auto-narration under any result (`Surface='caption'`); plus non-AI chart/table formatting polish, dark-mode repair, and a non-AI **comparison**/delta-chip feature on `/api/reporting/run` (Simple tab) | the spine, `/run` | ~days | ✅ done (2026-07-27) |

**Phase-1 acceptance:** a user with `reporting.ai.sql.use` types a question, gets
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
   (for "explain these numbers")? If no, drop `reporting.ai.explain.use` and
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
