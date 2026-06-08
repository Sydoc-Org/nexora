---
description: Run the nexora Flask-Babel extract→update→compile translation cycle for de/fr/it
argument-hint: "[locale]  (optional: de|fr|it — default all three)"
---

Run the nexora translation workflow (reference: `docs/howto/babel.md`). Goal: every user-facing string is extracted and `de`/`fr`/`it` are fully, non-fuzzily translated, then compiled. English is the source locale and has no `.po` file.

Steps:

1. **Extract** to the template catalog:
   `pybabel extract -F babel.cfg -o messages.pot .`
2. **Update** the locale catalogs:
   `pybabel update -i messages.pot -d translations`
   (First time for a brand-new locale only: `pybabel init -i messages.pot -d translations -l <locale>`.)
3. **Translate** any new or `#, fuzzy` msgids in `translations/<locale>/LC_MESSAGES/messages.po` for $ARGUMENTS (default: `de`, `fr`, `it`). Remove the `#, fuzzy` flag once a translation is confirmed correct.
4. **Compile:**
   `pybabel compile -d translations`
5. If a `test_translations.py` suite exists, run it — it enforces that `messages.pot` is in sync and every msgid is translated (non-fuzzy) in all three locales.

Notes:
- If `pybabel` isn't on PATH, use the venv copy (e.g. `./venv/Scripts/pybabel`).
- Restart the dev server after compiling so the new catalogs load.
- `babel.cfg` controls what gets extracted (Python + Jinja templates); mark strings with `{{ _('…') }}` / `_('…')` before extracting.
