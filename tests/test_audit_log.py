"""
Audit log: who did what, when and from which IP address.
"""

import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.auth as auth

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACKED_DB = PROJECT_ROOT / "database" / "snp_platform.db"


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "audit_test.db"
    shutil.copy(TRACKED_DB, path)
    monkeypatch.setattr(auth, "DATABASE_PATH", path)
    monkeypatch.setattr(auth, "get_client_info", lambda: ("203.0.113.7", "TestBrowser/1.0"))
    return path


def _rows(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM AdminActionLog ORDER BY log_id")]


def test_old_log_table_is_migrated_without_losing_rows(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE AdminActionLog (log_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "username TEXT, action TEXT NOT NULL, details TEXT, created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO AdminActionLog (username, action, details, created_at) "
                     "VALUES ('old', 'create_user_account', '', '2026-01-01T00:00:00')")
    monkeypatch.setattr(auth, "DATABASE_PATH", path)
    auth.ensure_user_account_table()
    logs = auth.get_admin_action_logs()
    assert list(logs["username"]) == ["old"]
    assert {"ip_address", "user_agent", "category"} <= set(logs.columns)


def test_every_row_records_ip_browser_and_category(db):
    auth.log_admin_action("lana", "data_final_merge", "source_id=S1")
    row = _rows(db)[-1]
    assert (row["ip_address"], row["user_agent"], row["category"]) == ("203.0.113.7", "TestBrowser/1.0", "data")


@pytest.mark.parametrize("action, category", [
    ("login_failed", "login"), ("logout", "login"), ("self_register_user", "account"),
    ("create_user_account", "account"), ("data_file_uploaded", "data"), ("data_rollback", "data"),
    ("library_submit", "community"), ("community_hide", "community"), ("ai_model_applied", "system"),
    ("something_new", "other"),
])
def test_actions_are_grouped_into_categories(action, category):
    assert auth.audit_category(action) == category


def test_logins_are_logged_with_the_reason(db):
    auth.create_user("student1", "correct-pass-1", role="user")
    assert auth.authenticate_user("student1", "wrong-pass-11") is None
    assert auth.authenticate_user("nobody", "whatever-123") is None
    assert auth.authenticate_user("student1", "correct-pass-1")
    events = [(r["username"], r["action"], r["details"]) for r in _rows(db)]
    assert ("student1", "login_failed", "Wrong password.") in events
    assert ("nobody", "login_failed", "Unknown username.") in events
    assert events[-1][:2] == ("student1", "login_success")
    assert all(r["ip_address"] == "203.0.113.7" for r in _rows(db))


def test_locked_out_attempts_are_logged(db):
    auth.create_user("student2", "correct-pass-2", role="user")
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        auth.authenticate_user("student2", "wrong-pass-22")
    with pytest.raises(auth.LoginLockedError):
        auth.authenticate_user("student2", "correct-pass-2")
    assert _rows(db)[-1]["action"] == "login_blocked_locked"


def test_self_registration_is_logged(db, monkeypatch):
    monkeypatch.setattr(auth, "registration_enabled", lambda: True)
    auth.self_register_user("newstudent", "a-good-pass-1")
    actions = [r["action"] for r in _rows(db) if r["username"] == "newstudent"]
    assert actions[:2] == ["self_register_user", "login_success"]


def test_a_broken_log_never_breaks_the_action(monkeypatch):
    def boom(*_args, **_kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(auth, "log_admin_action", boom)
    auth.safe_log_admin_action("lana", "data_rollback", "")  # must not raise


def test_client_ip_prefers_the_original_client_behind_proxies(monkeypatch):
    fake = SimpleNamespace(headers={"X-Forwarded-For": "198.51.100.4, 10.0.0.1", "User-Agent": "Firefox"},
                           ip_address="10.0.0.1")
    monkeypatch.setattr(auth.st, "context", fake, raising=False)
    assert auth.get_client_info() == ("198.51.100.4", "Firefox")


def test_client_ip_falls_back_to_the_socket_address(monkeypatch):
    fake = SimpleNamespace(headers={"User-Agent": "Edge"}, ip_address="192.0.2.9")
    monkeypatch.setattr(auth.st, "context", fake, raising=False)
    assert auth.get_client_info() == ("192.0.2.9", "Edge")


def test_local_sessions_are_recorded_as_loopback(monkeypatch):
    fake = SimpleNamespace(headers={"Host": "localhost:8510", "User-Agent": "Chrome"}, ip_address=None)
    monkeypatch.setattr(auth.st, "context", fake, raising=False)
    assert auth.get_client_info() == ("127.0.0.1", "Chrome")


def test_admin_views_log_every_data_operation():
    """Each data-changing button in the admin dashboard writes an audit row."""
    source = (PROJECT_ROOT / "app" / "views" / "admin.py").read_text(encoding="utf-8")
    for action in ("data_file_uploaded", "data_file_processed", "data_processing_failed",
                   "data_source_approved", "data_source_rejected", "data_online_update",
                   "data_final_merge", "data_rollback", "data_registry_saved"):
        assert f'"{action}"' in source, action
