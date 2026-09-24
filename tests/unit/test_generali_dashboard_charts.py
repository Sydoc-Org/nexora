r"""Chart hover and tooltip theming on the Generali dashboard.

Three faults, all of them Chart.js defaults nobody overrode:

1. The two single-series bar charts kept Chart.js's `nearest` + `intersect`,
   so a tooltip only appeared with the cursor exactly on the bar. On the
   *horizontal* one that is the worst case — the whole row reads as the
   target and most of it is the label and the empty track.
2. Every tooltip was the stock black box with white text and no border. On a
   dark page that is a near-black panel on a dark card with no edge between
   them, which is what made the hover look broken rather than merely plain.
3. The doughnuts drew their slice separators in a literal `#fff` — a white
   web over a dark chart. Same fault as the workitem stepper circles (#326).

The invariants here are about *where a colour comes from* and *how big the
hover target is*, not about exact values.

Deliberately NOT changed, and pinned so nobody "fixes" it: the doughnuts keep
`nearest`/`intersect`. The slice under the cursor is already the right answer,
and index mode would light up every slice at once.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PARTIAL = (REPO / "templates" / "js" / "_generali_dashboard_js.html").read_text(encoding="utf-8")

INDEX_MODE = "interaction: { mode: 'index', intersect: false }"


def _chart_block(canvas_id: str) -> str:
    """The `new Chart(...)` call for one canvas, up to the next one."""
    start = PARTIAL.index(f"getElementById('{canvas_id}')")
    rest = PARTIAL[start:]
    nxt = rest.find("new Chart(", 1)
    return rest[:nxt] if nxt != -1 else rest


def test_bar_charts_respond_across_the_whole_column():
    """Both were direct-hit-only before; a bar is a small target."""
    for canvas in ("empfaengerChart", "channelChart"):
        assert INDEX_MODE in _chart_block(canvas), canvas


def test_the_charts_that_already_had_it_keep_it():
    for canvas in ("nkChart", "trendChart"):
        assert INDEX_MODE in _chart_block(canvas), canvas


def test_doughnuts_deliberately_keep_the_default_mode():
    """Index mode on a doughnut lights every slice at once."""
    for canvas in ("doctypeChart", "languageChart"):
        assert INDEX_MODE not in _chart_block(canvas), canvas


def test_tooltip_takes_its_colours_from_theme_tokens():
    tooltip = PARTIAL[PARTIAL.index("Chart.defaults.plugins.tooltip") :][:900]
    for token in ("--nx-card", "--nx-text", "--nx-text-sec", "--nx-border"):
        assert token in tooltip, token


def test_tooltip_colours_are_scriptable_so_they_follow_a_theme_toggle():
    """Read once at creation, a tooltip stays the old theme's colour."""
    tooltip = PARTIAL[PARTIAL.index("Chart.defaults.plugins.tooltip") :][:900]
    for key in ("backgroundColor", "titleColor", "bodyColor", "borderColor"):
        assert re.search(rf"{key}:\s*\(\)\s*=>", tooltip), key


def test_doughnut_slice_separators_are_tokenised_and_scriptable():
    """A literal #fff here is a white web over the chart in dark mode."""
    for canvas in ("doctypeChart", "languageChart"):
        block = _chart_block(canvas)
        assert re.search(r"borderColor:\s*\(\)\s*=>\s*token\('--nx-card'", block), canvas


def test_no_hardcoded_white_is_left_on_a_themed_surface():
    """The trend line's own #4f46e5 is a series colour, not a surface."""
    assert "borderColor: '#fff'" not in PARTIAL
