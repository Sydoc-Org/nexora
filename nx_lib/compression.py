"""Gzip text responses on the way out.

Nexora's pages carry their JavaScript inline (``templates/js/*.html`` partials
included by the page template), so an HTML response is not a few KB of markup
but the whole client for that page -- ``/reporting`` alone is ~620 KB, and it
was going over the wire uncompressed on every navigation. Flask compresses
nothing by default, and IIS cannot make up for it here: ``web.config`` maps
``path="*"`` to the HttpPlatformHandler, so every request -- ``/static``
included -- is proxied to waitress rather than served (and compressed) by IIS
itself. Nobody was doing it.

ponytail: stdlib ``gzip``, not flask-compress. A new runtime dependency would
have to be installed into three interpreters (the dev-server global Python,
``.venv`` for tests, and PROD's ``D:\\sydoc\\tools\\py``) to save these ~20
lines -- and forgetting one of them is a silent 500 on that interpreter.
"""

import gzip

from flask import request

# Below this the gzip frame and the CPU cost outweigh the saving.
MIN_BYTES = 1024

# A send_file() body has to be read into memory to be compressed; past this
# it is not worth the RAM (the biggest text asset today is a 124 KB CSS).
MAX_BUFFER_BYTES = 2 * 1024 * 1024

# Compressible content types. Everything else (images, PDFs, xlsx, fonts) is
# already compressed and would only get bigger.
TEXT_TYPES = (
    "text/",
    "application/json",
    "application/javascript",
    "application/xml",
    "image/svg+xml",
)

# Measured on the real /reporting body (625 KB): level 1 = 14 ms / 33%,
# 5 = 24 ms / 27%, 6 = 36 ms / 27%, 9 = 80 ms / 27%. 5 is the knee -- past it
# you buy CPU, not bytes.
LEVEL = 5


def init_app(app):
    @app.after_request
    def _gzip(resp):
        # Caches (and IIS) must not hand a gzipped body to a client that did
        # not ask for one -- set this even when we decide not to compress.
        ctype = (resp.content_type or "").split(";")[0].strip().lower()
        if not ctype.startswith(TEXT_TYPES):
            return resp
        resp.vary.add("Accept-Encoding")

        if "gzip" not in request.headers.get("Accept-Encoding", "").lower():
            return resp
        # 204/304 have no body; a redirect's is not worth a frame. Errors are
        # left alone so a failure is never obscured by an encoding problem.
        if resp.status_code != 200:
            return resp
        if "Content-Encoding" in resp.headers:
            return resp
        # send_file() responses (every /static asset -- web.config hands the
        # whole path="*" to waitress, so Flask serves them, not IIS) arrive in
        # passthrough mode wrapping an open file, which also reads as streamed.
        # Reading one costs its size in memory, so take only a known, bounded
        # length: a 124 KB stylesheet yes, a large download no. Checked BEFORE
        # is_streamed for exactly that reason.
        if resp.direct_passthrough:
            length = resp.headers.get("Content-Length", type=int)
            if length is None or length > MAX_BUFFER_BYTES:
                return resp
            resp.direct_passthrough = False
        elif resp.is_streamed:
            # No length to check, and buffering it would defeat the streaming.
            return resp

        data = resp.get_data()
        if len(data) < MIN_BYTES:
            return resp
        resp.set_data(gzip.compress(data, LEVEL))
        resp.headers["Content-Encoding"] = "gzip"
        resp.headers["Content-Length"] = str(resp.calculate_content_length())
        # The ETag deliberately stays as send_file() set it. Suffixing it
        # "-gzip" (what flask-compress does) is more correct on paper -- the
        # compressed body IS a different entity -- but it breaks revalidation:
        # the browser sends the suffixed tag back in If-None-Match, Flask
        # compares it against the unsuffixed one it computes, and every
        # would-be 304 becomes a full 200. Vary: Accept-Encoding above is what
        # actually keeps caches honest, and IIS (our only proxy) respects it.
        return resp

    return app
