# Reporting help — in-app tips panel + docs sync guard (design)

Date: 2026-08-06. Decided interactively (all four options user-picked).

## What

1. **In-app tips panel** — a **Help** button in the Reporting page header
   opens a modal ("Get the best results") with curated tips: general
   result-quality tips plus Ask-AI prompting tips, and a **Full guide** link
   to the Confluence mirror of `docs/howto/reporting-guide.md`.
2. **Docs** — a new "Tips — getting the best results" section in
   `docs/howto/reporting-guide.md`; panel and section mirror each other.
3. **Sync guard** — convention (CLAUDE.md rule + banners in both files)
   plus a **non-blocking** pre-commit nudge: when reporting behaviour files
   are staged but neither the guide nor the panel is, print a reminder.

## Decisions

- Panel content is curated and translated (`{{ _('…') }}`, de/fr/it); the
  long-form guide is *not* duplicated in-app.
- Panel lives in its own partial `templates/_reporting_help.html` — a
  separate file so the pre-commit check can tell "help updated" from "page
  updated". Markup follows the existing `.reporting-modal` idiom; open/close
  is a self-contained inline script (toggle, Close, backdrop, Escape).
- AI tips block is wrapped in `{% if ai_enabled %}` — users without the
  assistant never see prompting tips for a bar they don't have.
- Full-guide link uses the title-based redirect
  `https://sydocteam.atlassian.net/wiki/display/nexora/Reporting+%E2%80%94+user+guide`
  (verified: Cloud 302-redirects `/wiki/display/<space>/<title>`, em-dash
  titles included). The guide page publishes when this branch merges to
  `main`; page-ID links were impossible before that and break on retitle
  anyway, so title-redirect is strictly better here.
- Nudge hook (`reporting-help-sync` in `.pre-commit-config.yaml`,
  `scripts/check-reporting-help-sync.py`): watches
  `templates/reporting.html`, `_reporting_simple.html`,
  `reporting_metrics.html`, `reporting_sources.html`,
  `templates/js/_reporting_*`, `nx_lib/views/reporting.py`; stays silent when
  `docs/howto/reporting-guide.md` or `templates/_reporting_help.html` is
  staged too. Always exits 0 — refactor-only template changes are common and
  a blocking gate would train people to skip hooks.
- Tip claims were adversarially verified against the current code by a
  16-claim multi-agent pass before shipping (exact caps: chart 50/12,
  drill 100 rows, forecast ≥5 periods).

## Not done (deliberate)

- No per-feature contextual tooltips beyond what already exists — one panel,
  one guide section.
- No "what's new" changelog surface in-app.
- No blocking sync gate (see above).
