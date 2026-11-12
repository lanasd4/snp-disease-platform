"""
Security regression tests: credentials, accounts, password hashing, login throttling.
"""

import hashlib
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

import core.auth as auth

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACKED_DB = PROJECT_ROOT / "database" / "snp_platform.db"
KNOWN_LEAKED_PASSWORD = "Admin" + "@12345"  # split so this file is not itself a match


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Fresh copy of the published database for each test."""
    path = tmp_path / "auth_test.db"
    shutil.copy(TRACKED_DB, path)
    monkeypatch.setattr(auth, "DATABASE_PATH", path)
    for key in ("SNP_ADMIN_USERNAME", "SNP_ADMIN_PASSWORD", "SNP_ALLOW_REGISTRATION"):
        monkeypatch.delenv(key, raising=False)
    return path


def _users(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT username, role, must_change_password FROM UserAccount").fetchall()


# --- nothing secret is shipped -------------------------------------------------

def test_no_hardcoded_admin_password_in_code():
    offenders = []
    for folder in ("app", "core", "pipeline"):
        for path in (PROJECT_ROOT / folder).rglob("*.py"):
            if KNOWN_LEAKED_PASSWORD in path.read_text(encoding="utf-8"):
                offenders.append(str(path))
    assert not offenders


def test_published_docs_do_not_contain_the_old_password():
    tracked = subprocess.run(
        ["git", "ls-files", "docs", "README.md"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    offenders = [f for f in tracked if KNOWN_LEAKED_PASSWORD in (PROJECT_ROOT / f).read_text(encoding="utf-8")]
    assert not offenders


def test_published_database_has_no_accounts_or_history():
    with sqlite3.connect(TRACKED_DB) as conn:
        for table in ("UserAccount", "UserSearchHistory", "AdminActionLog", "LoginThrottle"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


# --- first-admin bootstrap -------------------------------------------------------

def test_no_admin_is_created_without_settings(db):
    assert auth.ensure_bootstrap_admin() is False
    assert _users(db) == []


def test_admin_is_created_from_settings(db, monkeypatch):
    monkeypatch.setenv("SNP_ADMIN_USERNAME", "owner")
    monkeypatch.setenv("SNP_ADMIN_PASSWORD", "a-strong-pass-123")
    assert auth.ensure_bootstrap_admin() is True
    assert _users(db) == [("owner", "admin", 0)]
    assert auth.authenticate_user("owner", "a-strong-pass-123")["role"] == "admin"
    # Second call is a no-op once an active admin exists.
    assert auth.ensure_bootstrap_admin() is False


def test_bootstrap_never_takes_over_an_existing_account(db, monkeypatch):
    auth.create_user("owner", "user-password-1", role="user")
    auth.create_user("boss", "admin-password-1", role="admin", is_active=0)
    monkeypatch.setenv("SNP_ADMIN_USERNAME", "owner")
    monkeypatch.setenv("SNP_ADMIN_PASSWORD", "attacker-pass-1")
    assert auth.ensure_bootstrap_admin() is False
    assert auth.authenticate_user("owner", "attacker-pass-1") is None


# --- input validation ----------------------------------------------------------

@pytest.mark.parametrize("name", ["ab", "<script>x</script>", "a b", "[x](http://e.vil)", "x" * 33, "علي"])
def test_invalid_usernames_are_rejected(db, name):
    with pytest.raises(ValueError):
        auth.create_user(name, "valid-password-1")


@pytest.mark.parametrize("name", ["lana", "dr.kinan", "user_01", "a-b"])
def test_valid_usernames_are_accepted(db, name):
    auth.create_user(name, "valid-password-1")


@pytest.mark.parametrize("password", ["", "short", "x" * 129])
def test_password_length_limits(db, password):
    with pytest.raises(ValueError):
        auth.create_user("someone", password)


def test_self_registration_creates_user_role_only(db):
    user = auth.self_register_user("newbie", "valid-password-1")
    assert user["role"] == "user"


def test_self_registration_can_be_disabled(db, monkeypatch):
    monkeypatch.setenv("SNP_ALLOW_REGISTRATION", "false")
    with pytest.raises(ValueError):
        auth.self_register_user("newbie", "valid-password-1")


# --- password storage and login -------------------------------------------------

def test_hash_is_salted_pbkdf2_with_current_iterations():
    first, second = auth.hash_password("same-password"), auth.hash_password("same-password")
    assert first != second
    algorithm, iterations, _, _ = first.split("$")
    assert algorithm == "pbkdf2_sha256"
    assert int(iterations) == auth.HASH_ITERATIONS >= 600_000


def test_old_hash_is_upgraded_on_login(db):
    salt = bytes(16)
    old_digest = hashlib.pbkdf2_hmac("sha256", b"legacy-password", salt, 150_000).hex()
    old_hash = f"pbkdf2_sha256$150000${salt.hex()}${old_digest}"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO UserAccount (username, password_hash, role, is_active, created_at) "
            "VALUES ('legacy', ?, 'user', 1, '2026-01-01')",
            (old_hash,),
        )
    assert auth.authenticate_user("legacy", "legacy-password") is not None
    with sqlite3.connect(db) as conn:
        new_hash = conn.execute("SELECT password_hash FROM UserAccount WHERE username='legacy'").fetchone()[0]
    assert new_hash.split("$")[1] == str(auth.HASH_ITERATIONS)
    assert auth.authenticate_user("legacy", "legacy-password") is not None


def test_wrong_password_and_unknown_user_fail(db):
    auth.create_user("member", "right-password-1")
    assert auth.authenticate_user("member", "wrong-password") is None
    assert auth.authenticate_user("ghost", "whatever-123") is None


def test_login_is_locked_after_repeated_failures(db):
    auth.create_user("member", "right-password-1")
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        auth.authenticate_user("member", "wrong-password")
    with pytest.raises(auth.LoginLockedError):
        auth.authenticate_user("member", "right-password-1")


def test_admin_reset_forces_password_change(db):
    auth.create_user("member", "right-password-1")
    user_id = auth.get_user_by_username("member")["user_id"]
    auth.reset_user_password(user_id, "temporary-pass-1", actor_username="owner")
    assert _users(db) == [("member", "user", 1)]


def test_disabled_account_cannot_log_in(db):
    auth.create_user("member", "right-password-1", is_active=0)
    assert auth.authenticate_user("member", "right-password-1") is None


def test_sql_injection_in_username_is_harmless(db):
    auth.create_user("member", "right-password-1")
    assert auth.authenticate_user("member' OR '1'='1", "anything") is None
    assert re.fullmatch(r"\d+", str(auth._count_active_admins()))


def test_template_password_is_never_used(db, monkeypatch):
    monkeypatch.setenv("SNP_ADMIN_USERNAME", "owner")
    monkeypatch.setenv("SNP_ADMIN_PASSWORD", "CHANGE-ME-before-first-run")
    assert auth.ensure_bootstrap_admin() is False
    assert _users(db) == []
