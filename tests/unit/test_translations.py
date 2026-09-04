"""Static checks for Flask-Babel catalog hygiene.

Three independent checks:

1. ``test_pot_is_in_sync`` — re-running ``pybabel extract`` produces the same
   set of msgids as the committed ``messages.pot``. Catches new ``_(...)`` /
   ``gettext(...)`` calls added without re-extracting.

2. ``test_all_strings_translated`` — every msgid in every locale's ``.po``
   has a non-empty msgstr AND is not marked ``#, fuzzy``. One sub-test per
   locale so failures are scoped.

3. ``test_mo_files_up_to_date`` — every translated entry in ``.po`` appears
   in the corresponding ``.mo`` with the same translation. Compares content,
   not mtimes (mtimes are unreliable: git checkout writes files in sequence,
   so .po routinely ends up a few ms newer than .mo even when they match).

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
from babel.messages.mofile import read_mo
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

    # Use the same invocation as docs/howto/babel.md
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "babel.messages.frontend",
            "extract",
            "-F",
            str(BABEL_CFG),
            "-o",
            str(fresh_pot),
            ".",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"pybabel extract failed:\n{result.stderr}"

    committed = _msgid_set(_read_catalog(POT_PATH))
    fresh = _msgid_set(_read_catalog(fresh_pot))

    only_in_committed = committed - fresh
    only_in_fresh = fresh - committed

    if only_in_committed or only_in_fresh:
        msg = [
            "messages.pot is out of sync with the source. Run:",
            "    pybabel extract -F babel.cfg -o messages.pot .",
            "    pybabel update -i messages.pot -d translations",
            "",
        ]
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
            lines.extend(f"  - {mid!r}" for mid in untranslated[:20])
            if len(untranslated) > 20:
                lines.append(f"  ... and {len(untranslated) - 20} more")
            lines.append("")
        if fuzzy:
            lines.append(f"FUZZY (needs review, remove #, fuzzy after editing) ({len(fuzzy)}):")
            lines.extend(f"  - {mid!r}" for mid in fuzzy[:20])
            if len(fuzzy) > 20:
                lines.append(f"  ... and {len(fuzzy) - 20} more")
        pytest.fail("\n".join(lines))


def _translations_map(catalog):
    """Map (msgid, ctx) -> msgstr for entries with a non-empty translation.

    For plural forms msgid is a tuple and msgstr is a tuple of strings.
    Header (empty msgid) and untranslated entries are skipped, since pybabel
    compile omits untranslated entries from the .mo by default.
    """
    out = {}
    for msg in catalog:
        if not msg.id:
            continue
        key = (msg.id if isinstance(msg.id, str) else tuple(msg.id), msg.context)
        if isinstance(msg.string, tuple):
            if not any(msg.string):
                continue
            out[key] = tuple(msg.string)
        else:
            if not msg.string:
                continue
            out[key] = msg.string
    return out


@pytest.mark.parametrize("locale", LOCALES)
def test_mo_files_up_to_date(locale):
    """Every translated entry in .po must appear in .mo with the same msgstr.

    Content comparison instead of mtime: when both files are checked out by
    git, their mtimes reflect checkout order, not whether the .mo was
    actually compiled from the current .po.
    """
    po_path = TRANSLATIONS_DIR / locale / "LC_MESSAGES" / "messages.po"
    mo_path = TRANSLATIONS_DIR / locale / "LC_MESSAGES" / "messages.mo"

    assert po_path.exists(), f"missing {po_path}"
    if not mo_path.exists():
        pytest.fail(
            f"[{locale}] missing compiled {mo_path.relative_to(REPO_ROOT)}\n"
            "    Run: pybabel compile -d translations"
        )

    po_translations = _translations_map(_read_catalog(po_path))
    with open(mo_path, "rb") as f:
        mo_translations = _translations_map(read_mo(f))

    missing = [k for k in po_translations if k not in mo_translations]
    mismatched = [
        k
        for k in po_translations
        if k in mo_translations and po_translations[k] != mo_translations[k]
    ]

    if missing or mismatched:
        lines = [
            f"[{locale}] {mo_path.relative_to(REPO_ROOT)} is out of sync with "
            f"{po_path.relative_to(REPO_ROOT)}",
            "    Run: pybabel compile -d translations",
            "",
        ]
        if missing:
            lines.append(f"MISSING from .mo ({len(missing)}):")
            for mid, ctx in missing[:10]:
                lines.append(f"  - {mid!r}" + (f" [ctx={ctx!r}]" if ctx else ""))
            if len(missing) > 10:
                lines.append(f"  ... and {len(missing) - 10} more")
            lines.append("")
        if mismatched:
            lines.append(f"DIFFERENT translation in .mo vs .po ({len(mismatched)}):")
            for mid, ctx in mismatched[:10]:
                lines.append(
                    f"  - {mid!r}"
                    + (f" [ctx={ctx!r}]" if ctx else "")
                    + f"\n      .po: {po_translations[(mid, ctx)]!r}"
                    + f"\n      .mo: {mo_translations[(mid, ctx)]!r}"
                )
            if len(mismatched) > 10:
                lines.append(f"  ... and {len(mismatched) - 10} more")
        pytest.fail("\n".join(lines))


# --- 4. Template strings must survive Jinja's format pass -------------------
#
# jinja2's gettext alias ends with `return rv % variables` -- unconditionally,
# even when the call passes no variables. So a bare `%` in a translated string
# is not a cosmetic issue: `"Extraction correct %" % {}` raises ValueError and
# the whole page 500s. A literal percent sign must be written `%%`.
#
# This bit #254 in dd57cfbf: three reporting tips quoted measure labels ending
# in `%`, and /reporting was a hard 500 until they were escaped. It went
# unnoticed because Jinja caches templates for the process lifetime, so the
# dev server kept serving the pre-edit copy.
#
# Checked for msgstr too, not just msgid: a translator writing a bare `%`
# breaks that one locale only, which is exactly the kind of bug nobody sees
# until a French-speaking user opens the page.


class _AnyKey:
    """A mapping that answers every key, so `%(name)s` placeholders resolve.

    Named placeholders are legitimate -- the caller supplies them. Only a
    malformed conversion (a bare `%`) should fail, and that raises ValueError
    regardless of what the mapping holds.
    """

    def __getitem__(self, key):
        return 0  # works for %s, %d and %f alike


def _formats_cleanly(text):
    """True if Jinja's `rv % variables` would not raise on this string."""
    try:
        text % _AnyKey()
    except (ValueError, TypeError):
        return False
    return True


def _template_msgids():
    """msgids that come from a template, i.e. the ones Jinja renders."""
    catalog = _read_catalog(POT_PATH)
    out = []
    for msg in catalog:
        if not msg.id:
            continue
        if any(str(fname).startswith("templates") for fname, _lineno in msg.locations):
            out.append(msg.id)
    return out


def test_template_msgids_survive_jinja_percent_formatting():
    ids = _template_msgids()
    assert ids, "no template msgids found -- is messages.pot stale?"
    bad = [mid for mid in ids if not _formats_cleanly(mid)]
    assert not bad, (
        "these template strings contain an unescaped '%' and will raise "
        "ValueError inside jinja2's gettext (a 500 on the page). "
        "Write a literal percent sign as '%%':\n" + "\n".join(f"  - {mid!r}" for mid in bad)
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_translated_template_strings_survive_jinja_percent_formatting(locale):
    template_ids = set(_template_msgids())
    catalog = _read_catalog(TRANSLATIONS_DIR / locale / "LC_MESSAGES" / "messages.po")
    bad = []
    for msg in catalog:
        if not msg.id or msg.id not in template_ids:
            continue
        strings = msg.string if isinstance(msg.string, tuple) else (msg.string,)
        bad.extend(text for text in strings if text and not _formats_cleanly(text))
    assert not bad, (
        f"[{locale}] these translations contain an unescaped '%' and will "
        "raise inside jinja2's gettext, 500ing the page for this locale only. "
        "Write a literal percent sign as '%%':\n" + "\n".join(f"  - {text!r}" for text in bad)
    )
