## Overview
Eddard is Nexora's mascot — a small black-hole character (black core body, indigo accretion-ring "smile", two dot eyes). This handoff covers **only the newest piece: Eddard's "building a report" animation** (design reference labeled **8a** in the bundled prototype). It is a looping, state-driven sequence where Eddard flings report content out of his core onto a live report card, celebrates, then resets — cycling through **three distinct report variants** built from Nexora's real reporting measures: **Backlog, Documents Imported, Documents Exported, Document Field Extraction**.

The mascot's idle personality loop (turn 7a) and the earlier concept explorations are **not** part of this handoff — this package is scoped to the report-building animation only.

## About the Design Files
The bundled HTML file is a **design reference** built with inline styles and CSS keyframes in a browser prototyping tool — it is not production code to copy verbatim. Recreate this animation in the target codebase's existing environment (React, Vue, SwiftUI, native, etc.) using its established component and animation patterns. If no environment exists yet, pick the framework best suited to the project.

## Fidelity
**High-fidelity.** Colors, sizes, timings, and easing curves below are final and should be matched closely. The report card mockup UI (numbers, table rows, chart shapes) is illustrative sample data — wire it to real values in the target app.

## Behavior overview
A repeating cycle, driven by two independent timers:

1. **Build step** (`0–5`, advances every **1300ms**): controls what's visible on the report card.
   - `0` — empty state (dashed placeholder, "Empty report")
   - `1` — title card flies in
   - `2` — second content piece flies in
   - `3` — third content piece flies in
   - `4` — fourth content piece flies in
   - `5` — "Ready" badge pops in (card stays fully built)
   - Then wraps back to `0` (card clears) **and advances to the next report variant**.
2. **Report variant** (`0, 1, 2`, advances each time the build step wraps from `5`→`0`): selects which of the three report layouts plays next. Cycles in order and repeats.

Eddard's body reacts throughout: while building (`step` 1–4) he leans in (`rotate(6deg)`) with his eyes shifted toward the card (`translate(7px, 1px)`) and his core softly pulses/glows (box-shadow emit). On the "Ready" step he leans back and scales up slightly (`translateY(-14px) scale(1.06)`), eyes widen (`scale(1.15)`). At idle (step 0) he returns to neutral.

A status row below the card shows a colored dot + label reflecting the current step (see per-variant copy below); the dot pulses while building and turns green on "Ready".

## The three report variants

### Variant 1 — "Documents imported" (KPI report)
| Step | Content | Motion |
|---|---|---|
| 1 | Title row: small accent-color square icon + "Documents imported" + a placeholder subtitle bar | Flies in from lower-left, tumbling slightly, settling with overshoot (see **edToss** below) |
| 2 | Big KPI number "3,482" + green "▲ 8.3%" delta, baseline-aligned | Same fly-in-from-lower-left motion |
| 3 | Caption "DOCUMENTS EXPORTED · LAST 6 WEEKS" (uppercase, small, muted) above a 6-bar bar chart (heights 34/52/26/44/58/38px, alternating tint/full accent color, 16px wide, 8px gap) | Bars grow upward from baseline, staggered 0.15s→0.65s in 0.1s steps |
| 4 | Caption "BACKLOG TREND" above a 7-point line chart trending downward-right (values improving = backlog shrinking) | Line draws left-to-right via stroke-dashoffset |
| 5 | "Ready" badge, top-right of card | Pops in with overshoot |

Status labels per step: Idle → "Adding title…" → "Counting imports…" → "Charting exports…" → "Tracking backlog…" → "Report ready"

### Variant 2 — "Pipeline measures" (table + donut)
| Step | Content | Motion |
|---|---|---|
| 1 | Title row: icon + "Pipeline measures" + subtitle bar | Flies in from directly above, dropping into place |
| 2 | Two table rows: "Backlog — 214" and "Documents imported — 3,482", each a space-between flex row with a bottom divider | Drop in from above, staggered 0.05s / 0.15s |
| 3 | Two more rows: "Documents exported — 3,190" and a bold total-style row "Field extraction — 96.4%" (accent-colored value, no divider on last row) | Same drop-in motion, staggered |
| 4 | Small donut chart (52px, accent stroke over a light-gray track, ~53% sweep) + a 2-line legend: "● Extracted 96%" / "○ Pending 4%" | Pops in with overshoot; donut ring draws via stroke-dashoffset |
| 5 | "Ready" badge | Same as variant 1 |

Status labels: Idle → "Adding title…" → "Logging backlog & imports…" → "Logging exports & extraction…" → "Charting extraction…" → "Report ready"

### Variant 3 — "Weekly digest" (big number + progress + sparkline)
| Step | Content | Motion |
|---|---|---|
| 1 | Title row: icon + "Weekly digest" + subtitle bar | Flies in from the right, tumbling slightly |
| 2 | Big number "214" + muted label "documents in backlog" | Same fly-in-from-right motion |
| 3 | Three labeled horizontal progress bars: "Imported" 82%, "Exported" 54%, "Field extraction" 96% (6px tall tracks, accent fill) | Fill bars grow left-to-right (scaleX), staggered 0.05s/0.15s/0.25s |
| 4 | Caption "BACKLOG, WEEK OVER WEEK" above a small 7-point sparkline (trending down/improving) | Flies in from the right; line draws via stroke-dashoffset |
| 5 | "Ready" badge | Same as variant 1 |

Status labels: Idle → "Adding title…" → "Counting backlog…" → "Tracking imports & exports…" → "Plotting backlog trend…" → "Report ready"

## Animation reference (keyframes)
Timings/easings to reproduce exactly (durations in the target framework's animation/transition system):

- **edToss** (fly in from lower-left, used in Variant 1): `translate(-180px, 24px) scale(.3) rotate(-22deg)` opacity 0 → 55% opacity 1 → 72% overshoot `translate(6px,-5px) scale(1.06) rotate(4deg)` → settle at `translate(0,0) scale(1) rotate(0)`. Duration 0.7s, `cubic-bezier(.34,1.4,.6,1)`.
- **edTossTop** (drop from above, Variant 2 rows/title): `translateY(-58px) scale(.55)` opacity 0 → 55% opacity 1 → 72% overshoot `translateY(4px) scale(1.05)` → settle. Duration 0.7s title / 0.55s rows, same easing curve as edToss.
- **edTossR** (fly in from right, Variant 3): `translate(150px,10px) scale(.4) rotate(10deg)` opacity 0 → 55% opacity 1 → 72% overshoot `translate(-4px,-3px) scale(1.06) rotate(-2deg)` → settle. Duration 0.7s, same easing curve.
- **edGrow** (bar chart growth): `scaleY(0)` → `scaleY(1)`, transform-origin bottom, 0.5s ease-out, staggered per bar.
- **edGrowX** (horizontal progress fill): `scaleX(0)` → `scaleX(1)`, transform-origin left, 0.5s ease-out, staggered per row.
- **edDraw** (line chart, 260-wide viewBox): stroke-dashoffset 240 → 0, 0.9s ease-out (dasharray fixed at 240 to match path length).
- **edDraw100** (donut ring + sparkline, uses `pathLength="100"` so it's viewBox-size-independent): stroke-dashoffset 100 → 0, 0.8–0.9s ease-out.
- **edBadge** (Ready badge, donut pop-in): `scale(0)` opacity 0 → 60% overshoot `scale(1.15)` opacity 1 → settle `scale(1)`. Duration 0.5s, `cubic-bezier(.34,1.56,.64,1)`.
- **edEmit** (Eddard's core glow while building): box-shadow pulses between none and `0 0 22px 6px` of the accent color at 45% opacity, 1.3s ease-in-out loop.
- Eddard's body/eye lean transitions use `cubic-bezier(.34,1.56,.64,1)`, 0.4–0.5s.

## Design tokens
- Accent color: driven by a single CSS variable (`--acc`, sample value `#4f46e5`) and a light tint (`--acc-tint`, sample `#edf0ff`) — every colored element in this animation derives from these two so it follows the app's theme setting. Never hardcode the indigo.
- Body font: Inter, weights 400–800.
- Text colors: near-black `#101623` for primary values/labels, muted gray `#57617a` for secondary text, lighter gray `#8a93a6` for uppercase captions and idle-state text.
- Success green (used only for the "Ready" badge and the KPI delta): background `#eafaf1`, border `#bfe8cf`, icon fill `#18a45e`, text `#127a46`.
- Card surface: white, `1px solid #e2e5ea` border, `12px` radius, `0 8px 24px rgba(16,22,35,.10)` shadow.
- Report-card canvas background: `radial-gradient(120% 120% at 30% 36%, #f2f3ff, var(--acc-tint))`, `14px` radius.
- Spacing: card padding 16px; content pieces stack with ~10–14px top margin between them; table rows use 6–7px vertical padding with a `1px solid #eef0f3` divider (omitted on the last/total row).
- Type scale used here: 30–34px/800 for KPI and big numbers, 13px/700 for titles, 12px for body/table text, 11px for legend/status text, 10px/700 uppercase with 0.04em tracking for chart captions, 9px/700 uppercase for the "Live" tag.

## Assets
No image assets — everything is inline SVG (Eddard's face/ring) and CSS/DOM shapes (cards, bars, badges). No icon font or emoji used.

## Files
- `Eddard - Options.dc.html` — full prototype file. The relevant section is the block commented `<!-- ============ TURN 8 — Eddard at work ============ -->` near the top of the file, plus the `Component` class's `build`/`script` state and `renderVals()` logic at the bottom (booleans like `showTitleR/showKpi/showBars/showLine`, `showTitleT/showRows1/showRows2/showDonut`, `showTitleD/showBigNum/showProgress/showSpark`, `showDone`, `showEmpty`, and the `workLabel`/`workColor`/`workBodyT`/`workEyesT`/`workEmit` mascot-reaction values). Everything else in that file (turns 1–7) is unrelated prior exploration and out of scope for this handoff.
