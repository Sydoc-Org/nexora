# Legal pages: open questions (#260)

`/terms` and `/privacy` exist and every section is drafted, in English, German,
French and Italian. Both pages carry a prominent **Draft — not yet in force**
banner, and that banner stays until the questions below are answered and the
text has been reviewed by someone qualified to write it.

This document is the list of what is still missing, written as questions to
put to whoever owns the decision. It is deliberately not a legal document and
not legal advice — it is the set of facts and choices the pages need before
they can be published.

> ## Answered 2026-09-24 — text filled in, still a draft
>
> Management answered a one-page German question sheet (20 questions) and
> settled the placement in a chat. The pages now carry real text, German
> (authoritative, written in German) and English (courtesy), in
> `templates/legal/{privacy,terms}_{de,en}.html`; the page picks German for a
> German UI and English otherwise, with a `?lang=de|en` switch. **On `main`**
> since 2026-09-24, live on dev and staging and switched off on PROD by
> `LEGAL_PAGES_LIVE` (`nx_lib/config.py`) until management signs it off.
>
> **Decided:**
>
> - Controller: Sydoc AG, Mühlegasse 18, 6340 Baar, UID CHE-112.467.492; seat
>   and place of jurisdiction Baar. Contact `privacy@sydoc.ch`.
> - nexora is **not sold standalone** — it stays an extension of Sydoc's
>   services, so the Terms supplement the client contract, which already covers
>   liability, availability and jurisdiction and prevails on conflict. A
>   data-processing agreement is concluded as standard.
> - Links sit **under Help in the profile menu** (plus the login-page footer, so
>   they are readable signed out).
> - Retention: request log 180 days, sessions 8 days (both implemented and
>   pinned to `nx_lib/config.py` by a test); accounts are never deleted
>   automatically — the client requests it (per-user billing); the client's
>   admin may have accounts blocked or deleted, and that is recorded.
> - No availability or support-hours promise in nexora; changes announced on
>   the page with a "Stand"/"last updated" date. German is authoritative.
> - Azure region Switzerland; ngrok (USA) has a contract (details with Ben);
>   no EU users today, left open via the DPA. Management reviews the text.
>
> **Still open before publishing:**
>
> 1. ~~Create the `privacy@sydoc.ch` mailbox.~~ **Closed 2026-09-30** (IT,
>    G. Ruoss): privacy questions go to the existing helpdesk mailbox
>    `support.helpdesk@sydoc.ch`, the same one feedback goes to — no separate
>    mailbox. The helpdesk must spot requests for information, which the
>    30-day deadline (Art. 18 DSV) applies to.
> 2. **Q17 was "no guaranteed deadline"** — the revDSG requires an answer to a
>    request for information within **30 days**, so the page says 30 days.
>    Confirm with management.
> 3. **Document retention (Q7/Q9)** — the answer assumed nexora keeps customer
>    documents 8 days; nexora keeps no copy of its own, it shows them from the
>    processing systems, and entries made in nexora (reports, hours) live in
>    the tenant DB. The page says "as set out in the contract" and marks the
>    rest open. Confirm the wording.
> 4. **AI provider (Q11) unknown** — which provider production uses, where, and
>    whether a DPA exists. Ask Ben; marked open on the page.
> 5. **ngrok = data outside Switzerland** — named on the page; confirm the ngrok
>    contract includes data-processing terms.
> 6. **fr/it users get the English text** — confirm that is acceptable.
> 7. Management review and sign-off → then remove the draft banner
>    (`test_both_pages_carry_the_draft_notice` pins it) and merge.
>
> **Review findings, same day (in the text now, marked open where undecided):**
>
> 8. **Sensitive data** — Generali documents include health data
>    ("Gesundheitsfragen", "Arztunterlagen"), which the revDSG treats as
>    particularly sensitive. The privacy page now has a section for it; *where*
>    the documents are stored (country) and the extra safeguards are open.
> 9. **Disclosure abroad** — to the USA via ngrok, and via the browser to
>    Google Fonts, cdnjs (Cloudflare) and jsDelivr on every page load, plus the
>    AI provider if it is abroad. The page must name the safeguard for each
>    (Swiss-U.S. Data Privacy Framework certification or standard contractual
>    clauses). Self-hosting the fonts and scripts would remove three of them.
> 10. **Jurisdiction** — Baar has no court; the text now says Zug (seat Baar
>     ZG), to be confirmed by a legal professional.
> 11. **Accounts never deleted** — conflicts with keeping data only as long as
>     needed. Proposed on the page as "to be decided": deactivate, then delete
>     or anonymise after e.g. 12 months, keep only the billing record. Needs a
>     decision **and** engineering work (no such job exists).
> 12. **Cookies** — one necessary sign-in cookie (HttpOnly, 24 h on PROD) and
>     settings in the browser's local storage; now described. No banner needed.
> 13. **The Terms are never accepted by a user** — they bind only through the
>     client contract, so the contracts should say that the nexora terms of use
>     are part of them.
>
> **Second review, 2026-09-29 — the page against the code** (branch
> `fix/260-legal-review`; "Stand" moved to 29.09.2026):
>
> 14. **Request log described too narrowly.** Each row also carries the IP
>     address, the session id and the query parameters — including free-text
>     searches, which in the Generali document search can be a name or a
>     policy number. Fixed both ways: `search`, `q` and `docvalue` are now
>     logged as `[redacted]` (`LOG_REDACTED_ARGS`, `nx_lib/hooks.py`), and the
>     page lists what a row does hold.
> 15. **"Deleted after 180 days" held for `dbo.Logs` only.** The CSVs under
>     `var/logs/user/` were removed only by `csvLogs_toDB.ps1`, which has no
>     task definition and runs on PROD only — dev and staging never drained
>     them. The request hook now deletes hour folders past the retention on
>     every environment. **Still to check on SYAPP01:** that a hand-made task
>     runs `csvLogs_toDB.ps1`, or `dbo.Logs` (the admin log viewer) is empty.
> 16. **Session files had no scheduled cleanup.** `cleanup_expired_sessionFiles.ps1`
>     now has `cleanup-session-files-task.xml`, registered by the deploy.
> 17. **Tailwind (cdn.tailwindcss.com, USA) was not named** although the
>     sign-in, error and legal pages load it. Named now; building the CSS
>     locally would remove it (and it is a development-only CDN anyway).
> 18. **Inventory gaps:** profile picture, last sign-in, the failed-attempt
>     lock and feedback mail to support were stored but not listed. Listed now;
>     how long feedback mail is kept is marked open.
> 19. **Cookie:** also set for signed-out visitors (it carries the CSRF token),
>     not only to keep someone signed in. **Two-factor sign-in** is mandatory,
>     not "where enabled". Both corrected.
> 20. **`<html lang="">` on every page** — 47 templates used `get_locale`,
>     which the template context does not have. Now `current_lang`, pinned by
>     `tests/unit/test_template_html_lang.py`.
> 21. The draft pages now carry `noindex`, since dev and staging are public.
>
> **Answers, 2026-09-29** (G. Ruoss), now in the text:
>
> - Business documents are stored on **Sydoc's own servers in Switzerland**.
>   Safeguards stated from the code: permission plus mandatory 2FA, and
>   sensitive-marked fields only for an extra permission.
> - Feedback mail is **deleted once the request is dealt with**.
> - **No rule** for accounts of people who left — the "to be decided" proposal
>   is gone; the page keeps "until the organisation asks".
> - AI provider: **Anthropic, Claude (Sonnet)**, used only by the reporting
>   assistant. The page says what goes there (question and schema; rows only
>   for `reporting.ai.explain.use`), and the assistant's own log
>   (`dbo.ReportingAiAudit`, never pruned) is now in the inventory.
> - US transfers: checked on the providers' own pages that day — **Google,
>   Cloudflare and ngrok are Swiss-U.S. DPF certified**; Anthropic is not (its
>   DPA carries SCCs with a Swiss addendum); jsDelivr relies on SCCs per its
>   privacy policy; **nothing found for Tailwind Labs**.
>
> **Tailwind closed the same day:** every page now loads Tailwind from
> jsDelivr (already covered by SCCs), so Tailwind Labs is no recipient; the
> host is out of the CSP too.
>
> **Still open before PROD:** document retention where the contract is silent
> ("ka"; proposed: contract term, then delete or return within 30 days); how
> long the assistant log is kept (proposed: 180 days, needs a prune job); that
> Sydoc has concluded Anthropic's DPA (check the company API account accepted
> the Commercial Terms — the DPA is part of them); jurisdiction Zug (legal);
> management sign-off. (Contact mailbox closed 2026-09-30: `support.helpdesk@sydoc.ch`.)
>
> **Checks against the running setup, 2026-09-30** (IT, G. Ruoss; "Stand"
> moved to 30.09.2026):
>
> - **Anthropic DPA — closed.** The production API key sits in Sydoc's own
>   organisation in the Claude Console (created by Ben). The DPA is part of
>   Anthropic's Commercial Terms, which every Console API organisation runs
>   under, so nothing separate is signed; the "to be confirmed" line is gone.
>   Worth doing: Sydoc's payment method on the organisation, a second admin
>   besides Ben, a spending limit.
> - **ngrok — confirmed.** Paid pay-as-you-go account under a `@sydoc.ch`
>   owner; ngrok's DPA is incorporated into its Terms of Service
>   (<https://ngrok.com/dpa>). One agent fronts dev, staging and PROD.
> - **MS02 Azure Postgres — Switzerland North.** The runtime host resolves to
>   an address in `20.250.0.0/16`, which Microsoft's published Azure IP ranges
>   (ServiceTags_Public_20260928) assign to `AzureCloud.switzerlandn`.
> - **All Sydoc servers are in Switzerland** — matches "Sydoc's own servers in
>   Switzerland".
> - **Staging accounts** checked: only people who may see the PROD data.
> - **Helpdesk mailbox — the page is wrong today.** Tickets are deleted once
>   solved, but the e-mails in `support.helpdesk@sydoc.ch` are **never
>   deleted**, while the page says feedback is "deleted once the request is
>   dealt with". Privacy requests (possibly with ID copies) now land there too.
>   To decide later: a Microsoft 365 retention policy (e.g. 12 months) and the
>   page says that period, or the page says the mails are kept.
> - **Cleanups on PROD — working** (read off `\\syapp01\d$\sydoc\nexora`):
>   `prune_request_log.log` ran 03:45, deleted 911 rows, oldest remaining
>   `dbo.Logs` row 2026-04-02 (180 days); `prune_active_sessions.log` ran
>   03:30, deleted 9 of 73; 319 session files, none older than 8 days; only 7
>   hour folders of CSVs left under `var/logs/user/` (oldest 2026-09-15), the
>   rest drained into `dbo.Logs`. Closes point 15's SYAPP01 check.
> - **Still to check:** backup retention on PRDSQL01 — if backups outlive
>   180 days, the page needs a sentence on backups.
>
> The questions below are the original list, kept for the reasoning behind
> each one.

---

## How to use this

Questions in **section 1** are lookups — someone can answer them from the
commercial register or the contract file in minutes. **Section 2** needs
someone who can read the client contracts. **Section 3** are decisions nobody
can look up; the business has to make them, and two of them need engineering
work afterwards. **Section 4** is a compliance checklist for third parties that
already receive data today.

The single most important question is **3.1 (retention)**. Everything else is
wording; that one is a gap between what the policy should say and what the
system actually does.

---

## 1. Who we are — register and identity

These block the controller identity on `/privacy` and the contracting party on
`/terms`. Both pages currently say only "Sydoc AG".

1. **What is the exact registered legal name of the entity that operates
   nexora?** Including legal form, as it appears in the commercial register.
2. **What is the registered address, and the UID (`CHE-…`)?** A privacy notice
   has to identify the controller well enough to be served.
3. **Which city is the registered seat?** This becomes the stated place of
   jurisdiction in the Terms.
4. **Is there more than one Sydoc entity involved?** If the entity that
   operates the platform is not the entity that contracts with clients, the
   two pages need to name different parties, and the privacy page needs to say
   which one is the controller.
5. **Who is the named contact for data-protection questions** — a person, a
   role, or a mailbox? A privacy notice with no reachable contact does not do
   its job, and this is currently blank.
6. **Is there a data protection officer or an appointed representative?** If
   so, they have to be named.

## 2. What our contracts already say

These need someone who can read the master agreements. In several places the
right answer may be *"the contract already covers this, and the page must not
contradict it."*

1. **Do the client contracts contain terms that override these pages?** If a
   master service agreement takes precedence, the Terms must say so explicitly
   rather than appearing to be the whole agreement.
2. **Are we the controller or the processor for the business documents?** The
   draft assumes: Sydoc is **controller** for account, session and request-log
   data, and acts **on behalf of the client organisation** for the business
   documents and their index fields. This needs confirming, because it decides
   who has to answer a deletion request — us or the client.
3. **Is there any availability or uptime commitment in the contracts?** The
   page currently promises nothing, which is safe. If a commitment exists it
   has to be reflected; if it does not, confirm that so the wording can stay.
4. **What do the contracts say about confidentiality**, and how do individual
   non-disclosure undertakings relate to the obligation the Terms puts on each
   user?
5. **What is the agreed liability position** — any cap, and how are indirect
   and consequential losses treated? **Research this, do not draft it.** The
   Liability section is explicitly reserved for a lawyer.
6. **Who inside a client organisation is entitled to have an account
   suspended,** and does suspension carry notice? The draft says Sydoc may
   suspend an account on misuse or at the organisation's instruction, without
   saying who may instruct it.
7. **Are any users EU data subjects?** If staff of any client organisation are
   in the EU, GDPR Art. 13/14 applies alongside the Swiss DSG and changes what
   the privacy notice must contain. Worth settling early — it is cheaper than
   rewriting.

## 3. Decisions only we can make

Nobody can research these. They are business decisions, and the first two need
engineering work once decided.

1. **What are the retention periods?** This is the important one. The privacy
   page currently states, truthfully, that **nothing in nexora has a defined
   retention period**. Four separate answers are needed:

   | Data | Where it lives | Today |
   |---|---|---|
   | Request log | `var/logs/user/` CSV rows and `dbo.Logs` | kept indefinitely |
   | Session rows incl. IP address | `dbo.ActiveSessions` | kept indefinitely |
   | Business documents and index fields | tenant databases | kept indefinitely |
   | Closed / disabled accounts | `dbo.Users` | kept indefinitely |

   The request log is the sharpest edge: a per-request record of who did what,
   with IP addresses, no stated purpose limit and no expiry. Note that #227
   addresses **only** the session table, and only once its scheduled task is
   registered on the app host — merging that PR deletes nothing on its own.

2. **What is the legal basis for each purpose?** The draft states the purposes
   accurately (access control, authentication, staying signed in, fault
   tracing and misuse detection, service delivery) but assigns no basis to any
   of them. Contract performance and legitimate interest probably cover most;
   that needs deciding and wording per category, not in the aggregate.

3. **During which hours is the platform supported?** Needed for the
   Availability section. The draft originally claimed Swiss business hours;
   that was removed because nothing supported it.

4. **How is a change to these documents announced, and how much notice does a
   material change get?** Nothing currently announces a change to a legal
   page — `whats_new.py` announces releases from a hardcoded list, which is a
   different thing. Related: the page shows no last-changed date, and adding
   one belongs with this decision.

5. **Does continued use after a change count as acceptance?**

6. **Which language is authoritative?** The German, French and Italian are
   working translations of the English draft. For a Swiss contract the German
   is often the governing version — and a translated liability or
   governing-law clause is a **different clause**. If German is to govern, it
   needs writing in German rather than translating into it, and the current
   de/fr/it should be treated as scaffolding.

7. **Where does a data-subject request go, how quickly do we answer, and how
   do we verify the requester's identity** before disclosing anything?

## 4. Third parties that already receive data

Each of these is live today. Each needs naming in the privacy notice and each
needs a data-processing agreement. The page currently names the categories but
not the specifics.

1. **Which AI provider does production actually use, and in which region?**
   The reporting assistant is provider-agnostic and configured by
   `AI_PROVIDER` — either Anthropic or Azure OpenAI. Confirm which is live,
   and get the DPA.

   Worth stating precisely, because it is easy to get wrong in both
   directions: the assistant sends database **structure** — table and column
   names and their types — in order to translate a question into a query. It
   sends **result rows** as well, but only for accounts holding *both*
   `reporting.ai.explain_data` and `reporting.sql.run`. For every other
   account, no business data leaves the platform through the assistant.

2. **Which Azure regions host the MS02 client runtime,** and is a DPA in
   place? That client's runtime, statistics and doc-field databases are on
   Azure Postgres.

3. **Microsoft Graph** carries all outbound mail, including scheduled report
   delivery. Usually covered by the Microsoft DPA — confirm which tenant and
   which contracting entity it sits under.

4. **The public tunnel.** Easy to miss and it matters: the site is exposed
   through **ngrok** today, with Cloudflare Tunnel prepared but not yet cut
   over. A third party terminating TLS on internal traffic is a sub-processor
   and belongs in the disclosure. Confirm the plan and the paperwork for
   whichever is in use when the page goes live.

---

## Already verified — no need to research these

Read off the running system, so they can be stated as fact:

- **What is stored about a user:** name, username, e-mail, organisation,
  language and interface preferences; a password hash and, where enabled, a
  TOTP secret; session identifier, IP address, created and last-seen times;
  a per-request log of time, path, method and account; business documents and
  their index fields.
- **Planned maintenance** is announced in the application and can block
  sign-in while it runs (`maintenance.html`, `_get_blocking_maintenance`).
- **A release restart** is well under a minute.
- **Unplanned outages** are detected by automated monitoring
  (`ops/outage_monitor.py`, `nx_lib/outage.py`).
- **Accounts are never self-registered** — every one is created by Sydoc.
- Both pages are reachable **signed out** and render no user data, which is
  deliberate: a privacy notice readable only after signing in cannot inform
  the decision to sign in.

## Worth reading first

- The revised Swiss Federal Act on Data Protection (nDSG) and its ordinance.
- FDPIC guidance on the required content of a privacy notice.
- GDPR Art. 13/14, **if** question 2.7 turns out to be yes.

---

## Related

- `templates/legal.html` — both documents; the gap notes correspond to the
  questions above.
- `tests/integration/test_legal_pages.py` — pins the draft banner, the factual
  inventory, and the absence of any retention claim while none is implemented.
- #227 — prunes expired `dbo.ActiveSessions` rows; the only retention work
  currently in flight, and it needs a scheduled task on the app host before it
  does anything.

---

## What can live in the contract instead of on the page

Only the client organisations sign a contract; the individual users — their
staff — sign nothing. That split decides what may be delegated to the contract
and what has to be on the site regardless, and it is not the same answer for
the two documents.

There are two different legal relationships here:

- **The contract** is between Sydoc and the client organisation. It can carry
  anything that is a commercial term between two companies.
- **The privacy notice** discharges a *duty to inform each individual* whose
  data is processed. That duty is owed to the person, not to their employer,
  so a contract the person never sees cannot discharge it.

### Can go in the contract, with the page pointing at it

Almost all of the Terms. If the master agreement already covers these, `/terms`
can shrink to a short pointer plus the handful of rules a user needs to see:

| Topic | Notes |
|---|---|
| Liability, and any cap | Commercial term. Belongs in the contract. |
| Availability / SLA | Same. The page should not state a figure the contract does not. |
| Governing law and jurisdiction | Same. |
| Confidentiality obligations | Contract, plus individual NDAs where they exist. |
| Scope — who may hold an account | Contract decides; the page describes it. |
| Suspension rights and notice | Contract decides who may instruct it. |
| Processor terms, sub-processor consent, audit rights | Belongs in a DPA annexed to the contract. |

### Must be on the page regardless of any contract

The privacy notice cannot be delegated. The information duty runs to each
individual, and for account, session and request-log data Sydoc is most likely
the **controller** in its own right — a client's contract cannot discharge
Sydoc's own duty there.

| Topic | Why it cannot move to the contract |
|---|---|
| Controller identity and contact | The person has to be able to find and reach us. |
| What is stored about them | Owed to the individual, not their employer. |
| Purposes and legal bases | Same. |
| Retention periods | Same. |
| Recipients and sub-processors | Same. |
| Their rights, and how to exercise them | A right the individual exercises directly. |
| Right to complain to the FDPIC | Statutory; cannot be contracted away. |

### Needs to be in both, and consistent

These are the ones that bite. If the contract and the notice disagree, the
disagreement is the finding:

- **Retention periods.** The DPA says what Sydoc must do; the notice tells the
  individual what happens. Both, and identical.
- **Sub-processors.** Named in the notice, and consented to in the DPA.
- **Acceptable use.** The obligation is passed down through the contract, but
  the user only ever sees the page.
- **Which entity is controller and which is processor**, per data category.

### What this means for the review

Ask for the master agreement and any DPA to be read against **section 2** of
this document. The likely outcome is that most of the Terms is already
answered, and the Privacy Policy is almost entirely not — because it addresses
someone who never signed anything. If a DPA does not exist yet, that is a
larger finding than any wording gap on these pages.
