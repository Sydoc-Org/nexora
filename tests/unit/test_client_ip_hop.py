"""Rate-limit key and CSV-log IP read the RIGHTMOST X-Forwarded-For hop (the
one the nearest proxy appended), never the client-typed leftmost one."""

from nx_lib import create_app
from nx_lib.extensions import client_ip
from nx_lib.hooks import get_ip


def test_rightmost_hop_wins():
    app = create_app()
    with app.test_request_context(headers={"X-Forwarded-For": "6.6.6.6, 10.0.0.9"}):
        assert client_ip() == "10.0.0.9"
        assert get_ip() == "10.0.0.9"
    with app.test_request_context(environ_base={"REMOTE_ADDR": "192.168.1.5"}):
        assert client_ip() == "192.168.1.5"
        assert get_ip() == "192.168.1.5"
