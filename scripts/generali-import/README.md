# Generali CSV import scripts

Two scheduled jobs that run on the import host **prdimpexp01**
(`\\prdimpexp01\d$\sydoc\scripts\generali`):

1. **`getGeneraliCsvAttachment.ps1`** — pulls CSV (`.csv` / `.csv.gz`) attachments from the Generali
   mailbox via Microsoft Graph, decompresses them into `…\generali\import`, and moves each processed
   message to the *Gelöscht* folder. Scheduled by **`Import CSV Mail Attachment.xml`**.
2. **`csvToSql.ps1`** — MERGEs every CSV in `…\generali\import` into `reportjob` (logging each run in
   `ImportRuns`), first on **INTSQL01**, then on **PRDSQL01**. Scheduled by **`Import CSV to DB.xml`**.

## Layout

```
scripts/generali-import/
  .env.example      template for the secrets file (committed)
  .env              real secrets (gitignored) — master copy you deploy to the host
  remote/           the copies that run unattended on prdimpexp01 (Task Scheduler)
    getGeneraliCsvAttachment.ps1
    csvToSql.ps1
    Import CSV Mail Attachment.xml   (task export)
    Import CSV to DB.xml             (task export)
  local/            hand-run backup copies — identical behaviour, just interactive
    getGeneraliCsvAttachment.ps1
    csvToSql.ps1
```

`remote/` and `local/` are **identical except one thing**: `isLocal`.

- `remote/` → `isLocal` returns `$false`: runs silently, no prompts (for the scheduled task).
- `local/` → `isLocal` returns `$true`: prints progress and asks Y/N before each write — for when you
  run it **by hand** from your workstation as a fallback because the scheduled run failed.

Both folders point at the **same** paths (`\\prdimpexp01\d$\sydoc\scripts\generali`), read the **same**
`.env`, hit the **same** SQL servers and the **same** mailbox. `local/` is a manual backup, not a
separate environment.

## Configuration (`.env`)

The scripts no longer use `env.json`. Each one loads `\\prdimpexp01\d$\sydoc\scripts\generali\.env`
through the `load_from_dot_env` helper (defined at the top of the script) into process env vars, e.g.
`$env:DATABASE`, `$env:CLIENT_SECRET`.

`.env` format: `KEY=value`, one per line, **no quotes, no spaces around `=`, no inline comments** (a
trailing `# …` is folded into the value). Full-line comments (`# …`) are ignored. See `.env.example`
for the full key list.

## Deploying to prdimpexp01

1. Copy `remote/*.ps1` to `D:\sydoc\scripts\generali\` on the host (the scheduled tasks run them from
   there; the two `.xml` files are exports of those tasks).
2. Put the secrets file at `D:\sydoc\scripts\generali\.env` — copy this repo's `.env`, or convert the
   host's old `env.json` in place:

   ```powershell
   $j = Get-Content -Raw env.json | ConvertFrom-Json
   $j.PSObject.Properties | ForEach-Object { "$($_.Name)=$($_.Value)" } | Set-Content .env -Encoding utf8
   ```

3. Delete the old `env.json` from the host once `.env` is in place.

## Running the backup by hand

From your workstation (needs access to `\\prdimpexp01\d$` and the SQL servers):

```powershell
pwsh -File .\local\getGeneraliCsvAttachment.ps1   # fetch attachments
pwsh -File .\local\csvToSql.ps1                    # MERGE into INTSQL01 then PRDSQL01 (with prompts)
```
