# MS02 multi-source integration

Full detail on the MS02 client's Postgres engines, multi-source workitems, doc-field search, and
the prepared-documents register. Moved here from `CLAUDE.md` (2026-07-14) to keep that file lean;
this is the authoritative reference for the facts below.

## Engines (`nx_lib/db.py`)

- `engine_ms02_pg` — the MS02 client's Azure Postgres runtime DB (same Octo schema, PG dialect);
  stays `None` until its `MS02_*` env vars are set (graceful degrade).
- `engine_ms02_stats_pg` — the MS02 client's dashboard-statistics DB (`Praesidialdepartement_BS`,
  Azure Postgres); stays `None` until `MS02_STATS_DB_*` are set (defaults reuse the MS02 runtime
  host/login). The dashboard reads the actual stats table + date columns from the `'ms02'`
  `dbo.Statconfig` row (`public."DossierStatistik"`, cols `DatumInTempExport`/`ImportDate` — *not*
  the dead `public.batchtracking` that `0025` first seeded; corrected by migration `0031`), so it
  never hardcodes a Postgres table name.
- `engine_ms02_docfields_pg` — the MS02 client's doc-field source DB (Azure Postgres, same
  host/login as the MS02 runtime, a *different* dbname — for MS02 the client's *statistik* DB
  `Praesidialdepartement_BS`, which holds the per-process columnar tables like
  `public."DossierStatistik"`); stays `None` until `MS02_DOCFIELDS_DB_*` are set (defaults reuse
  the MS02 runtime host/login; only the dbname differs). Doc-field search pre-resolves matches
  against it into a workitem-id allow-set — no ETL, never joined in-query to the runtime DB.
  **Degrade contract (fail closed):** while this engine is `None` — or any resolution step
  errors — an active doc-field search excludes MS02 rows entirely (empty allow-set), it never
  runs the Postgres source unconstrained. An env with the MS02 runtime configured but no
  `MS02_DOCFIELDS_DB_NAME` (STAGING, 2026-07-20) used to flood every doc-field search with the
  full MS02 corpus.

## Workitem identity is compound (client + id)

Workitem ids are unique only **within** a client: on INT 1216 ids exist in both the Octo
runtime and the MS02 runtime (96 of them visible in a single unfiltered list). Anything keyed
on a bare workitem id is therefore ambiguous, and the following rules are load-bearing:

- **Detail requests carry the row's client** — `/api/get_media_info/<id>`,
  `/api/get_media_raw/<id>/<idx>` and `/api/get_audithistory/<id>` accept `?client=<code>`,
  which the list row supplies (`data-client`). `get_source_for_workitem(id, client_hint=…)`
  trusts that hint over probing, because probing cannot distinguish two identically numbered
  workitems.
- **The probe includes the default source.** It previously probed only non-default clients, so
  a default/MS02 collision looked like a single MS02 claim and was cached permanently in
  `dbo.WorkitemSourceCache`. Ambiguous ids are now logged and never cached.
- **Per-workitem caches are keyed per client** (`_wi_cache_key`), or one client's document
  answers for the other's identically numbered workitem.
- **Front-end element ids are keyed `client-id`**, not the bare id — two rows otherwise shared
  one DOM id. At most one detail panel per id is open at a time, since the shared panel
  partial's internal ids are still id-keyed.
- **The PID-register cross-reference (`_stamp_in_register` → `dbo.PreparedDocuments`) is
  MS02-only.** Ids collide across clients, so it resolves rows to PIDs (via
  `resolve_ms02_wids_to_pids`) only for rows whose `client == "ms02"` — an unfiltered lookup would
  stamp a default-client row with an unrelated MS02 person's PID. `resolve_ms02_pid_to_wids` /
  `resolve_ms02_wids_to_pids` still normalize ids at the NVARCHAR/string-vs-Postgres-integer seam
  (`_as_workitem_ids`, `int()` coercion) before matching — an unnormalized id silently drops out
  of the PID map, the same failure mode that used to break every tag/priority/assigned filter
  before collaboration was removed.

## Multi-source workitems

The MS02 client is integrated via `nx_lib/workitem_sources.py` (per-source adapters
`SqlServerSource`/`PostgresSource`, plus the probe-then-cache routing backed by
`dbo.WorkitemSourceCache`, migration `0023`) and `nx_lib/clients.py` (client registry mapping each
client to its runtime engine + Octo creds). Octo access-token requests are signed with per-client
credentials. The Postgres driver is `psycopg2-binary` (must be installed on the prod interpreter
separately — see `docs/howto/iis.md`).

## Dashboard statistics

Dashboard statistics are made multi-source via `dbo.Statconfig.ClientCode` (migration `0024`) —
`'default'` rows are served by the Statistics DB (T-SQL), `'ms02'` rows by `engine_ms02_stats_pg`
(Postgres, aggregated once over `public.batchtracking`); the `ClientConfig` registry carries each
client's `stats_engine`/`stats_dialect`.

## Doc-field search

Doc-field (document-field) search is `SearchConfig`-driven for every client:
`dbo.SearchConfig.ClientCode` (migration `0027`, mirroring `Statconfig.ClientCode` from `0024`)
routes `'default'` rows to StatisticsDB and `'ms02'` rows to `engine_ms02_docfields_pg`. For BOTH,
`col_<field>` is a real **column** name in a wide per-process *statistik* table
(`SearchConfig.TableName`, e.g. `public."DossierStatistik"`), matched columnar as
`"<col>"::text ILIKE %value%` and pre-resolved to a workitem-id allow-set
(`resolve_ms02_docfield_ids` in `nx_lib/workitem_sources.py`) applied as `twi."ID" = ANY(...)`.

Migration `0030` corrected the earlier EAV (`t_DocumentIndexes` `"Name"`/`"StringValue"`)
assumption from `0027`: the MS02 doc-field source is the columnar `DossierStatistik` (in the same
Postgres DB the stats engine uses), not an EAV index; `'ms02'` rows therefore carry
Postgres-syntax `TimeFilter`s (the `'default'` rows stay T-SQL).

Doc-field visibility is permission-aware — `dbo.Search_Field_Labels.IsSensitive` marks sensitive
`FieldKey`s, gated by the shared `workitems.filter.documentfields.sensitive` permission and
enforced server-side at every surface (dropdown, values API, search, detail panel, CSV).

## Personal-number (PID) import & prepared-documents register

The same statistik table also backs an MS02-only **personal-number (PID) import**:
`resolve_ms02_pid_to_wids` (per-PID map resolver; sibling to `resolve_ms02_pid_ids`) and the
`/import_prepared_audit` route upserts an uploaded five-column Excel
(PID/Collected/CollectedBy/Prepared/PreparedBy — duplicate 'PreparedBy' header tolerated via
positional first-wins) by PID into the persistent register `dbo.PreparedDocuments` (migration
`0033`): one row per personal number, accumulating, shared across MS02 users, read-only +
clear-whole-list (v1).

The register is viewed on the standalone `/prepared_documents` page (route in
`nx_lib/views/workitems.py`; data access in `nx_lib/prepared_documents.py`; templates
`prepared_documents.html` + paired `templates/js/_prepared_documents_js.html`) with real
OFFSET/FETCH pagination and a live (non-stored) Octo cross-reference status column computed per
page via `resolve_ms02_pid_to_wids`. The workitems-page link to that page is shown only when an
MS02 prepared-docs target process is selected (e.g. `sydoc.05_PDBS`); it is hidden on "All
Processes" and on non-PDBS processes. Gated by `workitems.import.preparedaudit` (migration `0029`,
reused) AND `ms02_active`; registered in `page_visibility()` as `preparedDocsPagePerm`.

The earlier transient session-overlay (`?pidImport=<token>` filter with row-merge + synthetic
rows) has been removed. The personal-number column is owner-seeded as the `'ms02'` `SearchConfig`
`col_pid` value (read dynamically per the user's `target_processes`, e.g.
`ProcessName='sydoc.05_PDBS'`; the full PDBS mapping + `ClientCode='ms02'` is migration `0030`).

The register's Octo-Status cell also exposes a read-only **Preview** modal (via the shared
`templates/js/_workitem_detail_panel_js.html` partial) showing the full workitem detail panel
beside a renamed "Open in Workitems" link; write controls are suppressed in that context. The
modal's Import → Extraction → Validation → Delivery timeline reflects the document's live Octo
stage/status (resolved via `resolve_octo_wid_stage`, forwarded as
`data-status`/`data-current-stage` into the shared renderer). A reverse **"In register"** chip on
the Workitems detail panel links back to `prepared_documents?pid=<pid>`, and the register accepts
an exact `?pid=` URL filter with a "Show all" reset link.

Helpers: `pids_in_register()` (bulk PID→register-presence lookup in
`nx_lib/prepared_documents.py`) and `resolve_ms02_wids_to_pids()` (workitem-ID → PID reverse map
in `nx_lib/workitem_sources.py`). MS02-only; no dedicated permission, no dedicated migration.
