"""WSGI middleware applied to the Flask app for production deployments."""


class PrefixMiddleware:
    """Strip an external URL prefix (e.g. /nexora) from incoming requests.

    Used in production when IIS reverse-proxies the app under a sub-path. The
    middleware rewrites PATH_INFO/SCRIPT_NAME so Flask routes still resolve
    against the unprefixed URL space.
    """

    def __init__(self, app, prefix=""):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if environ["PATH_INFO"].startswith(self.prefix):
            environ["PATH_INFO"] = environ["PATH_INFO"][len(self.prefix):]
            environ["SCRIPT_NAME"] = self.prefix
            return self.app(environ, start_response)
        start_response("404 NOT FOUND", [("Content-Type", "text/plain")])
        return [b"This URL does not belong to the application."]
