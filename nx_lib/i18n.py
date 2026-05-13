"""Locale / timezone resolution used by Flask-Babel."""

from flask import g, request, session


def get_locale():
    if "locale" in session:
        return session["locale"]
    user = getattr(g, "user", None)
    if user is not None and user.locale in ["en", "de", "fr", "it"]:
        return user.locale
    return request.accept_languages.best_match(["de", "fr", "en", "it"])


def get_timezone():
    user = getattr(g, "user", None)
    if user is not None:
        return user.timezone
