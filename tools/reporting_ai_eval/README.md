# reporting AI eval: 22-prompt statistical stress test

A repeatable harness for the reporting AI chat agent
(`POST /api/reporting/ai/agent`), covering hard statistical stakeholder
questions - partial-period alignment, YoY quarters, percentiles/medians,
outlier detection, seasonality, ratios, null/backlog semantics, ambiguity,
refusal. Committed so every fix to the agent has a measurable before/after
instead of one-off manual probing.

Full design context: `docs/design/reporting-ai-assistant.md`.

## Files

- `prompts.json` - the 22 prompts, grouped by trap, each with a `good` line
  describing what a passing answer looks like.
- `run_eval.py` - the collector. Logs in via `/dev/login/<user>`, posts every
  prompt to the agent endpoint, saves the full JSON response per case.
- `baseline_2026-07-28.md` - the original run's scored results (6.1/10
  average) and the issues it surfaced (#127-#130). Historical: it predates the
  #127/#128/#129 fixes, so it is not a valid "before" for anything measured
  today - collect a fresh before-run instead.
- `run_2026-08-03_issue132.md` - before/after pair for the #132 grounding
  fixes (5.41 -> 6.23), collected the same day on the same data so the prompt
  change is the only difference.
- `results/` (gitignored, created on run) - per-case raw JSON from your run.

## Running

Requires a running INT dev server with `/dev/login/<username>` enabled (see
`docs/howto/nx.md` - `nx -u`).

```
python tools/reporting_ai_eval/run_eval.py
# or against a non-default port/host, and a custom output dir:
python tools/reporting_ai_eval/run_eval.py http://127.0.0.1:8010 tools/reporting_ai_eval/results-after
```

Each case writes `<NN>.json` (prompt, HTTP status, elapsed time, full
response body incl. `answer`/`sql`/`definition`/`toolTrace`). A case whose
output file already exists is skipped, so an interrupted run resumes - delete
the file (or the whole output dir) to force a re-run. Requests are spaced 7s
apart to stay under the AI route's 10/min limiter.

## Scoring

The runner only *collects* - it does not score. Judging is
manual/Claude-assisted: read each `<NN>.json` against the matching `good`
line in `prompts.json` and score 1-10, the same way `baseline_2026-07-28.md`
was produced (an independent judge pass per case, reading the full response
and tool trace, not just the answer text). There's no fixed rubric beyond
"does this match what the `good` line describes" - use judgment, and note
anything the criterion doesn't anticipate (empty answers, crashes, wrong
universe of data) as its own finding.

To compare against the baseline: run the harness, score the fresh results the
same way, then diff the two score tables and read the per-case deltas rather
than just the two averages - a case can shift for a different reason than the
fix under test.
