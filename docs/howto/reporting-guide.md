# Reporting — user guide

This is the **how do I actually use it** guide for the Reporting page. No
technical knowledge assumed. If you want to know how the thing is *built*
instead, read [`reporting.md`](reporting.md) — that one is for developers.

<!-- Maintainers: this file is END-USER-FACING at runtime — the app renders it
  at /reporting/guide (nx_lib/views/reporting/pages.py), and the deploy workflow
  copies it to the server. Keep it current: if you change how Reporting
  *behaves* for a user, update this file AND the in-app tips panel
  (templates/_reporting_help.html, the Help button) in the same commit. See
  "Keeping docs in sync" in CLAUDE.md; the reporting-help-sync pre-commit hook
  reminds you. Keep the H1 unique (Confluence page title). -->

---

## The 60-second version

1. Open **Reporting** from the left navigation.
2. In the **Library**, click **New report** (top right).
3. Answer four questions: *what to measure* → *which processes* → *how to break
   it down* → *what time range*.
4. Click **Show result**.

You now have a number, a chart and a table. Everything else in this guide is
detail on top of those four steps.

---

## Tips — getting the best results

The same tips live inside the app: the **Help** button in the Reporting page
header opens them in a panel, and its **Full guide** link opens this whole
guide as an app page.

**Building a report**

- Watch the **coverage badge** (e.g. `2/5`) on measures and categories: only
  part of the processes provide that field, and documents from the others land
  in the empty bucket. Hover it to see which. If a number looks too low, check
  the badge first.
- Everything in one empty bucket? The breakdown field is not filled in for the
  processes you selected.
- Not sure which table a source really reads? Click its card in the **Sources**
  rail: **List** shows the tables it uses and their columns, **Diagram** draws
  the relationships between them.
- Relative presets stay relative: a report saved with "This month" shows the
  current month on every run and in every scheduled mail. Schedule times are
  UTC.
- To see **which document fields extraction gets right**, pick the "Field
  extraction quality" measure **"Extraction correct %"** and break down by
  **Field**. Sort by the measure ascending and the worst field is the top row.
- That source covers **every customer whose process is onboarded in nexora**, so
  break down by **Customer** to compare them, or add a Customer filter to look at
  one. Field names are translated to a shared vocabulary first, which is what
  makes the comparison meaningful: whatever each customer calls its invoice
  number, it lands on the same "Invoice number" row. **Stream** splits a customer
  that runs more than one document flow.
- The measure list is grouped by source, and the process list only offers
  processes nexora has actually onboarded — Octo's own internal process names
  are not reportable. If a process you expect is missing, it needs onboarding;
  it is not a display filter you can switch off.
- Two traps on that source. Use **"Extraction correct %"**, not "Extracted %":
  the latter only asks whether the machine put *anything* in the box, and
  everything Octo fills in automatically comes back fully extracted. And stay
  on **Field** rather than "Field (incl. unmapped)" or "Field (Octo raw
  name)": those two list all ~630 names Octo emits, 230 of which are internal
  bookkeeping pinned at the maximum, so a chart of them is just flat lines
  along the top and tells you nothing. "Field" is the ~20 fields nexora knows
  about, plus one empty bucket for the rest.
- A field with a **high "Avg. 2nd-candidate confidence %"** sitting close to its
  best-candidate confidence means the extractor was torn between two readings —
  usually a better thing to fix than a field that is simply never found.
- The palette button in the chart toolbar recolours each series and the
  title, and puts a series on its own right-hand axis — Backlog starts there
  by default so a few hundred stays readable next to tens of thousands. Picks
  are saved with the report.

**Checking a number**

- Click a chart bar or a table row to open the documents behind that number;
  the **Query** card beside the chart shows exactly how it was computed.
- Click the ↑/↓ chip on the total to see which processes or categories drove
  the change since the previous period.
- The ↑/↓ comparison chips compare a window shifted back by your range's
  length in days — not the previous calendar period. Hover a chip for the
  exact dates.
- Two people can see different totals on the same report: it always runs with
  the viewer's own data access.
- Charts cap at 50 axis values and 12 series — past the cap you get a partial
  chart or none at all; the table and exports always carry the full data.
- Need exact control the wizard can't give? **Advanced** in the left navigation
  opens the three-panel builder, and its **SQL** tab runs a read-only query
  when even that is not enough. A failed query names the reason from the
  database, and switching between **Table** and **SQL** clears the result so
  you never read the other mode's numbers.
- Fastest way to look inside a table: click its source card under **Sources**,
  expand the table, then **Query the first 100 rows**. The SQL tab opens on the
  right database with the query written and already run.

**Saving and sharing**

- Save writes back to the report you have open — the pencil beside the title
  renames it in place, and neither one leaves a duplicate behind. A result that
  is not a saved report yet (a wizard run, an answer from Eddard) asks for a
  name and lands under My reports. To keep the original untouched, use
  ⋯ → **Save as copy** (**Save as** in the Advanced builder).
- A scheduled email runs with the report owner's data access — recipients see
  the owner's numbers, not their own.
- Delete a report you own: open its card's **…** menu under My reports and
  pick Delete, or open the report and use ⋯ → Delete report. Shared copies and
  schedules go with it.

**Asking the AI**

- Name the measure, the time range and the processes: *"invoices by process,
  last 3 months"* beats *"show me invoices"*.
- Check what the AI built with **Open report** — the filters and process
  scope it chose are visible there before you trust the number.
- Follow-ups work: the chat remembers the conversation, so *"now only this
  quarter"* refines the last answer.
- When the AI used tools, unfold **How the agent worked** to see the steps; if
  a **Continue** button appears, click it before rephrasing your question.

> This section and the in-app panel (`templates/_reporting_help.html`) mirror
> each other — change both together.

---

## Finding your way around

The page is a small workspace with a fixed navigation on the left:

- **Library** — every report you can see, as cards: search, sort, and switch
  between 2 or 4 cards per row. This is the start screen.
- **Results** — brings back the **last result you rendered**, exactly as you
  left it, without running the report again.
- **Dashboards** — opens your most recent dashboard.
- **Scheduled** — every automatic delivery you own, in one table.
- **Advanced** — the full builder for exact control.

Under the navigation, the **Sources** list shows each data source you can
report on, with a green dot and its current response time.
Which sources you see depends on your permissions. Generali users typically get
the tenant's own tables here — **Documents**, **Attendance**, **Base Services**,
**Project Management**, **Reporting**, **CSV Imports** and **PDQM Report** — each a
flat table with dates, so "over time" breakdowns work.
In the Simple wizard's measure list they form one **Generali** block: Documents
(the same document feed the Generali dashboard charts — break it down by document
type, input channel, language, post-check…), Attendance, Base Services, Project
Management, Reporting and CSV Imports. Sydoc staff also see **Bucherer — EasyTax**
(imported and exported documents, pages) and **Frigemo — Documents** (daily
imported/exported documents and pages, deleted documents, invoices) and **Sydoc — Project Hours** (hours booked in
bpsuite by customer, project package, task and user) and **MediaMarkt — Batches**
(pieces scanned per batch, entered on the Sydoc tenant page). Clicking a source card in the rail opens its
database **structure**, not a report — start reports with **New report**.

**Click a source card** to look inside the database behind it (needs the
"browse source structure" permission — see [For administrators](#for-administrators-internal)):

- **List** — the tables this source actually reads, biggest first, with their
  row counts. Open one to see its columns, their types, which is the primary
  key (🔑) and which point at another table (🔗 — click it to jump there).
- **Diagram** — the same tables drawn as boxes, with a solid arrow from each
  foreign key to the table it references and a dashed one from a view to what
  it reads. Drag to pan, scroll to zoom, **Fit** to see everything again;
  clicking a box opens it in the list.

The rest of the database is left out: the header says how many tables were
hidden. "Used" means named by the source registry, plus whatever those tables
join to or a used view reads. And it is a read-only look at the structure —
no data rows are shown.

## Three ways to build a report

There are three ways in. They all produce the same kind of report; pick
whichever suits you.

| Way in | Where | Best for |
|---|---|---|
| **Guided builder** (wizard) | **New report** in the Library | Almost everyone, almost always. Four questions, no jargon. |
| **Ask Eddard** | **Eddard** button, top right | You know the question in words but not which fields to pick. |
| **Advanced builder** | **Advanced** in the left navigation | You want exact control: pick individual columns, several filters, custom sort, custom headers. |

You can start in one and move to another: any result has an **Open in Advanced**
entry in its **…** menu, and Eddard's answers have an **Open report** chip.

### Way 1 — the guided builder

**New report** walks you through four steps — the step chips across the top
show where you are, and the **So far** panel on the right collects your picks.
**Back** returns a step without losing your picks; **✕** leaves without
deleting anything you saved.

1. **What do you want to measure?**
   Pick one or more measures (e.g. *documents*). The first pick decides which
   data source you are in, so measures from other sources grey out until you
   clear the selection. Each measure you add becomes its own column, series and
   total in the result.

   **The imports / exports / backlog view:** pick *Documents imported*,
   *Documents exported* and *Backlog* together (or the *Pages …* variants),
   break down by *Date*, and you get one line per measure on a
   shared time axis — imports counted on their import date, exports on their
   export date, backlog as the point-in-time level. These "anchored" measures
   can't be mixed with the plain ones (the incompatible pills grey out).

2. **Which processes?**
   A checklist, everything ticked by default. Untick to narrow. This step is
   skipped for data sources that have no processes. Entries read
   `client.process` (e.g. `privera.03_Invoice_New`) — the same naming, and
   the same set of processes, you see everywhere else in the app (only
   processes you have access to are offered).

3. **Break it down by…**
   - *Time* — a date field such as **Import date** or **Export date**; pick a
     **Granularity** (Week / Month / Quarter / Year).
   - *Document fields* — the everyday ones: **Process**, Page Count, Document
     Type, Document Source, Creditor Name. **Show advanced fields** unfolds the
     rest (Owner no., Forwarding, raw Octo names, validation statuses …).
   - *None — just the total* — one big number, no chart.

   You can pick up to **three** breakdowns. The first one becomes the chart's
   horizontal axis; the rest become the coloured series (e.g. "Process ·
   Document Source").

4. **Time range**
   A preset (Today, This week, This month, Last month, Last 3 months, This
   quarter, Last quarter, This year, Last year, Last N days) or **Custom** with a
   date picker. Also choose the **Date field** — usually *import date* (when the
   document came in) or *export date* (when it left).

   **Presets are relative, and stay relative.** A report saved with "This month"
   shows *this* month every time it is opened or emailed — it does not freeze on
   the month you built it in.

Then **Show result**. To change something afterwards, hit **Adjust** — the
wizard reopens with all your answers still selected. The chips above the
result are editable too: clicking the **Processes** chip or any *is one of*
filter chip opens a checkbox picker of the known values — no typing needed.
Ticking everything simply removes the restriction.

#### About those "2/5" badges

Some measures and categories carry a small **coverage badge** like `2/5`, with a
progress bar. It means: *only 2 of the 5 processes actually provide this field.*
The two chip types count against different denominators: a **measure** badge
counts all processes you may access (you pick the measure before the process
step, and the badge does not recompute when you narrow the selection later); a
**category** badge counts the processes currently selected.

- Amber = partial coverage. Muted = low coverage (a third or less).
- Hover it to see which processes do provide it.
- Documents from the other processes land in the empty bucket — a partial
  measure only counts the documents of the processes that have it.

Chips that no selected process provides at all are hidden, and the rest sort
best-coverage-first. **If a number looks too low, check the badge first.**

### Way 2 — Ask Eddard

**Eddard** is the reporting assistant — the little black hole in the top bar,
who blinks at you while he waits and throws a report together while he works.
Click **Eddard** in the top-right and ask in plain words — *"documents per
month this year"*, *"invoices by process, last 3 months"* — or click one of
the starter chips in the empty panel. The answer arrives in the same panel.

- Answers where the agent used tools include a **How the agent worked** section
  you can unfold to see each step it took. If a **Continue** button appears
  under an answer, the agent ran out of budget mid-way — one click resumes it
  with more room; try that before rephrasing.
- If it built a report, an **Open report** chip opens it in the results view.
  **Use it.** The filters and process scope Eddard chose are visible there —
  a wrong guess (wrong date range, wrong process) shows up immediately, and
  you can adjust before trusting the number. From there, **Open in Advanced**
  reaches the builder if you need it.
- It remembers the conversation, so "…now only this quarter" works as a
  follow-up. Three follow-up chips are offered for you.
- The composer carries an **answer depth** control at its bottom-left, next
  to the send button — click it for **Quick**, **Balanced** (the default) or
  **Deep**. Quick trades deliberation for speed, right for a straight count
  you already know the shape of. Deep lets Eddard think longer before
  answering; use it when a question spans several sources or the first
  answer came back wrong. The control only appears when the configured
  assistant model supports it, so not every environment shows it.

Eddard does not get to bypass anything: he can only build a report you were
already allowed to run, and the report still runs through the normal path with
your own permissions.

If you do not see the **Eddard** button, the assistant is either not switched
on in your environment or not granted to your account.

### Way 3 — the Advanced builder

Three panels:

- **Left** — the data source, the process picker, and a searchable list of
  fields. Double-click or drag a field to add it as a column.
- **Middle** — your result, plus the report title, **Save** and **Export**.
- **Right** — **Columns** (order, and custom display headers), **Filters**,
  **Sort**, **Format** (title/subtitle).

Then **Run**.

Filters support: equals, not equals, is one of, is not one of, greater/less
than (and or-equal), between, contains, starts with, is empty, is not empty.
Date filters offer the same relative presets as the wizard.

Narrowing the process selection also **removes** any column, filter or sort on a
field none of the remaining processes provide — that is deliberate, the report
could not run otherwise.

---

## Reading the result

**The stat band** at the top. Every figure says what it is a figure *of*:

- One **total card per measure** — `Total · Documents imported`, then
  `Total · Documents exported`, and so on, one per measure you picked. There is
  no single number combining them: a document that was imported and later
  exported would be counted twice, so adding the two together would not be a
  count of anything real.
- A measure that is a **rate or an average** (an extraction-correct %, say) is
  not something you can add up, so its card is headed **`Overall · …`** and
  says *over every matching row* underneath. That figure is the real overall
  rate across every document behind the report — not the numbers in the chart
  added together, which for a percentage would give you something like 4,655%.
- Below them, **number of buckets, average and peak** for the first
  measure — the card says which one it is describing. A report with no
  breakdown (*just the total*) has no buckets, so these are not shown.
- **Buckets counts periods, not rows.** If you break down by a date *and*
  something else — per month *and* per field — each month contributes one row
  per field, so the table has many more rows than there are months. Buckets
  still counts the months. The average card then reads **`Avg per row`** and
  tells you how many values it averaged, because with a breakdown the average
  is across the cells of the table rather than across the periods.
- **Rows with no date are left out** of these figures, and the chart leaves
  them out too. If some of your documents have no export date they cannot sit
  in any month, so counting them would move every figure without appearing
  anywhere you can see. Eddard's summary tells you how many were set aside.

**Delta chips (↑ 12%)** appear on those cards when your report uses exactly one
relative date preset. They compare against the period *immediately before* the
one you are looking at.

Two things to know, because they surprise people:

- **It is not "last calendar month".** It shifts back by however many days your
  current window is long. A 31-day month shifted back 31 days does not land
  neatly on the 1st of a 30-day month. Hover the chip — the tooltip always shows
  the exact dates it compared against.
- **The arrow colour is direction only, never judgement.** Up is up. The chip
  does not know whether up is good news for your metric.

The **average** chip disappears when the two periods do not have the same number
of buckets — averaging across two different-length periods would invent a
percentage, so it is dropped rather than shown wrong.

**The chart** is a line for time breakdowns and bars for categories, with a
bar / line / pie / doughnut switcher (your choice is saved with the report).
There is a button to download the chart as a **PNG**. Charts show at most 50
values along the axis and 12 series (the 12 largest are kept). Past 50 axis
values the two builders differ: Advanced charts the top 50 by value with a note;
the guided view charts the first 50 for a category axis, and for a date axis (or a
result with several breakdowns) shows no chart at all with a hint to pick a
coarser granularity or a shorter range. The table and exports always carry the
full data.

The data rows show under the chart; **Hide table** collapses them. The **Query** card beside the chart
always shows the actual database query behind the number, formatted and
copyable — useful when you want to prove where a figure came from.

### Today, unfinished periods and gaps

- A time chart **stops at today**. *This year* draws January up to the current
  month — the months that haven't happened yet are not drawn as zero, and the
  *Groups* / *Ø per group* cards only count the periods that exist.
- The period that contains today is **still filling up**: its bar is faded (its
  line segment dashed) and the note *"The current period is still running"*
  appears under the chart. Don't read it as a drop.
- **Backlog is a level, not a count.** Its *Total* is the newest snapshot, never
  the sum of all snapshots. A period nobody measured shows as a **gap** in the
  line (not zero) with the note *"Gaps are periods without a backlog snapshot"*.
- A weekly or daily breakdown of a whole year charts fine — the 50-point cut
  only applies to category axes.

### Forecast

If your report is *one time breakdown plus a measure*, the **Forecast** toggle
becomes available. (In the guided view the toggle is always visible in the chart
toolbar but greyed out until the report qualifies; Advanced hides it instead.)
On a line chart it extends the chart with a dashed projection line and a shaded
95% confidence band; on a bar chart the predicted periods are drawn as
translucent bars in the series' colour. Pie and doughnut charts have no
forecast. The predicted rows are appended to the table with a *Forecast* badge,
and switching the forecast off again is instant — nothing is re-queried.

- It fits a trend and, when there is enough history, a repeating seasonal
  pattern on top. The unfinished current period is left out of the fit (it
  stays on the chart as-is) and the projection starts right after it; a
  backlog's unmeasured periods are carried forward, not counted as empty.
- It needs at least 5 periods of history. Below that you get *"Not enough
  history to forecast this series."*
- The setting is saved with the report — including for scheduled emails.
- Exports get an extra **Forecast** column so you can tell predicted rows from
  real ones. Predicted points are not clickable — there are no real documents
  behind a number the system invented.

### Colours & axes

The palette button in the chart toolbar opens a small panel with a colour
picker for every series and one for the **report title and legend**. Each
series also has a **Left | Right** switch: put it on *Right* to plot that line
against its own scale on the right-hand side — the way to keep a *Backlog* of a
few hundred readable next to imports in the tens of thousands (when *Backlog*
shares a chart with other measures it starts on the right axis by default).
Each axis is titled with the series it carries, and when it carries exactly one
series its numbers take that series' colour. **Reset colours** returns to the
standard palette.

- Your picks are saved with the report and come back when you open it.
- Emailed reports and the Advanced builder use the standard colours.

### Click a bar to see the documents behind it

On any report that has a measure *and* a breakdown, **clicking a chart bar/point
or a table row** opens a drawer listing the actual documents that make up that
number. A hint line tells you when this is available.

- Shows up to **100 rows**. The drawer's CSV / Excel export is currently capped
  at the same 100 rows — for the full set, narrow the bucket or run the
  underlying rows as their own report.
- Workitem numbers are links — click to open the document detail panel over the
  drawer, or Ctrl-click to open it in a new Workitems tab.
- Not available on: plain row lists with no measure, the single big-number card,
  pivot cells, and hand-written SQL results.
- On a distinct-count measure, the drawer says so: you may see more rows than
  the number, because the same value can appear on several rows.

### Click the arrow on the total to see what drove the change

When a report with a time preset shows a small **↑ / ↓ percentage** next to its
total, that chip is a button. Click it and a panel explains the change: one
tab per breakdown (process first, then the source's other categories), each
listing which values moved the number most, with the previous and current
figure, the change, and its share of the total change.

- Click a row to jump to the documents behind that value.
- "(other)" gathers everything outside the top eight.
- Averages and distinct counts show the change but no share — a share of an
  average has no meaning.

---

## Saving, sharing, finding again

**Save** writes back to the report you have open — yours, or a shared one you
have edit rights on (in which case everyone sees the change). The pencil beside
the title renames that same report; neither leaves a duplicate behind. A result
that is not a saved report yet — a wizard run, an answer from Eddard — asks for
a name instead and lands under **My reports**.

To keep the original as it was, make a copy: ⋯ → **Save as copy** in the
results view, **Save as** in the Advanced builder. The copy becomes the report
you have open, so the next Save goes to the copy, not the original.

The **Library** groups everything into three shelves:

- **Library** — reports shared with the whole organisation.
- **My reports** — yours.
- **Shared with me** — reports someone shared with you by name.

Above the shelves: a **search box**, a **sort** dropdown (recently updated /
name), and a layout toggle for **2 or 4 cards per row**. Every card you own has
a **…** menu with **Share** and **Delete**; clicking anywhere else on the card
opens the report.

Cards show a small preview chart. It only reflects your real numbers after you
have opened and run that report in this browser — before that it is a
decorative placeholder, so don't read trends off a card you haven't opened.
A dashboard card previews the dashboard itself: a miniature of its real card
layout (one tile per card), plus a card count. Nothing runs until you click a
card.

**Share** (on a report you own) does two independent things:

- **Visibility** — *private* (only you) or *shared* (readable by everyone who
  can open the Reporting page).
- **Named shares** — share with specific colleagues, optionally with **Can
  edit**.

Once a report of yours is shared either way, its card and its entry in the
Advanced dropdown are tagged **· shared**. A named share does not move the card
to the **Library** shelf — that shelf is only for reports shared with the whole
organisation.

Only the owner can change visibility, manage shares, rename or delete. Someone
with a read-only share who edits and saves gets their own copy instead.

> **Two people can open the same shared report and see different numbers.** That
> is correct, not a bug: a report always runs with the *viewer's* own data
> access. Someone who cannot see a process simply does not get its rows.

---

## Exporting

Pick **Excel** or **CSV** next to the **Export** button. What you get depends on
what you are looking at:

- **Table/grid view** → the data rows. Excel includes a title block (report
  title, source, timestamp), a frozen header row, and — if a chart is on screen
  — the chart image above the table. CSV is data rows only.
- **Pivot view** → the pivot matrix as displayed.
- **Chart view** → a PNG image of the chart.

---

## Getting it by email

The **Scheduled** page (left navigation) lists every automatic delivery you
own, across all your reports: what runs, how often, who gets it, in which
format, when it last ran and when it runs next. From there:

- The **toggle** at the start of each row switches a schedule on or off —
  switched-off rows stay in the list, dimmed.
- **New schedule** opens a small form: pick one of your saved reports, a
  **frequency** (daily / weekly / monthly), a **time** (UTC — mind the
  offset), a **format** (Excel / CSV) and the **recipients**.
- The bin icon at the end of a row deletes that schedule.

Reports with a breakdown get the chart drawn into the mail body and into the
attached file.

**Alert-only schedules.** The **Send** dropdown can turn a schedule into an
alert: *only when the total is above / at least / below / at most N*. If the
condition is not met, no mail goes out that run. For reports without a measure,
the threshold compares against the number of rows.

The schedule runs the report **as its owner**, with the owner's data access —
not the recipients'.

---

## Report definitions

A **report definition** is a saved bundle of measures and a tile layout that
a report can render its result through, instead of the usual chart + table.
It is the reporting equivalent of a template: build it once, then pick it for
any report where you want that shape.

**Creating one.** Open **Report definitions** in the left navigation, then
**New definition**:

- **Add a measure** for each number you want, then pick what it computes (see
  the six measures below).
- **Add a tile** — a KPI tile (one measure, optionally with a small
  sparkline), a chart (bar, stacked bar, line, area, pie, doughnut or gauge)
  or a table.
- **Drag** tiles to arrange them and **resize** by their corner grip, the same
  way a dashboard card works.
- **Done** saves it.

**The six measures, in plain words:**

| Measure | Shows |
|---|---|
| Current | The latest value — for a report broken down by time, the most recent bucket; otherwise the total. |
| Mean | The average across every bucket. |
| Min / max | The smallest and largest values seen. |
| Range | The gap between the smallest and the largest. |
| Standard deviation | How spread out the values are around the average. |
| Percentile | The value below which a chosen percentage of the data falls (e.g. the 90th percentile). |

**Using one.** Pick a report definition at the top of the guided builder, or
next to **Saved reports** in the Advanced builder — do this before you run,
same as picking a source. Running the report then draws your tiles instead of
the standard chart and table. Pick **Standard** to go back to the usual view.

**It is private.** A report definition you create is yours alone — sharing a
report that uses one does not share the definition with the recipient; they
just see the standard view instead.

**If you delete one**, every report that was using it quietly falls back to
the standard view next time it runs — nothing else breaks.

**Exporting** a report that uses a definition adds a small **Measures**
block underneath the data in the Excel/CSV file, listing each measure and its
value.

---

## Dashboards

**New dashboard** builds a page of live cards out of your saved reports. A
card is a **piece of a report** — one KPI tile, the chart, the table, or the
whole report — shown exactly as the report itself shows it. Change the report
and every card built from it follows.

- A dashboard takes the **whole width of the window** — the workspace rail
  slides away while it is open and comes back when you return to the Library.
  **Present** shows it fullscreen for a wall screen or a meeting (Esc leaves).
- **Edit / Done** toggles edit mode: drag cards to rearrange or resize them,
  add, duplicate or remove them, and set the **global filters**.
- **Add a card** (header button, or the dashed tile at the end of the grid):
  pick one of your saved reports and it opens in front of you, complete —
  the KPI band, the chart, the table. Hover a KPI tile or the chart and click
  **Add to dashboard**; the table has its own button; **Add whole report** in
  the header takes everything. Take as many pieces as you like, then close.
  Each card lands at a sensible size, ready to move or resize.
- **Moving and resizing.** In edit mode a card is grabbable anywhere: drag it
  and the grid reflows live — the other cards slide out of the way and the
  dashed outline shows where it will land.
  Drag the little corner grip at its bottom right to resize — the width snaps
  to the 12 columns of the grid, the height to whole rows (up to 6). Both are
  saved with the dashboard on **Done**.
- **The Results tab's chart tools, per card.** In edit mode every card that
  shows a chart carries the same small toolbar the Results tab has: chart
  type (bar, line, stacked, pie, doughnut), download as image, **Forecast**
  with its horizon, and **Colours & axes** (a colour per series, left/right
  axis, reset). Changes apply to *this card only* and are saved with the
  dashboard on **Done** — the report itself is untouched, so the same report
  can be a bar chart on one card and a forecast line on another. In view mode
  the toolbar is hidden. Forecast needs a report with exactly one date
  breakdown (same rule as the Results tab); on other reports the button is
  greyed out and clicking it tells you why.
- **A whole-report card looks like the report.** KPI strip on top, full-width
  chart, table behind *Show table*, and the card grows with its content instead
  of clipping.
- **Global filters are the reports' own filters.** The bar shows one chip per
  field your cards' reports already filter on — *Date · This month*,
  *Processes · All processes*, *Status · open* — with the value the reports
  use ("mixed" if they disagree). Click a chip to change it: a date chip
  offers the usual presets (this / last month, quarter, year …) or a custom
  range, a list chip a checkbox picker. The new value replaces the reports'
  own on every card; the chip turns coloured and its ↺ goes back to what the
  reports say. The small "+" adds a filter on a field no report uses. A card
  can still override a field — it shows "This card overrides the global
  filters".
- KPI cards carry the same "vs previous period" chip the report's own KPI band
  shows.
- Cards drill through exactly like a normal report — click a chart element or
  a table row and the document drawer opens.
- **Export** is per card: the header menu lists the cards, pick one.
- A card whose report was deleted says so. Cards from dashboards built before
  this version show a note asking you to remove them and add the piece again.

A dashboard saves, shares and deletes exactly like any other report.

---

## Why does my number look wrong?

| Symptom | Likely cause |
|---|---|
| Number lower than expected | A measure or category with a partial coverage badge (`2/5`) — the other processes contribute nothing to it. |
| A colleague sees a different total | Correct behaviour. Reports run with the viewer's own data access. |
| "Showing the first N rows…" | The result hit the row cap. Narrow the filters or the time range. |
| The comparison chip looks off by a few days | The comparison shifts by day count, not calendar period. Hover it for the exact dates compared. |
| The average delta chip vanished | The two periods have different bucket counts, so the percentage would be fabricated. Total and peak are still valid. |
| Everything lands in one empty bucket | The breakdown field is not filled in for the processes you selected. |
| The saved report shows a different month than when I built it | Working as intended — relative presets re-resolve on every run. |
| Scheduled mail arrives at an odd hour | Schedule times are **UTC**. |
| Chart says it is showing the top 50 | Charts cap at 50 axis values and 12 series. Filter down, or use the table/export. |
| The line chart shows no empty months | Zero-months only appear for a single date breakdown with a bounded time range. With a second breakdown or "All time", empty periods drop off the axis entirely. |
| A button is missing entirely | It is permission-gated. See below. |

---

## Words used on the page

| Word | Means |
|---|---|
| **Measure** | The thing being counted or summed — e.g. documents. |
| **Breakdown / dimension** | What splits the number up — per month, per process, per document type. |
| **Granularity / grain** | How wide a time bucket is: week, month, quarter, year. |
| **Process** | One configured document workflow. In this deployment each one corresponds to a client, so "per process" reads as "per client". |
| **Source** | Which body of data the report reads from. Most reports use *Document Processing*. |
| **Scope** | The processes a report is allowed to include. |
| **Bucket** | One bar/point of the chart — one month, one category, … |
| **Drill-through** | Clicking a number to see the individual documents behind it. |
| **Report definition** | A saved bundle of measures and a tile layout a report can render its result through, in place of the standard chart + table. |
| **Measure (definition)** | One computed number inside a report definition — current, mean, min/max, range, standard deviation or percentile. |

---

## If something is greyed out or missing

Reporting is permission-gated feature by feature, so two people can see two
different pages. Ask an administrator to grant what you need:

| You cannot… | Ask for |
|---|---|
| Open the page at all | Reporting page access |
| See a particular data source | Access to that source |
| Export to Excel/CSV | Export permission |
| See a client or process in the picker | Row scope for that process |
| Ask Eddard | AI assistant access |
| Set up email delivery | Scheduling permission |
| Write your own SQL | SQL sandbox access (below) |
| Click a source card to see its tables | Browse source structure (`reporting.sources.schema.view`) |

---

## For administrators (internal)

Everything above is for anyone using the page. The rest is for people who
administer it.

**Data sources** (`/reporting/sources`) — the registry of what the source
selector offers. Add or retire a source here; no code change needed for a
table-shaped source.

**Measures** (`/reporting/metrics`) — the list the wizard's first step offers.
Adding a row here widens the guided builder for everyone, without a release.

**Source structure** — `reporting.sources.schema.view` turns the Sources rail cards
into buttons that open the tables, columns and foreign keys of the database
behind a source. It reads structure only (no rows), on the same connection the
source already uses, and still requires the source's own permission — so it
widens *what you see of* a database, never *which* databases you reach.

**Live SQL sandbox** — the **SQL** tab in the Advanced builder, for when the
builder cannot express the query. It runs a single read-only `SELECT` against a
chosen database. The **Target** picker names the real databases — the same names
as the Sources rail cards (`SYDOC_Statistik`, `RuntimeDatabase`, `Generali`) —
with `SYDOC_Statistik` on the base permission and each other database behind its
own extra grant. The nexora database itself is not a target: it holds the
password hashes. A quicker way in: open a source's **Structure**, expand a table,
and press **Query the first 100 rows** — it drops you into the SQL tab with
`SELECT TOP (100) * FROM …` already written and run. Guard rails: the statement
is parsed and rejected unless it is a single `SELECT`, it runs on a read-only
login, results cap at 50,000 rows,
statements time out at ~30 seconds, and every run is audited. First use requires
a one-time acknowledgement. When a query fails, the reason from the database
("Invalid object name 'Workitem'.") is shown under the error. Switching between
**Table** and **SQL** clears the result area, so you never look at the other
mode's rows or query.

Setup, permission codes, endpoints, database schema and everything else
technical: [`reporting.md`](reporting.md).

---

## See also

- [`reporting.md`](reporting.md) — the developer/architecture reference.
- [`../design/reporting-ai-assistant.md`](../design/reporting-ai-assistant.md) —
  how the AI assistant is designed.
