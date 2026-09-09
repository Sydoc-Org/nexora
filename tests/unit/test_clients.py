"""Client registry: default always present; octo creds resolve by domain.

_build_clients() reads dbo.Clients (migration 0079) via engine_nexora_db.raw_connection(),
the same mocking pattern as tests/unit/test_mapping_config.py. A DB load failure falls
back to a hardcoded default-only registry so the app still boots (e.g. on TEST, which
has no dbo.Clients).
"""

import logging
import types
from unittest.mock import MagicMock

from nx_lib import clients


def _row(
    client_code="default",
    display_name="Default",
    dialect="tsql",
    runtime_engine_key="engine_octo_db",
    stats_engine_key="engine_statistics_db",
    stats_dialect="tsql",
    docfields_engine_key="engine_statistics_db",
    docfields_dialect="tsql",
    octo_domain=None,
    secret_ref=None,
    is_active=True,
):
    return types.SimpleNamespace(
        ClientCode=client_code,
        DisplayName=display_name,
        Dialect=dialect,
        RuntimeEngineKey=runtime_engine_key,
        StatsEngineKey=stats_engine_key,
        StatsDialect=stats_dialect,
        DocfieldsEngineKey=docfields_engine_key,
        DocfieldsDialect=docfields_dialect,
        OctoDomain=octo_domain,
        SecretRef=secret_ref,
        IsActive=is_active,
    )


class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def execute(self, sql, *params):
        pass

    def fetchall(self):
        return self._rows


def _engine_with(rows):
    cur = _FakeCursor(rows)
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng, conn


def _dead_engine(msg="NexoraDB down"):
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError(msg)
    return eng


def test_engine_keys_cannot_drift_from_the_engine_dict():
    """_ENGINE_KEYS is what /admin/clients validates a submitted engine key
    against; _engines() is what _build_clients() resolves it with. A sixth
    engine added to one and not the other would make the admin page reject a
    legitimate key with 'Unknown runtime engine key'."""
    assert tuple(clients._engines()) == clients._ENGINE_KEYS


def test_engine_keys_cover_todays_six_engines():
    assert set(clients._ENGINE_KEYS) == {
        "engine_octo_db",
        "engine_statistics_db",
        "engine_ms02_pg",
        "engine_ms02_stats_pg",
        "engine_ms02_docfields_pg",
        "engine_generali_db",
    }


def test_default_client_present():
    assert "default" in clients.CLIENTS
    d = clients.CLIENTS["default"]
    assert d.code == "default"
    assert d.dialect == "tsql"


def test_octo_creds_for_unknown_domain_falls_back_to_default(monkeypatch):
    from nx_lib import config as cfg

    monkeypatch.setattr(cfg, "OCTO_CLIENT_ID", "DEF_ID")
    monkeypatch.setattr(cfg, "OCTO_CLIENT_SECRET", "DEF_SECRET")
    monkeypatch.setattr(cfg, "OCTO_GRANT_TYPE", "client_credentials")
    cid, secret, grant = clients.octo_creds_for_domain("nobody.example")
    assert cid == "DEF_ID"
    assert secret == "DEF_SECRET"
    assert grant == "client_credentials"


def test_octo_creds_resolve_by_registered_domain():
    # The default client's own domain resolves to the default creds.
    d = clients.CLIENTS["default"]
    cid, secret, grant = clients.octo_creds_for_domain(d.octo_domain)
    assert cid == d.octo_client_id
    assert secret == d.octo_secret


def test_build_clients_reads_rows_from_db(monkeypatch):
    monkeypatch.setattr(clients, "engine_octo_db", "ENGINE_OCTO")
    monkeypatch.setattr(clients, "engine_statistics_db", "ENGINE_STATS")
    eng, conn = _engine_with([_row()])
    monkeypatch.setattr(clients, "engine_nexora_db", eng)

    result = clients._build_clients()

    assert set(result.keys()) == {"default"}
    d = result["default"]
    assert d.code == "default"
    assert d.dialect == "tsql"
    assert d.runtime_engine == "ENGINE_OCTO"
    assert d.stats_engine == "ENGINE_STATS"
    assert d.docfields_engine == "ENGINE_STATS"
    conn.close.assert_called_once()


def test_build_clients_skips_row_whose_engine_is_none(monkeypatch):
    monkeypatch.setattr(clients, "engine_octo_db", "ENGINE_OCTO")
    monkeypatch.setattr(clients, "engine_statistics_db", "ENGINE_STATS")
    monkeypatch.setattr(clients, "engine_ms02_pg", None)  # today's MS02 degradation
    monkeypatch.setattr(clients.cfg, "MS02_OCTO_DOMAIN", "ms02.example")
    rows = [
        _row(),
        _row(
            client_code="ms02",
            display_name="MS02",
            dialect="postgres",
            runtime_engine_key="engine_ms02_pg",
            stats_engine_key="engine_ms02_stats_pg",
            stats_dialect="postgres",
            docfields_engine_key="engine_ms02_docfields_pg",
            docfields_dialect="postgres",
            secret_ref="MS02",
        ),
    ]
    eng, _ = _engine_with(rows)
    monkeypatch.setattr(clients, "engine_nexora_db", eng)

    result = clients._build_clients()

    assert set(result.keys()) == {"default"}


def test_build_clients_loads_domainless_non_default_row_as_data_only(monkeypatch):
    """A non-default row without any resolvable Octo domain is a data-only
    connection (#257, Generali): it loads with octo_domain None and stays out
    of workitem routing (workitem_clients), instead of being skipped."""
    monkeypatch.setattr(clients, "engine_octo_db", "ENGINE_OCTO")
    monkeypatch.setattr(clients, "engine_statistics_db", "ENGINE_STATS")
    monkeypatch.setattr(clients, "engine_ms02_pg", "ENGINE_MS02")
    monkeypatch.setattr(clients.cfg, "MS02_OCTO_DOMAIN", None)  # unset env domain
    rows = [
        _row(),
        _row(
            client_code="ms02",
            display_name="MS02",
            dialect="postgres",
            runtime_engine_key="engine_ms02_pg",
            stats_engine_key="engine_ms02_stats_pg",
            stats_dialect="postgres",
            docfields_engine_key="engine_ms02_docfields_pg",
            docfields_dialect="postgres",
            octo_domain=None,
            secret_ref="MS02",
        ),
    ]
    eng, _ = _engine_with(rows)
    monkeypatch.setattr(clients, "engine_nexora_db", eng)

    result = clients._build_clients()

    assert set(result.keys()) == {"default", "ms02"}
    assert result["ms02"].octo_domain is None
    monkeypatch.setattr(clients, "CLIENTS", result)
    assert clients.workitem_clients() == ["default"]


def test_default_survives_engine_and_domain_degradation(monkeypatch):
    """D5: the skip guard was always MS02-only. 'default' must stay registered
    even when its own runtime engine is unavailable and its Octo domain is unset --
    workitem_sources.py indexes CLIENTS["default"] unguarded (CLIENTS["default"],
    CLIENTS.get(code) or CLIENTS["default"])."""
    monkeypatch.setattr(clients, "engine_octo_db", None)
    monkeypatch.setattr(clients.cfg, "OCTO_DOMAIN", None)
    eng, _ = _engine_with([_row(runtime_engine_key="engine_octo_db", octo_domain=None)])
    monkeypatch.setattr(clients, "engine_nexora_db", eng)

    result = clients._build_clients()

    assert "default" in result
    assert result["default"].code == "default"


def test_default_row_skipped_logs_warning(monkeypatch, caplog):
    """Case 2 (active 'default' row present but dropped by the skip guard) must
    log a warning naming what was wrong -- an admin saving a bad 'default' row
    through the phase-B UI should not be silently swapped to stale env config."""
    monkeypatch.setattr(clients, "engine_octo_db", None)
    monkeypatch.setattr(clients.cfg, "OCTO_DOMAIN", None)
    eng, _ = _engine_with([_row(runtime_engine_key="engine_octo_db", octo_domain=None)])
    monkeypatch.setattr(clients, "engine_nexora_db", eng)

    with caplog.at_level(logging.WARNING, logger="nx_lib.clients"):
        result = clients._build_clients()

    assert "default" in result
    assert any(
        "default" in rec.message and "unresolved" in rec.message.lower() for rec in caplog.records
    )


def test_no_default_row_at_all_logs_no_warning(monkeypatch, caplog):
    """Case 1 (dbo.Clients simply has no 'default' row) is benign -- the
    hardcoded fallback is exactly right and must stay silent."""
    monkeypatch.setattr(clients, "engine_octo_db", "ENGINE_OCTO")
    monkeypatch.setattr(clients, "engine_statistics_db", "ENGINE_STATS")
    eng, _ = _engine_with([])  # no rows at all
    monkeypatch.setattr(clients, "engine_nexora_db", eng)

    with caplog.at_level(logging.WARNING, logger="nx_lib.clients"):
        result = clients._build_clients()

    assert "default" in result
    assert caplog.records == []


def test_build_clients_prefers_db_octo_domain_over_env(monkeypatch):
    """OctoDomain column wins over the SecretRef-resolved env domain when set --
    phase B writes this column through the admin UI."""
    monkeypatch.setattr(clients, "engine_octo_db", "ENGINE_OCTO")
    monkeypatch.setattr(clients, "engine_statistics_db", "ENGINE_STATS")
    monkeypatch.setattr(clients.cfg, "OCTO_DOMAIN", "env-default.example")
    eng, _ = _engine_with([_row(octo_domain="db-default.example")])
    monkeypatch.setattr(clients, "engine_nexora_db", eng)

    result = clients._build_clients()

    assert result["default"].octo_domain == "db-default.example"


def test_build_clients_skips_inactive_rows(monkeypatch):
    monkeypatch.setattr(clients, "engine_octo_db", "ENGINE_OCTO")
    monkeypatch.setattr(clients, "engine_statistics_db", "ENGINE_STATS")
    rows = [
        _row(),
        _row(client_code="ms02", display_name="MS02", is_active=False),
    ]
    eng, _ = _engine_with(rows)
    monkeypatch.setattr(clients, "engine_nexora_db", eng)

    result = clients._build_clients()

    assert set(result.keys()) == {"default"}


def test_build_clients_falls_back_to_hardcoded_default_on_db_error(monkeypatch):
    monkeypatch.setattr(clients, "engine_nexora_db", _dead_engine())

    result = clients._build_clients()

    assert set(result.keys()) == {"default"}
    assert result["default"].code == "default"
    assert result["default"].runtime_engine is clients.engine_octo_db


# ---- degraded-state signal --------------------------------------------------
#
# _build_clients() runs at import, before Flask configures logging: its
# logger.error reaches stderr (waitress-stdout*) but never app.log, and nothing
# surfaces it in the UI. The recorded reason is what /admin/clients and
# /admin/status render, so it must not depend on logging at all.


def test_db_error_records_a_degraded_reason_on_the_module(monkeypatch):
    monkeypatch.setattr(clients, "engine_nexora_db", _dead_engine("NexoraDB down"))
    monkeypatch.setattr(clients, "REGISTRY_DEGRADED_REASON", None)

    clients._build_clients()

    assert clients.REGISTRY_DEGRADED_REASON
    assert "NexoraDB down" in clients.REGISTRY_DEGRADED_REASON


def test_degraded_reason_is_recorded_even_with_logging_disabled(monkeypatch):
    """Nothing may be logged this early -- the flag still has to be set."""
    monkeypatch.setattr(clients, "engine_nexora_db", _dead_engine("no logging yet"))
    monkeypatch.setattr(clients, "REGISTRY_DEGRADED_REASON", None)
    logging.disable(logging.CRITICAL)
    try:
        clients._build_clients()
    finally:
        logging.disable(logging.NOTSET)

    assert "no logging yet" in clients.REGISTRY_DEGRADED_REASON


def test_successful_load_clears_the_degraded_reason(monkeypatch):
    eng, _conn = _engine_with([_row()])
    monkeypatch.setattr(clients, "engine_nexora_db", eng)
    monkeypatch.setattr(clients, "REGISTRY_DEGRADED_REASON", "stale from an earlier build")

    clients._build_clients()

    assert clients.REGISTRY_DEGRADED_REASON is None


def test_a_skipped_row_is_not_a_registry_wide_degradation(monkeypatch):
    """A single unresolvable row is the documented degrade-gracefully contract,
    not a registry failure -- /admin/clients marks that row 'configured, not
    loaded' instead of showing the red banner."""
    eng, _conn = _engine_with([_row(), _row(client_code="ms02", runtime_engine_key="nope")])
    monkeypatch.setattr(clients, "engine_nexora_db", eng)
    monkeypatch.setattr(clients, "REGISTRY_DEGRADED_REASON", None)

    result = clients._build_clients()

    assert set(result) == {"default"}
    assert clients.REGISTRY_DEGRADED_REASON is None


def test_secret_ref_resolves_ms02_prefixed_env_keys(monkeypatch):
    from nx_lib import config as cfg

    monkeypatch.setattr(cfg, "MS02_OCTO_DOMAIN", "ms02.example")
    monkeypatch.setattr(cfg, "MS02_OCTO_CLIENT_ID", "MS02_ID")
    monkeypatch.setattr(cfg, "MS02_OCTO_CLIENT_SECRET", "MS02_SECRET")
    monkeypatch.setattr(cfg, "MS02_OCTO_GRANT_TYPE", "client_credentials")

    domain, client_id, secret, grant_type = clients._creds_for("MS02")

    assert domain == "ms02.example"
    assert client_id == "MS02_ID"
    assert secret == "MS02_SECRET"
    assert grant_type == "client_credentials"


def test_secret_ref_null_resolves_unprefixed_octo_keys(monkeypatch):
    from nx_lib import config as cfg

    monkeypatch.setattr(cfg, "OCTO_DOMAIN", "default.example")
    monkeypatch.setattr(cfg, "OCTO_CLIENT_ID", "DEF_ID")
    monkeypatch.setattr(cfg, "OCTO_CLIENT_SECRET", "DEF_SECRET")
    monkeypatch.setattr(cfg, "OCTO_GRANT_TYPE", "client_credentials")

    domain, client_id, secret, grant_type = clients._creds_for(None)

    assert domain == "default.example"
    assert client_id == "DEF_ID"
    assert secret == "DEF_SECRET"
    assert grant_type == "client_credentials"


def test_octo_creds_for_domain_unchanged_for_unknown_domain(monkeypatch):
    """Regression guard: unknown-domain fallback still returns the module-level
    cfg.OCTO_* creds directly (not e.g. CLIENTS['default'])."""
    from nx_lib import config as cfg

    monkeypatch.setattr(cfg, "OCTO_CLIENT_ID", "MODULE_ID")
    monkeypatch.setattr(cfg, "OCTO_CLIENT_SECRET", "MODULE_SECRET")
    monkeypatch.setattr(cfg, "OCTO_GRANT_TYPE", "client_credentials")

    cid, secret, grant = clients.octo_creds_for_domain("still-nobody.example")

    assert (cid, secret, grant) == ("MODULE_ID", "MODULE_SECRET", "client_credentials")
