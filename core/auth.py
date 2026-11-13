
"""
Admin Authentication and Role-Based Access
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import hmac
import os
import sqlite3
import time
from typing import Optional, Dict, Any

import re

import streamlit as st
from core.paths import DATABASE_PATH
from core.settings import (
    ADMIN_PASSWORD_KEY,
    ADMIN_USERNAME_KEY,
    get_setting,
    registration_enabled,
)


ALLOWED_ROLES = {"admin", "user", "guest"}
HASH_NAME = "sha256"
# OWASP 2023 recommendation for PBKDF2-HMAC-SHA256.
HASH_ITERATIONS = 600_000

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# Login throttling: after this many consecutive failed attempts for a username, further attempts are...
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300


class LoginLockedError(RuntimeError):
    """Raised when a username is temporarily locked out after too many failed attempts."""


def validate_username(username: str) -> str:
    """Return the stripped username or raise ValueError if it is not allowed."""
    username = (username or "").strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "Username must be 3-32 characters: English letters, digits, dot, dash or underscore."
        )
    return username


def validate_new_password(password: str) -> str:
    """Raise ValueError unless the password length is within the allowed range."""
    password = password or ""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters.")
    return password


def get_database_path() -> Path:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_database_path(), timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_user_account_table() -> None:
    """Create UserAccount and AdminActionLog tables if they do not exist."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS UserAccount (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user', 'guest')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
                created_at TEXT NOT NULL,
                last_login TEXT
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS AdminActionLog (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(UserAccount)").fetchall()
        }

        if "must_change_password" not in existing_columns:
            conn.execute(
                "ALTER TABLE UserAccount "
                "ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"
            )

        conn.commit()


def ensure_login_throttle_table() -> None:
    """Create the LoginThrottle table (failed-attempt tracking) if missing."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS LoginThrottle (
                username TEXT PRIMARY KEY,
                fail_count INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT
            );
            """
        )
        conn.commit()


def _get_throttle_row(username: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT username, fail_count, locked_until FROM LoginThrottle WHERE username = ?",
            (username,),
        ).fetchone()

    return dict(row) if row else None


def is_login_locked(username: str) -> Optional[float]:
    """Return remaining lockout seconds for `username`, or None if not locked."""
    ensure_login_throttle_table()

    row = _get_throttle_row(username)

    if not row or not row.get("locked_until"):
        return None

    try:
        locked_until = datetime.fromisoformat(row["locked_until"])
    except Exception:
        return None

    remaining = (locked_until - datetime.now()).total_seconds()

    return remaining if remaining > 0 else None


def record_login_failure(username: str) -> None:
    """Increment the failed-attempt counter and lock the username out if it hits the limit."""
    ensure_login_throttle_table()

    row = _get_throttle_row(username)
    fail_count = (row["fail_count"] if row else 0) + 1
    locked_until = None

    if fail_count >= LOGIN_MAX_ATTEMPTS:
        locked_until = (
            datetime.now() + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)
        ).isoformat(timespec="seconds")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO LoginThrottle (username, fail_count, locked_until)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                fail_count = excluded.fail_count,
                locked_until = excluded.locked_until
            """,
            (username, fail_count, locked_until),
        )
        conn.commit()


def reset_login_throttle(username: str) -> None:
    """Clear the failed-attempt counter for `username` after a successful login."""
    ensure_login_throttle_table()

    with get_connection() as conn:
        conn.execute("DELETE FROM LoginThrottle WHERE username = ?", (username,))
        conn.commit()


def hash_password(password: str) -> str:
    """Return salted PBKDF2 password hash."""
    validate_new_password(password)

    salt = os.urandom(16)

    digest = hashlib.pbkdf2_hmac(
        HASH_NAME,
        password.encode("utf-8"),
        salt,
        HASH_ITERATIONS,
    )

    return f"pbkdf2_{HASH_NAME}${HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify plaintext password against stored PBKDF2 hash."""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)

        if algorithm != f"pbkdf2_{HASH_NAME}":
            return False

        new_digest = hashlib.pbkdf2_hmac(
            HASH_NAME,
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        ).hex()

        return hmac.compare_digest(new_digest, digest_hex)

    except Exception:
        return False


def _hash_needs_upgrade(stored_hash: str) -> bool:
    try:
        return int(stored_hash.split("$", 3)[1]) < HASH_ITERATIONS
    except (IndexError, ValueError):
        return False


# Hash compared against when the username does not exist, so a failed login
# takes the same time whether or not the account exists.
_DUMMY_HASH = f"pbkdf2_{HASH_NAME}${HASH_ITERATIONS}${'00' * 16}${'00' * 32}"


def log_admin_action(username: str, action: str, details: str = "") -> None:
    ensure_user_account_table()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO AdminActionLog (username, action, details, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                action,
                details,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()


def create_user(username: str, password: str, role: str = "user", is_active: int = 1) -> None:
    """Create new user account."""
    ensure_user_account_table()

    username = validate_username(username)
    role = role.strip().lower()

    if role not in ALLOWED_ROLES:
        raise ValueError(f"Invalid role: {role}")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO UserAccount
                (username, password_hash, role, is_active, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (
                username,
                hash_password(password),
                role,
                int(is_active),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    ensure_user_account_table()

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT user_id, username, password_hash, role, is_active, created_at,
                   last_login, must_change_password
            FROM UserAccount
            WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()

    return dict(row) if row else None


def ensure_bootstrap_admin() -> bool:
    """Create the first admin from the SNP_ADMIN_USERNAME / SNP_ADMIN_PASSWORD"""
    ensure_user_account_table()

    username = (get_setting(ADMIN_USERNAME_KEY) or "").strip()
    password = get_setting(ADMIN_PASSWORD_KEY) or ""

    if not username or not password or _count_active_admins() > 0:
        return False

    if password.upper().startswith("CHANGE-ME"):
        # Template value from .streamlit/secrets.toml was never replaced.
        return False

    if get_user_by_username(username):
        # The name is taken by a non-admin or disabled account: never
        # silently promote or overwrite an existing account.
        return False

    create_user(username, password, role="admin", is_active=1)
    log_admin_action(username, "create_bootstrap_admin", "First admin created from deployment settings.")
    return True


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    username = (username or "").strip()
    password = password or ""

    if not username or not password:
        return None

    remaining_lock_seconds = is_login_locked(username)

    if remaining_lock_seconds is not None:
        wait_minutes = int(remaining_lock_seconds // 60) + 1
        raise LoginLockedError(
            f"Too many failed login attempts for '{username}'. "
            f"Try again in about {wait_minutes} minute(s)."
        )

    user = get_user_by_username(username)

    if not user:
        verify_password(password, _DUMMY_HASH)
        record_login_failure(username)
        return None

    if int(user.get("is_active", 0)) != 1:
        record_login_failure(username)
        return None

    if not verify_password(password, user.get("password_hash", "")):
        record_login_failure(username)
        return None

    reset_login_throttle(username)

    if _hash_needs_upgrade(user.get("password_hash", "")):
        with get_connection() as conn:
            conn.execute(
                "UPDATE UserAccount SET password_hash = ? WHERE user_id = ?",
                (hash_password(password), user["user_id"]),
            )
            conn.commit()

    login_time = datetime.now().isoformat(timespec="seconds")

    last_login_saved = False
    for attempt in range(3):
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE UserAccount SET last_login = ? WHERE user_id = ?",
                    (login_time, user["user_id"]),
                )
                conn.commit()
            last_login_saved = True
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 2:
                break
            time.sleep(0.08 * (attempt + 1))

    if last_login_saved:
        user["last_login"] = login_time
    user.pop("password_hash", None)

    return user


def init_auth_state() -> None:
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None

    if "auth_role" not in st.session_state:
        st.session_state.auth_role = "guest"

    if "auth_login_error" not in st.session_state:
        st.session_state.auth_login_error = ""


def login_user(user: Dict[str, Any]) -> None:
    st.session_state["auth_user"] = dict(user)
    st.session_state["auth_role"] = user.get("role", "guest")
    st.session_state["auth_login_error"] = ""


def logout_user() -> None:
    st.session_state["auth_user"] = None
    st.session_state["auth_role"] = "guest"
    st.session_state["auth_login_error"] = ""


def get_current_role() -> str:
    init_auth_state()
    return st.session_state.get("auth_role", "guest") or "guest"


def get_current_user() -> Optional[Dict[str, Any]]:
    init_auth_state()
    return st.session_state.get("auth_user")


def is_admin() -> bool:
    return get_current_role() == "admin"


def _rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def render_auth_sidebar() -> None:
    """Render login/logout and user self-registration controls inside the Streamlit sidebar."""
    init_auth_state()

    from core.i18n import t  # local import avoids a hard dependency for non-UI callers

    user = get_current_user()

    st.sidebar.markdown(f"### {t('auth.account')}")

    if user:
        role = get_current_role()

        st.sidebar.success(f"{t('auth.logged_in_as')}: {user.get('username')} ({role})")

        if st.sidebar.button(
            t('common.logout'),
            width="stretch",
            key="auth_logout_btn"
        ):
            logout_user()
            _rerun()

        return

    with st.sidebar.expander(t('common.login'), expanded=False):
        with st.form("auth_login_form", clear_on_submit=False):
            username = st.text_input(t('common.username'), key="auth_username")
            password = st.text_input(t('common.password'), type="password", key="auth_password")
            submitted = st.form_submit_button(t('common.login'), width="stretch")

        if submitted:
            try:
                user_record = authenticate_user(username.strip(), password)
            except LoginLockedError as exc:
                user_record = None
                st.session_state["auth_login_error"] = f"{t('auth.login_locked_prefix')} ({exc})"

            if user_record:
                login_user(user_record)
                st.success(t('auth.login_success'))
                _rerun()
            elif not st.session_state.get("auth_login_error"):
                st.session_state["auth_login_error"] = t('auth.login_invalid')

            if not user_record:
                st.error(st.session_state["auth_login_error"])
        elif st.session_state.get("auth_login_error"):
            st.error(st.session_state["auth_login_error"])

    if not registration_enabled():
        return

    with st.sidebar.expander(t('auth.create_account'), expanded=False):
        st.caption(t('auth.register_self_note'))
        from core.userdb import backend

        if backend() == "sqlite" and get_setting("SNP_TRIAL_NOTICE", "true").strip().lower() in {"1", "true", "yes"}:
            st.info(t('auth.trial_notice'))

        reg_username = st.text_input(
            t('auth.new_username'),
            key="auth_register_username"
        )

        reg_password = st.text_input(
            t('auth.new_password'),
            type="password",
            key="auth_register_password"
        )

        reg_confirm = st.text_input(
            t('auth.confirm_password'),
            type="password",
            key="auth_register_confirm"
        )

        if st.button(
            t('auth.create_account'),
            width="stretch",
            key="auth_register_user_btn"
        ):
            if not reg_username.strip():
                st.error(t('auth.username_required'))
            elif len(reg_password) < PASSWORD_MIN_LENGTH:
                st.error(t('auth.password_min_length'))
            elif reg_password != reg_confirm:
                st.error(t('auth.password_mismatch'))
            else:
                try:
                    user_record = self_register_user(reg_username, reg_password)
                    login_user(user_record)
                    st.success(t('auth.register_success'))
                    _rerun()
                except Exception as exc:
                    st.error(f"{t('auth.register_failed_prefix')}: {exc}")


def render_user_status_card() -> None:
    """Render user status card using the existing sidebar card style."""
    init_auth_state()

    from html import escape as _esc
    from core.i18n import t

    user = get_current_user()
    role = get_current_role()

    if user:
        title = user.get("username", "User")
        subtitle = f"{t('auth.role_label')}: {role}"
        plan = t('auth.role_admin_console') if role == "admin" else t('auth.role_research_user')
        avatar = "🛡️" if role == "admin" else "👤"
    else:
        title = t('common.guest_user')
        subtitle = ""
        plan = t('auth.explorer_plan')
        avatar = "●"

    st.sidebar.markdown(
        f"""
        <div class="guest-card">
            <div style="display:flex; align-items:center;">
                <div class="guest-avatar">{avatar}</div>
                <div>
                    <div class="guest-title">{_esc(str(title))}</div>
                    <div class="guest-subtitle">{_esc(str(subtitle))}</div>
                </div>
            </div>
            <div class="guest-plan">{_esc(str(plan))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_force_password_change_gate() -> bool:
    """Block the rest of the app behind a mandatory password-change form when required."""
    init_auth_state()

    from core.i18n import t

    user = get_current_user()

    if not user or not int(user.get("must_change_password", 0) or 0):
        return False

    st.warning(t('auth.must_change_password_warning'))

    with st.form("force_password_change_form", clear_on_submit=False):
        current_password = st.text_input(t('auth.current_password'), type="password")
        new_password = st.text_input(t('auth.new_password_min8'), type="password")
        confirm_password = st.text_input(t('auth.confirm_new_password'), type="password")
        submitted = st.form_submit_button(t('auth.change_password_button'))

    if submitted:
        if new_password != confirm_password:
            st.error(t('auth.new_password_mismatch'))
        else:
            try:
                change_own_password(user["user_id"], current_password, new_password)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["auth_user"]["must_change_password"] = 0
                st.success(t('auth.password_changed_success'))
                _rerun()

    return True


# User/Admin Management helpers for Admin Dashboard

def _count_active_admins() -> int:
    ensure_user_account_table()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) 
            FROM UserAccount 
            WHERE role = 'admin' AND is_active = 1
            """
        ).fetchone()

    return int(row[0]) if row else 0


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    ensure_user_account_table()

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT user_id, username, password_hash, role, is_active, created_at,
                   last_login, must_change_password
            FROM UserAccount
            WHERE user_id = ?
            """,
            (int(user_id),)
        ).fetchone()

    return dict(row) if row else None


def list_users(include_password_hash: bool = False):
    """Return platform users as a pandas DataFrame."""
    import pandas as pd

    ensure_user_account_table()

    if include_password_hash:
        query = """
        SELECT user_id, username, password_hash, role, is_active, created_at, last_login
        FROM UserAccount
        ORDER BY user_id;
        """
    else:
        query = """
        SELECT user_id, username, role, is_active, created_at, last_login
        FROM UserAccount
        ORDER BY user_id;
        """

    with get_connection() as conn:
        return pd.read_sql_query(query, conn)


def create_user_account(
    username: str,
    password: str,
    role: str = "user",
    is_active: int = 1,
    actor_username: str = "admin"
) -> None:
    """Create a user account and log the action."""
    create_user(username=username, password=password, role=role, is_active=is_active)

    log_admin_action(
        actor_username,
        "create_user_account",
        f"Created username={username.strip()}, role={role}, is_active={int(is_active)}"
    )


def update_user_role(user_id: int, new_role: str, actor_username: str = "admin") -> None:
    """Update user role with protection against removing the last active admin."""
    ensure_user_account_table()

    new_role = new_role.strip().lower()

    if new_role not in ALLOWED_ROLES:
        raise ValueError(f"Invalid role: {new_role}")

    user = get_user_by_id(user_id)

    if not user:
        raise ValueError("User not found.")

    old_role = user["role"]

    if old_role == "admin" and new_role != "admin" and int(user["is_active"]) == 1:
        if _count_active_admins() <= 1:
            raise ValueError("Cannot change role of the last active admin.")

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE UserAccount
            SET role = ?
            WHERE user_id = ?
            """,
            (new_role, int(user_id))
        )
        conn.commit()

    log_admin_action(
        actor_username,
        "update_user_role",
        f"user_id={user_id}, username={user['username']}, old_role={old_role}, new_role={new_role}"
    )


def set_user_active(user_id: int, is_active: int, actor_username: str = "admin") -> None:
    """Enable or disable a user account."""
    ensure_user_account_table()

    is_active = int(is_active)
    if is_active not in [0, 1]:
        raise ValueError("is_active must be 0 or 1.")

    user = get_user_by_id(user_id)

    if not user:
        raise ValueError("User not found.")

    if user["role"] == "admin" and int(user["is_active"]) == 1 and is_active == 0:
        if _count_active_admins() <= 1:
            raise ValueError("Cannot disable the last active admin.")

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE UserAccount
            SET is_active = ?
            WHERE user_id = ?
            """,
            (is_active, int(user_id))
        )
        conn.commit()

    log_admin_action(
        actor_username,
        "set_user_active",
        f"user_id={user_id}, username={user['username']}, is_active={is_active}"
    )


def reset_user_password(user_id: int, new_password: str, actor_username: str = "admin") -> None:
    """Reset user password using the same secure hash function."""
    ensure_user_account_table()

    validate_new_password(new_password)

    user = get_user_by_id(user_id)

    if not user:
        raise ValueError("User not found.")

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE UserAccount
            SET password_hash = ?, must_change_password = 1
            WHERE user_id = ?
            """,
            (hash_password(new_password), int(user_id))
        )
        conn.commit()

    log_admin_action(
        actor_username,
        "reset_user_password",
        f"user_id={user_id}, username={user['username']}"
    )


def change_own_password(user_id: int, current_password: str, new_password: str) -> None:
    """Self-service password change for the logged-in user."""
    ensure_user_account_table()

    user = get_user_by_id(user_id)

    if not user:
        raise ValueError("User not found.")

    if not verify_password(current_password, user.get("password_hash", "")):
        raise ValueError("Current password is incorrect.")

    validate_new_password(new_password)

    if verify_password(new_password, user.get("password_hash", "")):
        raise ValueError("New password must be different from the current password.")

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE UserAccount
            SET password_hash = ?, must_change_password = 0
            WHERE user_id = ?
            """,
            (hash_password(new_password), int(user_id))
        )
        conn.commit()

    log_admin_action(
        user["username"],
        "change_own_password",
        f"user_id={user_id}, username={user['username']}"
    )


def get_admin_action_logs(limit: int = 100):
    """Return recent admin/user management actions."""
    import pandas as pd

    ensure_user_account_table()

    limit = int(limit)

    with get_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT log_id, username, action, details, created_at
            FROM AdminActionLog
            ORDER BY log_id DESC
            LIMIT ?;
            """,
            conn,
            params=(limit,)
        )


# User self-registration and private search history

def ensure_user_search_history_table() -> None:
    """Create a persistent private search history table."""
    ensure_user_account_table()

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS UserSearchHistory (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                search_mode TEXT NOT NULL,
                query TEXT NOT NULL,
                result_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES UserAccount(user_id)
            );
            """
        )
        conn.commit()


def self_register_user(username: str, password: str) -> Dict[str, Any]:
    """Public self-registration."""
    if not registration_enabled():
        raise ValueError("Self-registration is disabled.")

    ensure_user_account_table()
    ensure_user_search_history_table()

    username = validate_username(username)
    validate_new_password(password)

    existing = get_user_by_username(username)

    if existing:
        raise ValueError("Username already exists.")

    create_user(
        username=username,
        password=password,
        role="user",
        is_active=1,
    )

    log_admin_action(
        username,
        "self_register_user",
        "User created an account through self-registration."
    )

    user = authenticate_user(username, password)

    if not user:
        raise ValueError("Account created, but login failed.")

    return user


def save_user_search_history(query: str, search_mode: str, result_count: int) -> None:
    """Save private search history for logged-in users only."""
    ensure_user_search_history_table()

    user = get_current_user()

    if not user:
        return

    role = user.get("role", "guest")

    if role == "guest":
        return

    query = str(query).strip()

    if not query:
        return

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO UserSearchHistory
                (user_id, username, search_mode, query, result_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(user["user_id"]),
                user["username"],
                str(search_mode),
                query,
                int(result_count),
                datetime.now().isoformat(timespec="seconds"),
            )
        )
        conn.commit()


def get_my_search_history(limit: int = 50):
    """Return only the logged-in user's own search history."""
    import pandas as pd

    ensure_user_search_history_table()

    user = get_current_user()

    if not user:
        return pd.DataFrame(columns=[
            "history_id", "search_mode", "query", "result_count", "created_at"
        ])

    with get_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT history_id, search_mode, query, result_count, created_at
            FROM UserSearchHistory
            WHERE user_id = ?
            ORDER BY history_id DESC
            LIMIT ?;
            """,
            conn,
            params=(int(user["user_id"]), int(limit))
        )


def clear_my_search_history() -> None:
    """Clear only the logged-in user's own search history."""
    ensure_user_search_history_table()

    user = get_current_user()

    if not user:
        return

    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM UserSearchHistory
            WHERE user_id = ?
            """,
            (int(user["user_id"]),)
        )
        conn.commit()
