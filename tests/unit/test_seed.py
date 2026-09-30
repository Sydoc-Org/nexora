"""nx_lib/seed.py -- the INT-only seeding module behind scripts/seed-int-db.py
and the admin overview's Seed / Clear buttons. Pure parts only; nothing here
touches a database."""

import random
import types

import pytest

from nx_lib import seed as seedlib

# ------------------------------- guards -------------------------------------


def test_refuses_outside_int(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "STAGING")
    assert "expected 'INT'" in (seedlib.seed_refusal() or "")


def test_refuses_production_looking_server(monkeypatch):
    """The trap: the var is DB_SERVER_PRD everywhere, so the check is on the
    resolved VALUE. A server called PRDSQL01 is refused even under INT."""
    monkeypatch.setenv("ENVIRONMENT", "INT")
    monkeypatch.setattr(
        "nx_lib.config",
        types.SimpleNamespace(DB_SERVER_PRD="PRDSQL01", DB_STATISTICS="SYDOC_Statistik"),
    )
    assert "looks like production" in (seedlib.seed_refusal() or "")


def test_allows_int_server(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "INT")
    monkeypatch.setattr(
        "nx_lib.config",
        types.SimpleNamespace(DB_SERVER_PRD="INTSQL01", DB_STATISTICS="SYDOC_Statistik"),
    )
    assert seedlib.seed_refusal() is None


def test_run_seed_raises_when_refused(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "PROD")
    with pytest.raises(seedlib.SeedRefusedError):
        seedlib.run_seed("backlog-history", 14, apply_it=False)
    with pytest.raises(seedlib.SeedRefusedError):
        seedlib.clear_seeds()


def test_run_seed_rejects_unknown_seeder_and_short_window(monkeypatch):
    monkeypatch.setattr(seedlib, "seed_refusal", lambda: None)
    with pytest.raises(seedlib.SeedRefusedError, match="unknown seeder"):
        seedlib.run_seed("nope", 14, apply_it=False)
    with pytest.raises(seedlib.SeedRefusedError, match="at least 2"):
        seedlib.run_seed("backlog-history", 1, apply_it=False)


# ------------------------------- random walk --------------------------------


def test_random_walk_today_equals_live_and_stays_in_band():
    """Mean-reverting: over 90 days the series must neither collapse to zero
    nor run away -- that would be as useless for verification as an empty
    table."""
    walk = seedlib.random_walk(200, 90, random.Random(7))
    assert len(walk) == 90
    assert walk[0] == 200
    assert all(80 <= v <= 400 for v in walk), (min(walk), max(walk))


def test_random_walk_never_negative_and_floors_zero_today():
    walk = seedlib.random_walk(0, 5, random.Random(1))
    assert walk[0] == 1  # max(1, ...) so a dead pair still draws a line
    assert all(v >= 0 for v in walk)


# ------------------------------- apply / clear plumbing ---------------------


def test_run_seed_dry_run_writes_nothing(monkeypatch):
    monkeypatch.setattr(seedlib, "seed_refusal", lambda: None)
    calls = []

    def fake_plan(days, rng, report):
        report.rows.extend({"a": f"2026-09-{d + 1:02d} 20:00:00", "n": d} for d in range(days))

    spec = seedlib.Seeder(
        name="fake",
        table="dbo.Fake",
        doc="fake",
        plan=fake_plan,
        write=lambda rows: calls.append(("write", len(rows))) or len(rows),
        delete=lambda rows: calls.append(("delete", len(rows))) or len(rows),
    )
    monkeypatch.setattr(seedlib, "SEEDERS", {"fake": spec})
    monkeypatch.setattr(seedlib, "_record_run", lambda *a, **k: pytest.fail("recorded a dry run"))

    report = seedlib.run_seed("fake", 3, apply_it=False)
    assert report.applied is False
    assert len(report.rows) == 3
    assert calls == []


def test_run_seed_apply_clears_own_runs_then_records_then_writes(monkeypatch):
    """Order matters: the run is recorded BEFORE the insert so a crash
    mid-insert still leaves a run whose clear removes whatever landed."""
    monkeypatch.setattr(seedlib, "seed_refusal", lambda: None)
    order = []

    def fake_plan(days, rng, report):
        report.rows.extend({"n": d} for d in range(days))

    spec = seedlib.Seeder(
        name="fake",
        table="dbo.Fake",
        doc="fake",
        plan=fake_plan,
        write=lambda rows: order.append("write") or len(rows),
        delete=lambda rows: order.append("delete") or len(rows),
    )
    monkeypatch.setattr(seedlib, "SEEDERS", {"fake": spec})
    monkeypatch.setattr(
        seedlib,
        "clear_seeds",
        lambda seeder=None: order.append(f"clear:{seeder}") or {"runs": 1, "rows": 4},
    )
    monkeypatch.setattr(seedlib, "_record_run", lambda *a, **k: order.append("record") or 42)

    report = seedlib.run_seed("fake", 2, apply_it=True, seeded_by="tester")
    assert order == ["clear:fake", "record", "write"]
    assert report.run_id == 42
    assert report.inserted == 2
    assert report.cleared_rows == 4
    assert report.to_dict()["planned"] == 2


def test_backlog_delete_matches_every_written_column():
    """The clear must only ever hit rows that still look exactly like what was
    seeded -- every column of the insert is in the delete's WHERE."""
    sql = str(seedlib._BACKLOG_DELETE)
    for col in ("SnapshotAt", "SourceCode", "ClientName", "ProcessName", "BacklogCount"):
        assert col in sql
    # ISO string cast server-side: the legacy ODBC driver cannot bind dates.
    assert "CAST(:a AS DATETIME2(0))" in sql
