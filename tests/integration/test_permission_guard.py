"""Integration tests verifying that @require_permission denies unauthorised users."""

ADMIN_ROUTE = (
    "/admin"  # guarded by @require_permission("admin.view") in nx_lib/views/admin/overview.py
)


def test_protected_route_denies_noperm_user(login):
    client = login(username="noperm@test.local")
    resp = client.get(ADMIN_ROUTE)
    assert resp.status_code == 403, f"expected 403, got {resp.status_code}"


def test_protected_route_allows_admin_user(login):
    client = login(username="admin@test.local")
    resp = client.get(ADMIN_ROUTE)
    # 200 if route renders normally; 302 if the view itself redirects (e.g. to a sub-page).
    # 403 would mean the admin seed is missing admin.view.
    assert resp.status_code in (200, 302), f"admin denied: {resp.status_code}"
