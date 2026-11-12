"""
Render every page of the real app (guest and admin) and fail on any exception.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ENTRY = str(Path(__file__).resolve().parents[1] / "app" / "main.py")
NAV_KEY = "main_navigation_display"
TIMEOUT = 120


def _new_app(admin: bool) -> AppTest:
    at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT)
    if admin:
        at.session_state["auth_user"] = {
            "user_id": 0, "username": "test_admin", "role": "admin", "must_change_password": 0,
        }
        at.session_state["auth_role"] = "admin"
    return at.run()


def _page_count(admin: bool) -> int:
    return len(_new_app(admin).sidebar.radio(key=NAV_KEY).options)


GUEST_PAGES = range(_page_count(admin=False))
ADMIN_PAGES = range(_page_count(admin=True))


def _render(page_index: int, admin: bool) -> AppTest:
    at = _new_app(admin)
    radio = at.sidebar.radio(key=NAV_KEY)
    radio.set_value(radio.options[page_index]).run()
    return at


@pytest.mark.parametrize("page_index", GUEST_PAGES)
def test_guest_page_renders(page_index):
    at = _render(page_index, admin=False)
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("page_index", ADMIN_PAGES)
def test_admin_page_renders(page_index):
    at = _render(page_index, admin=True)
    assert not at.exception, [e.value for e in at.exception]


def _snapshot_project_files():
    root = Path(__file__).resolve().parents[1]
    return {
        path: path.stat().st_mtime_ns
        for folder in ("data", "outputs", "database")
        for path in (root / folder).rglob("*")
        if path.is_file()
    }


def test_rendering_pages_does_not_modify_project_files():
    before = _snapshot_project_files()
    for page_index in ADMIN_PAGES:
        _render(page_index, admin=True)
    after = _snapshot_project_files()
    changed = sorted(str(p) for p in set(before) | set(after) if before.get(p) != after.get(p))
    assert not changed, changed


def test_admin_page_hidden_from_guests():
    assert _page_count(admin=True) == _page_count(admin=False) + 1
