# Reference screen — Dashboard

One screen, not a page catalogue: the approved slim Dashboard (option 1a of the
redesign) composed entirely from the kit's components, so a developer can see
every component in its intended context.

| File | What |
|---|---|
| `DashboardScreen.jsx` | PageHead → FilterRow → KpiStrip → ChartHeader/UnderlineTabs → SectionRule + SeriesLegend |
| `Shell.jsx` | the persistent nav rail from `templates/_header.html` (64px → 220px on hover) |
| `Charts.jsx` | SVG stand-ins for the Chart.js canvases; the axis treatment and colours are the spec |

The nav rail is display-only. Other pages are not recreated here on purpose —
the kit (`components/`, `tokens/`, `guidelines/`) is what future pages follow.
