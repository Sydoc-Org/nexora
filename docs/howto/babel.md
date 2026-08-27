# Babel translation workflow

## Setup (one-time)

```powershell
py -m venv venv               # create venv
.\venv\Scripts\activate       # activate venv
pip install Flask-Babel       # install babel
```

Create `babel.cfg`:

```
[python: *.py]
[jinja2: **/templates/**.html]
encoding=utf-8
```

## Marking strings

In HTML/Jinja templates: `{{ _('string1') }}`, `{{ _('string2') }}`
In Python: `_('string1')` or `gettext('string1')`

**Not in `static/js/*.js`.** The extractor only reads `**/templates/**.html`
and Python, so a `_()` in a static JS file is never extracted and never
translated. Those files (see #191) are paired with a small inline shim in
`templates/js/` that renders an `I18N` / `NX_*` object literal — add the string
there as `key: {{ _("…")|tojson }}` and read `I18N.key` from the `.js`.

## Extract → init → update → translate → compile

Get all marked strings into `messages.pot`:

```powershell
pybabel extract -F babel.cfg -o messages.pot .
```

First time per locale:

```powershell
pybabel init -i messages.pot -d translations -l de   # german
pybabel init -i messages.pot -d translations -l fr   # french
pybabel init -i messages.pot -d translations -l it   # italian
```

Subsequent updates:

```powershell
pybabel update -i messages.pot -d translations
```

Translate strings in `translations/<lang>/LC_MESSAGES/messages.po`:

```
msgid "string1"
msgstr "string1 in the target language"
```

Compile:

```powershell
pybabel compile -d translations
```
