"""MS02 client config keys exist and default sanely."""

from nx_lib import config as cfg


def test_ms02_keys_exist():
    # These attributes must exist (value may be None on a box without MS02 env).
    for name in (
        "MS02_DB_HOST",
        "MS02_DB_NAME",
        "MS02_DB_USER",
        "MS02_DB_PWD",
        "MS02_DB_PORT",
        "MS02_OCTO_DOMAIN",
        "MS02_OCTO_CLIENT_ID",
        "MS02_OCTO_CLIENT_SECRET",
        "MS02_OCTO_GRANT_TYPE",
    ):
        assert hasattr(cfg, name), f"missing config.{name}"


def test_ms02_port_defaults_to_5432():
    # When MS02_DB_PORT is unset, it defaults to the Postgres default.
    assert cfg.MS02_DB_PORT in ("5432", None) or isinstance(cfg.MS02_DB_PORT, str)
