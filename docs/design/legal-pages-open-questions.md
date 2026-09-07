# Legal pages: open questions (#260)

`/terms` and `/privacy` exist and every section is drafted, in English, German,
French and Italian. Both pages carry a prominent **Draft — not yet in force**
banner, and that banner stays until the questions below are answered and the
text has been reviewed by someone qualified to write it.

This document is the list of what is still missing, written as questions to
put to whoever owns the decision. It is deliberately not a legal document and
not legal advice — it is the set of facts and choices the pages need before
they can be published.

**Status:** 13 sections drafted, 12 gaps open. Every gap is marked in the page
itself as a *To be completed* note, so the page and this document cannot drift
apart silently.

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
