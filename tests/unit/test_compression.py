"""Response gzip (nx_lib/compression.py)."""

import gzip

from flask import Flask, send_file

from nx_lib import compression

BIG = "x" * 5000


def _app(css_path=None):
    app = Flask(__name__)
    compression.init_app(app)

    @app.route("/asset.css")
    def asset():
        # send_file() is how /static is served: a direct_passthrough response
        # wrapping an open file, which also reads as streamed.
        return send_file(css_path, mimetype="text/css")

    @app.route("/big")
    def big():
        return BIG

    @app.route("/small")
    def small():
        return "hi"

    @app.route("/png")
    def png():
        return app.response_class(b"\x89PNG" + b"\0" * 5000, mimetype="image/png")

    @app.route("/boom")
    def boom():
        return BIG, 500

    return app.test_client()


def test_large_text_is_gzipped_and_declares_itself():
    res = _app().get("/big", headers={"Accept-Encoding": "gzip"})
    assert res.headers["Content-Encoding"] == "gzip"
    assert gzip.decompress(res.get_data()).decode() == BIG
    assert int(res.headers["Content-Length"]) == len(res.get_data())
    assert len(res.get_data()) < len(BIG)
    assert "Accept-Encoding" in res.headers["Vary"]


def test_client_that_did_not_ask_gets_plain_text_and_a_vary_header():
    res = _app().get("/big")
    assert "Content-Encoding" not in res.headers
    assert res.get_data().decode() == BIG
    # Without Vary a shared cache could hand this body to a gzip client's
    # request, or the gzipped one to this client.
    assert "Accept-Encoding" in res.headers["Vary"]


def test_small_already_compressed_and_error_responses_are_left_alone():
    client = _app()
    for path in ("/small", "/png", "/boom"):
        res = client.get(path, headers={"Accept-Encoding": "gzip"})
        assert "Content-Encoding" not in res.headers, path


def test_static_style_send_file_response_is_compressed(tmp_path):
    # web.config routes path="*" to waitress, so Flask (not IIS) serves
    # /static -- a passthrough response has to be compressed here or nowhere.
    css = tmp_path / "big.css"
    css.write_text(BIG)
    client = _app(css)
    res = client.get("/asset.css", headers={"Accept-Encoding": "gzip"})
    assert res.headers["Content-Encoding"] == "gzip"
    assert gzip.decompress(res.get_data()).decode() == BIG
    # Revalidation must survive compression: a browser sends back the ETag it
    # was given, and a rewritten one (e.g. "…-gzip") would turn every 304 into
    # a full re-download of the asset.
    again = client.get(
        "/asset.css",
        headers={"Accept-Encoding": "gzip", "If-None-Match": res.headers["ETag"]},
    )
    assert again.status_code == 304
