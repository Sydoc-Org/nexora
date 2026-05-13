"""Unit tests for nx_lib.security — pure logic, no DB."""

from unittest.mock import patch

from nx_lib.security import has_permission


def test_has_permission_returns_true_when_present():
    with patch("nx_lib.security.session", {"permissions": ["admin.view"]}):
        assert has_permission("admin.view") is True


def test_has_permission_returns_false_when_missing():
    with patch("nx_lib.security.session", {"permissions": ["dashboard.view"]}):
        assert has_permission("admin.delete") is False


def test_has_permission_returns_false_when_no_permissions_in_session():
    with patch("nx_lib.security.session", {}):
        assert has_permission("admin.view") is False
