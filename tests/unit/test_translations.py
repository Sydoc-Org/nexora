"""Static checks for Flask-Babel catalog hygiene.

Three independent checks:

1. ``test_pot_is_in_sync`` — re-running ``pybabel extract`` produces the same
   set of msgids as the committed ``messages.pot``. Catches new ``_(...)`` /
   ``gettext(...)`` calls added without re-extracting.

2. ``test_all_strings_translated`` — every msgid in every locale's ``.po``
   has a non-empty msgstr AND is not marked ``#, fuzzy``. One sub-test per
   locale so failures are scoped.

3. ``test_mo_files_up_to_date`` — every ``.po`` has a corresponding ``.mo``
   that is no older than the ``.po``.

If any of these fail, the fix is one of:
    pybabel extract -F babel.cfg -o messages.pot .
    pybabel update -i messages.pot -d translations
    # edit translations/<lang>/LC_MESSAGES/messages.po
    pybabel compile -d translations
"""

import subprocess
import sys
from pathlib import Path

import pytest
from babel.messages.pofile import read_po


REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS_DIR = REPO_ROOT / "translations"
POT_PATH = REPO_ROOT / "messages.pot"
BABEL_CFG = REPO_ROOT / "babel.cfg"
LOCALES = ("de", "fr", "it")


def _read_catalog(path):
    with open(path, "rb") as f:
        return read_po(f)


def _msgid_set(catalog):
    """Set of (msgid, context) tuples — skip the header (empty msgid)."""
    out = set()
    for msg in catalog:
        if not msg.id:
            continue
        # msg.id is a tuple for plural forms, str otherwise
        out.add((msg.id if isinstance(msg.id, str) else tuple(msg.id), msg.context))
    return out


def test_pot_is_in_sync(tmp_path):
    """messages.pot must contain exactly the msgids that pybabel extract finds."""
    fresh_pot = tmp_path / "messages.pot"

    # Use the same invocation as howtobabel.txt
    result = subprocess.run(
        [sys.executable, "-m", "babel.messages.frontend", "extract",
         "-F", str(BABEL_CFG), "-o", str(fresh_pot), "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"pybabel extract failed:\n{result.stderr}"

    committed = _msgid_set(_read_catalog(POT_PATH))
    fresh = _msgid_set(_read_catalog(fresh_pot))

    only_in_committed = committed - fresh
    only_in_fresh = fresh - committed

    if only_in_committed or only_in_fresh:
        msg = ["messages.pot is out of sync with the source. Run:",
               "    pybabel extract -F babel.cfg -o messages.pot .",
               "    pybabel update -i messages.pot -d translations",
               ""]
        if only_in_fresh:
            msg.append(f"NEW strings in source but not in messages.pot ({len(only_in_fresh)}):")
            for mid, ctx in sorted(only_in_fresh, key=lambda x: str(x[0]))[:20]:
                msg.append(f"  + {mid!r}" + (f" [ctx={ctx!r}]" if ctx else ""))
            if len(only_in_fresh) > 20:
                msg.append(f"  ... and {len(only_in_fresh) - 20} more")
            msg.append("")
        if only_in_committed:
            msg.append(f"REMOVED strings still in messages.pot ({len(only_in_committed)}):")
            for mid, ctx in sorted(only_in_committed, key=lambda x: str(x[0]))[:20]:
                msg.append(f"  - {mid!r}" + (f" [ctx={ctx!r}]" if ctx else ""))
            if len(only_in_committed) > 20:
                msg.append(f"  ... and {len(only_in_committed) - 20} more")
        pytest.fail("\n".join(msg))


@pytest.mark.parametrize("locale", LOCALES)
def test_all_strings_translated(locale):
    """Every translatable msgid must have a non-empty, non-fuzzy msgstr."""
    po_path = TRANSLATIONS_DIR / locale / "LC_MESSAGES" / "messages.po"
    assert po_path.exists(), f"missing {po_path}"

    catalog = _read_catalog(po_path)

    untranslated = []
    fuzzy = []
    for msg in catalog:
        if not msg.id:
            continue  # header
        # plural form: msg.string is a tuple, all entries must be non-empty
        if isinstance(msg.string, tuple):
            if any(not s for s in msg.string):
                untranslated.append(msg.id)
                continue
        else:
            if not msg.string:
                untranslated.append(msg.id)
                continue
        if "fuzzy" in msg.flags:
            fuzzy.append(msg.id)

    if untranslated or fuzzy:
        lines = [f"[{locale}] translations incomplete in {po_path.relative_to(REPO_ROOT)}:", ""]
        if untranslated:
            lines.append(f"UNTRANSLATED ({len(untranslated)}):")
            for mid in untranslated[:20]:
                lines.append(f"  - {mid!r}")
            if len(untranslated) > 20:
                lines.append(f"  ... and {len(untranslated) - 20} more")
            lines.append("")
        if fuzzy:
            lines.append(f"FUZZY (needs review, remove #, fuzzy after editing) ({len(fuzzy)}):")
            for mid in fuzzy[:20]:
                lines.append(f"  - {mid!r}")
            if len(fuzzy) > 20:
                lines.append(f"  ... and {len(fuzzy) - 20} more")
        pytest.fail("\n".join(lines))


@pytest.mark.parametrize("locale", LOCALES)
def test_mo_files_up_to_date(locale):
    """Every .po must have a .mo that is no older than the .po."""
    po_path = TRANSLATIONS_DIR / locale / "LC_MESSAGES" / "messages.po"
    mo_path = TRANSLATIONS_DIR / locale / "LC_MESSAGES" / "messages.mo"

    assert po_path.exists(), f"missing {po_path}"
    if not mo_path.exists():
        pytest.fail(
            f"[{locale}] missing compiled {mo_path.relative_to(REPO_ROOT)}\n"
            "    Run: pybabel compile -d translations"
        )

    po_mtime = po_path.stat().st_mtime
    mo_mtime = mo_path.stat().st_mtime
    if mo_mtime < po_mtime:
        pytest.fail(
            f"[{locale}] {mo_path.relative_to(REPO_ROOT)} is older than its .po "
            f"(po={po_mtime}, mo={mo_mtime})\n"
            "    Run: pybabel compile -d translations"
        )
