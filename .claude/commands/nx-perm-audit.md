---
description: Audit the live nexora permission grants for anomalies (a customer seeing another org's processes or tenant pages, profile/org mismatches, customers with admin codes, override noise, dead codes). Read-only, PROD by default.
argument-hint: "[PROD|INT]"
---

Run the read-only permission audit and explain what it found. Environment: `$1`, default `PROD`.

1. **Run** from the repo root with the project venv: `.venv\Scripts\python scripts/perm-audit.py --env <ENV>`. It only SELECTs and calls `dbo.spGetUserPermissions`; it never writes. Save a copy to `var/reports/perm-audit-<ENV>-<date>.md` (gitignored).
2. **Explain** each section in plain words and say whether it looks intentional:
   - **Cross-organization grants** — a customer user effectively sees another customer's processes or another tenant's pages. Staff (org `SYDC`, profiles `enterpriseAdmin`/`globalAdmin`) are exempt. This is the finding the audit exists for.
   - **Profile does not match organization** — the profile was built for another org (a Privera user on `issUser`). Usually the same root cause as a cross-org line.
   - **Customers holding admin codes** — any `admin.*` on a non-staff user.
   - **Override noise** — per-user overrides that change nothing. Cleanup candidates, not risks.
   - **Housekeeping** — users without a valid profile, empty profiles, codes nobody holds, codes the codebase never references, profile-level deny rows (no effect; #238 drops them).
3. **Group by root cause** (same org, same profile) instead of repeating per user. Where PROD and INT differ (per-process `process.<client>.<name>.view` codes on INT since #238's `0087`, legacy families on PROD), say so.
4. **Never change** grants, profiles or users from this command. A fix is a separate request: `/admin/users` and `/admin/permissions` in the app, or a migration for catalogue changes.

Rules live in `audit()` in `scripts/perm-audit.py`. Its tenant fallback map mirrors migrations 0089–0104 and is dead code once PROD carries `Organizations.TenantCode`; delete it then.
