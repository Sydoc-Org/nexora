<!--
Shown automatically when opening a PR. The checklist is the stuff that is easy
to forget because nothing else catches it — delete the lines that do not apply.
-->

## What changed

<!-- One or two sentences. Link the issue: "Closes #123". -->

## Before merging to `main`

- [ ] **Env keys on PROD.** If this PR added or renamed anything in
      `env/*.env.example`, run `python scripts/env-sync.py` and paste the
      missing `KEY=value` lines into `\\syapp01\d$\sydoc\nexora\env\PROD.env`.
      `deploy.yml` excludes `*.env` from the robocopy mirror, so **env keys
      never deploy themselves and the omission is silent** — a feature ships,
      runs, logs happily, and quietly does nothing. (Only *missing keys* are
      actionable; a value that differs between dev and PROD is normal.)
- [ ] **Scheduled tasks.** New `ops/` script that needs wiring? Import its task
      XML on SYAPP01 and confirm one manual run.
- [ ] Migrations applied to INT, and immutable (a change means a new file).
      PROD migrations run automatically on deploy — env keys do not.
- [ ] `CHANGELOG.md` updated under `[Unreleased]`, docs touched by the change
      updated in the same PR.
- [ ] Tests pass locally (`pytest`), translations in sync if strings changed
      (`/nx-i18n`).

## Verification

<!-- How you actually confirmed this works — a command and its output, a
     screenshot, a live run. Green mocked tests alone are not verification. -->
