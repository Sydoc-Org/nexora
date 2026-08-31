# Beautification Phase 2c — measured performance mediums — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Findings come from the 2026-08-31 performance audit (live-measured on INT: `/api/workitems` 638ms warm median, page shells 68-225ms). Anchor on symbols, re-Grep before editing.

**Prerequisite:** independent of 2a/2b — may run in parallel **in its own worktree**, but coordinate on `nx_lib/workitem_sources.py` if 2a is in flight. Shared context: the Phase 0+1 plan. **Migrations needed: NO** (query changes are code-side). **Measure before/after for every task** — curl against `127.0.0.1` (never `localhost`), 3 runs, median; record numbers in the commit body.

**Goal:** Cut the measured hot-path costs: the workitems double-CTE, the per-row source-probe loop, the prepared-docs N+1, pool/timeout hygiene, generali dashboard caching, and the per-request session rewrite.

---

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | Count via `COUNT(*) OVER()` window function in the page query itself — no separate count query, no count cache. | One query instead of two identical heavy CTE scans; simplest correct fix, works on both SQL Server and PG. |
| D2 | Source-routing cache stores are batched per page, not deferred to background. | No background machinery exists; a single batched MERGE after the merge loop removes the per-row commit storm with ~10 lines. |
| D3 | Pool sizing: NexoraDB engine `pool_size=32, max_overflow=16`; other engines unchanged. | Every request touches NexoraDB (hooks); 32 waitress threads must never queue on the pool. Other engines are not per-request. |
| D4 | The unbounded `?all=true` on the three generali list endpoints gets the export ceiling (100k), not removal. | Consumers exist; a cap is the non-breaking fix. |

### Task 1: Kill the double CTE in workitems paging

- [ ] `nx_lib/workitem_sources.py` — both `def list_workitems(self, filt, offset, limit):` implementations (SqlServerSource and the PG twin): replace the separate `COUNT(*)` execution of the ranked CTE with `COUNT(*) OVER ()` selected in the page query; total read from the first row (0 rows → run a cheap `SELECT COUNT`-only fallback or return 0 with filters that yielded nothing — keep semantics identical).
- [ ] Unit tests for both dialects (mock cursor) + integration on INT; **measure** `/api/workitems` before/after (expect a large cut of the 638ms).
- [ ] Commit: `perf(workitems): single-pass paging via COUNT(*) OVER()`.

### Task 2: Batch the source-routing warm loop

- [ ] `fetch_merged_page` post-merge loop calls `get_source_for_workitem` + `_cache_store` per uncached row (per-row probes + MERGE+commit). Batch: collect uncached ids, resolve with the existing batched lookup where possible, and write ONE MERGE (table-valued or executemany) + one commit.
- [ ] Test with a page of fresh MS02 rows (INT has the 1216-collision fixtures); measure a cold multi-source page.
- [ ] Commit: `perf(workitems): batch source-routing cache stores per page`.

### Task 3: Batch the prepared-documents stage N+1

- [ ] `views/workitems.py::_resolve_prepared_doc_wid_stage` runs one PG ranked-CTE per PID (up to 200/page). Add a batch variant of the PG stage resolver (`WHERE twi."ID" = ANY(%s)`) and resolve the page in one round-trip.
- [ ] Test + measure the prepared-documents page.
- [ ] Commit: `perf(prepared-docs): resolve stages in one batched query`.

### Task 4: Pool and timeout hygiene

- [ ] `nx_lib/db.py`: NexoraDB engine → `pool_size=32, max_overflow=16` (D3). Add `LoginTimeout` to the ODBC connect string (5s) so a downed DB fails fast instead of ~15s driver default.
- [ ] `views/reporting.py::api_sources_health` (or its 2a home): probe engines via the parallel/bounded idiom `ping_dbs_parallel` already provides (0.8s budget) instead of sequential unbounded probes.
- [ ] Verify INT under parallel load (simple concurrent curl loop); watch for pool exhaustion warnings.
- [ ] Commit: `perf(db): size NexoraDB pool for 32 threads, bound connect and health probes`.

### Task 5: Generali dashboard caching + the all=true cap

- [ ] `views/generali*::api_generali_stats` (7 aggregate scans/load) and `api_generali_filter_options` (7 DISTINCT scans/load): `@cache.cached`-style 120s per-user/per-filter caching (house precedent: the dashboard KPI endpoints with their error-response filter).
- [ ] Cap the three `?all=true` list endpoints at the export ceiling (D4).
- [ ] Tests + measure the generali dashboard load.
- [ ] Commit: `perf(generali): cache dashboard aggregates, cap unbounded list exports`.

### Task 6: Stop rewriting the session every request

- [ ] `nx_lib/hooks.py`: the per-request `session["permissions"] = …` / `session["ui_prefs"] = …` assignments mark the session dirty even when values are unchanged → filesystem session write + Set-Cookie per request on PROD. Assign only when the value actually differs.
- [ ] Careful: equality must be on the plain data (lists/dicts), and the #155 rule stands — this changes WHEN we write, never WHAT is read fresh.
- [ ] Integration test: unchanged-permission request leaves `session.modified` false; changed permissions still propagate within the TTL.
- [ ] Commit: `perf(session): skip session writes when permissions and prefs are unchanged`.

### Task 7: Changelog + docs

- [ ] `CHANGELOG.md` (Performance) with the measured before/after numbers; touch `docs/design/architecture-conventions.md` if pool numbers are documented. Full gate green.
- [ ] Commit: `docs: record phase 2c performance results`.

## Gotchas & notes

- Timing methodology from the audit: warm medians, `127.0.0.1`, dev server restarted first. PROD gains will exceed INT for Task 4/6 (32 threads + Flask-Session filesystem exist only there).
- Do not touch what the audit certified good: `user_cache` TTL layer, maintenance cache, dashboard KPI caches, docfield allow-set caching, compression (and never suffix the ETag).
- The `?all=true` cap is user-visible — CHANGELOG entry + check no scheduled export relies on >100k rows.
