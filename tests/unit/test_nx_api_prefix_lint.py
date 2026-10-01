"""NX.api / NX.apiSafe add API_PREFIX themselves (nx_core.js resolveUrl).

A URL that is already prefixed ("${API}api/..." or API_PREFIX + "api/...")
becomes "/nexora/nexora/api/..." on PROD and STAGING -- a 404 that INT, whose
prefix is "/", never shows (#433: the Controlling page loaded nothing on
staging). Pass "/api/..." to them instead.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CALL = re.compile(
    r"NX\.api(?:Safe)?\(\s*(?:`\$\{(?:API|API_PREFIX|window\.API_PREFIX)\}|(?:API|API_PREFIX|window\.API_PREFIX)\s*\+)"
)


def test_no_prefixed_url_is_passed_to_nx_api():
    offenders = []
    for path in sorted((REPO / "static" / "js").rglob("*.js")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CALL.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{n}: {line.strip()[:100]}")
    assert not offenders, "NX.api adds API_PREFIX itself:\n" + "\n".join(offenders)
