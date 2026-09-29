"""Every page declares its language (#260 review).

47 templates wrote ``<html lang="{{ get_locale }}">``. ``get_locale`` is not in
the template context -- the context processor exposes ``current_lang`` -- so
Jinja rendered an empty string and every page shipped ``lang=""``: screen
readers and hyphenation had no language to go on.
"""

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
HTML_LANG = re.compile(r'<html lang="([^"]*)"')


def test_html_lang_uses_the_context_variable():
    wrong = [
        f"{path.relative_to(TEMPLATES)}: lang={value!r}"
        for path in TEMPLATES.rglob("*.html")
        for value in HTML_LANG.findall(path.read_text(encoding="utf-8"))
        if value not in ("{{ current_lang }}", "en")
    ]
    assert not wrong, "use {{ current_lang }}: " + "; ".join(wrong)


def test_rendered_page_carries_the_language(client):
    for headers in ({}, {"Accept-Language": "de-CH,de;q=0.9"}, {"Accept-Language": "es"}):
        body = client.get("/privacy", headers=headers).get_data(as_text=True)
        lang = HTML_LANG.search(body).group(1)
        assert lang in ("de", "en", "fr", "it"), f"{headers}: rendered lang={lang!r}"
