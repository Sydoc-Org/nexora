# Handoff: Eddard — the Nexora reporting mascot

## Overview
Eddard is the mascot/assistant character for Nexora's Reporting product. He is a
friendly, animated version of the **Nexora house logo — a black hole**: a black
"event horizon" core as the body, an indigo accretion ring wrapping around it like
Saturn, and two simple white dot eyes. No mouth. He is used as a lively presence in
the reporting UI (empty states, the report-builder, loading/working indicators).

Two behaviors are specified here:
- **Idle / personality loop** (prototype card `7a`): Eddard floats, looks around,
  blinks, winks, hops with squash-and-stretch, and does a wide-eyed surprise.
- **"Eddard builds a report"** (prototype card `8a`): he flings each report piece
  out of his core onto a page (title → KPI → bar chart → trend line), pops a green
  "Ready" badge, then clears back to idle.

## About the design files
The file in this bundle (`Eddard - Options.dc.html`) is a **design reference created
in HTML** — a prototype showing the intended look and motion, not production code to
copy directly. It is authored in a small internal component format (a `.dc.html` with
an inline template + a `class Component` logic block); **do not** try to run that
format in the target app.

The task is to **recreate this mascot in the Nexora codebase's existing environment**
using its established patterns. The Nexora front end renders the logo today with plain
HTML + CSS (`static/css/_nexoraLogo.css`, layered `<div>`s), so the natural fit is an
inline **SVG component** (React/Vue/whatever the app uses) with CSS keyframes, plus a
tiny state machine for the action loops. If you prefer, the static mark can stay as the
existing CSS logo; this handoff only adds the *animated mascot* treatment.

## Fidelity
**High-fidelity.** Exact geometry, colors, keyframes, timings, and state sequences are
given below. Recreate it precisely, but wire the **accent color to the app's existing
accent token** (see Design Tokens) rather than hardcoding indigo.

## The mascot mark (geometry)

Draw in an SVG with `viewBox="0 0 200 200"`, `fill="none"`. Layer order matters
(back ring → body → eyes → front ring) so the ring reads as passing behind and in
front of the body:

1. **Back half of ring** (behind body):
   `<path d="M24 116 A76 22 0 0 1 176 116" stroke="<accent-soft>" stroke-width="9" stroke-linecap="round"/>`
2. **Body group** (this group receives the animated transform — see below):
   - Core: `<circle cx="100" cy="98" r="52" fill="#0a0a12"/>`
   - Rim: `<circle cx="100" cy="98" r="52" stroke="<accent>" stroke-width="3"/>`
   - **Eyes** (nested groups so shift / blink / wink compose):
     - shift group (looks around): transform per state
       - blink group (`animation: edBlink`)
         - left eye wink wrapper (transform per state): `<circle cx="84" cy="90" r="7.5" fill="#fff"/>`
         - right eye: `<circle cx="116" cy="90" r="7.5" fill="#fff"/>`
     - All eye groups use `transform-box: fill-box; transform-origin: center;`
3. **Front half of ring** (in front of body's lower edge):
   `<path d="M24 116 A76 22 0 0 0 176 116" stroke="<accent>" stroke-width="10" stroke-linecap="round"/>`
   with `transform-box: fill-box; transform-origin: center; animation: edRingWob 4s ease-in-out infinite;`

The whole SVG sits inside a wrapper div with `animation: edFloat 4.5s ease-in-out infinite`
for the ambient hover.

Small-size lockup (nav / 24px): same layers simplified — ring arcs `A16 5`, core `r10`,
eyes `r1.7`.

## Design tokens

| Token | Value | Notes |
|---|---|---|
| Core / body | `#0a0a12` | The black hole — stays black in light AND dark theme (intentional). |
| Accent | `var(--acc)` → default `#4f46e5` | **Wire to the app's accent token** (`--nx-accent`). Ring rim, front ring, bars, line. |
| Accent soft | `color-mix(in srgb, var(--acc) 55%, #fff)` | Back ring, lighter bars, drifting sparks. |
| Accent tint | `#edf0ff` (`--acc-tint`) | Chip backgrounds, stage gradient. |
| Eyes | `#fff` | Simple solid dots, no sclera/pupil, no highlight. |
| Success | `#18a45e` (bg `#eafaf1`, border `#bfe8cf`, text `#127a46`) | "Ready" badge, positive delta. |
| Ink | `#101623` | Report title / KPI number. |
| Muted | `#8a93a6` | Idle status dot. |
| Neutral border | `#e2e5ea`; placeholder `#eef0f3` | Cards, empty-state dashes. |
| Stage bg | `radial-gradient(120% 120% at 50% 38%, #f2f3ff, var(--acc-tint))` | Behind the mascot. |
| Font | `Inter`, weights 400–800 | Matches Nexora. |

The Nexora logo CSS already re-tints the accent per `html[data-accent]` / dark mode
(`--nx-accent`, `--nx-violet`); reuse those variables so Eddard follows the user's
accent picker automatically. Keep the core black in both themes.

## Keyframes (exact)

```css
@keyframes edFloat  { 0%,100% { transform: translateY(0)   rotate(-2deg); } 50% { transform: translateY(-9px) rotate(2deg); } }
@keyframes edBlink  { 0%,92%,100% { transform: scaleY(1); } 96% { transform: scaleY(.1); } }        /* on eyes group */
@keyframes edRingWob{ 0%,100% { transform: scaleX(1); } 50% { transform: scaleX(1.05); } }           /* on front ring */
@keyframes edDrift1 { 0%,100% { transform: translate(0,0);   opacity:.5; } 50% { transform: translate(10px,-14px);  opacity:1; } }
@keyframes edDrift2 { 0%,100% { transform: translate(0,0);   opacity:.4; } 50% { transform: translate(-12px,10px);  opacity:.9; } }

/* report-builder (8a) */
@keyframes edToss  { 0% { transform: translate(-180px,24px) scale(.3) rotate(-22deg); opacity:0; } 55% { opacity:1; } 72% { transform: translate(6px,-5px) scale(1.06) rotate(4deg); } 100% { transform: translate(0,0) scale(1) rotate(0); opacity:1; } }
@keyframes edGrow  { from { transform: scaleY(0); } to { transform: scaleY(1); } }                   /* bars, transform-origin:bottom */
@keyframes edDraw  { from { stroke-dashoffset:240; } to { stroke-dashoffset:0; } }                    /* trend line, stroke-dasharray:240 */
@keyframes edBadge { 0% { transform: scale(0); opacity:0; } 60% { transform: scale(1.15); opacity:1; } 100% { transform: scale(1); opacity:1; } }
@keyframes edEmit  { 0%,100% { box-shadow: 0 0 0 0 transparent; } 50% { box-shadow: 0 0 22px 6px color-mix(in srgb, var(--acc) 45%, transparent); } }
@keyframes edThink { 0% { opacity:.2; } 50% { opacity:1; } 100% { opacity:.2; } }                     /* status dot while working */
@keyframes edOrbit { from { transform: rotate(0); } to { transform: rotate(360deg); } }              /* optional orbiting spark */
```

All animated SVG sub-groups need `transform-box: fill-box; transform-origin: center;`
(bars use `transform-origin: bottom`). State-driven transforms use a CSS transition
`transform .4–.55s cubic-bezier(.34,1.56,.64,1)` for the springy feel.

## Behavior 1 — Idle / personality loop (card `7a`)

A mood index cycles on a fixed sequence; each mood sets three transforms that animate
via the spring transition. Blink and float run continuously underneath.

- **Timer:** advance every **1450 ms** through the sequence
  `[0, 1, 0, 2, 3, 0, 4, 5, 0, 1, 4, 0]` (indexes into the mood table).
- **Mood table** (ex/ey = eye shift px, es = eye scale, wy = left-eye scaleY for wink,
  hop = body translateY px, sx/sy = body scale):

| # | Mood | ex | ey | es | wy | hop | sx | sy |
|---|------|----|----|----|----|-----|----|----|
| 0 | idle        | 0  | 0  | 1    | 1    | 0   | 1    | 1    |
| 1 | look left   | -8 | 1  | 1    | 1    | 0   | 1    | 1    |
| 2 | look right  | 8  | 1  | 1    | 1    | 0   | 1    | 1    |
| 3 | wink        | 3  | 0  | 1    | 0.08 | 0   | 1.03 | 1    |
| 4 | happy hop   | 0  | 0  | 1    | 1    | -16 | 1.06 | 0.9  |
| 5 | surprise    | 0  | -4 | 1.42 | 1    | -9  | 0.92 | 1.12 |

Apply:
- Body group: `transform: translateY(<hop>px) scale(<sx>,<sy>)` (origin center bottom).
- Eye-shift group: `transform: translate(<ex>px,<ey>px) scale(<es>)`.
- Left-eye wink wrapper: `transform: scaleY(<wy>)` (transition `.16s ease`).

Ambient extras: 3 small drifting spark dots around him (`edDrift1`/`edDrift2`,
durations 4–6 s, staggered delays), accent-soft / accent colors.

## Behavior 2 — "Eddard builds a report" (card `8a`)

Layout: horizontal row — mascot on the left (~164px), a white report card on the right
(flex:1, `border:1px solid #e2e5ea; border-radius:12px; box-shadow:0 8px 24px rgba(16,22,35,.10); padding:16px`)
on the stage gradient. A status pill sits below.

- **Timer:** `build` counter cycles **0→5**, advancing every **1300 ms**, then wraps to 0 (clears).
- **Reveal thresholds** (each piece is mounted when true; it plays its entrance
  animation once on mount):

| build | Status label | Empty | Title | KPI | Bars | Line | Done badge | Mascot |
|------:|--------------|:--:|:--:|:--:|:--:|:--:|:--:|--------|
| 0 | Idle             | ✓ | | | | | | upright, eyes center |
| 1 | Adding title…    | | ✓ | | | | | lean `rotate(6deg)`, eyes `translate(7px,1px)`, core `edEmit` glow |
| 2 | Adding metrics…  | | ✓ | ✓ | | | | lean + glow |
| 3 | Charting data…   | | ✓ | ✓ | ✓ | | | lean + glow |
| 4 | Drawing trend…   | | ✓ | ✓ | ✓ | ✓ | | lean + glow |
| 5 | Report ready     | | ✓ | ✓ | ✓ | ✓ | ✓ | `translateY(-14px) scale(1.06)`, eyes `translate(0,-2px) scale(1.15)` |

- Status dot color: idle `#8a93a6`, working `var(--acc)` (with `edThink` pulse),
  ready `#18a45e`.
- **Entrance animations:** each report slot wrapper uses
  `animation: edToss .7s cubic-bezier(.34,1.4,.6,1) both` so it flies in from the
  mascot (left). Inside the bar chart, the 6 bars each use
  `animation: edGrow .5s ease-out both` with staggered `animation-delay` 0.15→0.65s.
  The trend line uses `stroke-dasharray:240; animation: edDraw .9s ease-out both`.
  The "Ready" badge uses `edBadge .5s cubic-bezier(.34,1.56,.64,1) both`.

**Report contents (exact copy):** title "Monthly report"; KPI "€1.24M" with green
"▲ 8.3%"; 6 bars heights `34,52,26,44,58,38`px (alternating `accent` / `accent-soft`);
trend polyline points `0,38 44,26 88,30 132,14 176,20 220,6 260,12`. Empty state: a
dashed inset box reading "Empty report".

## State management
Three independent interval timers (each `setInterval`, cleared on unmount):
- personality mood — 1450 ms, indexes the sequence above;
- report build — 1300 ms, `build = (build + 1) % 6`;
- (the same prototype also has an unrelated "assistant status" cycle you can ignore).

In a component, hold `mood` and `build` in state, `setInterval` in mount /
`clearInterval` on unmount, and derive the transforms/flags in render. Respect
`prefers-reduced-motion`: disable the loops (or hold each on its resting frame) as the
existing logo CSS already does for its disk/sparks.

## Accessibility
Mark the SVG `aria-hidden="true"` (decorative), same as the current `.bh` logo. If
Eddard conveys status (building/ready), surface that via the visible status label and,
if it's a live region, `aria-live="polite"` on the label — not via the animation.

## Files
- `Eddard - Options.dc.html` — the full prototype. The relevant cards are `7a`
  (personality loop) and `8a` (report builder). Earlier cards (`1x`–`6x`) are the
  concept exploration that led here and can be ignored for implementation.
- Reference (in the app repo, not this bundle): `static/css/_nexoraLogo.css` and
  `templates/nexora_logo/_nexora_logo.html` — the existing static black-hole logo whose
  colors/accent variables Eddard should match.
