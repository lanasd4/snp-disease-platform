"""
Runtime settings read from environment variables or Streamlit secrets.
"""

from __future__ import annotations

import os
from typing import Optional

ADMIN_USERNAME_KEY = "SNP_ADMIN_USERNAME"
ADMIN_PASSWORD_KEY = "SNP_ADMIN_PASSWORD"
ALLOW_REGISTRATION_KEY = "SNP_ALLOW_REGISTRATION"

_TRUE_VALUES = {"1", "true", "yes", "on"}


def get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return a setting from the environment, then Streamlit secrets, else `default`."""
    value = os.environ.get(name)
    if value not in (None, ""):
        return value

    if os.environ.get("SNP_IGNORE_SECRETS") == "1":
        # Tests set this so a developer's local .streamlit/secrets.toml never leaks in.
        return default

    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        # No secrets.toml (normal for local runs) or Streamlit not running.
        value = None

    if value in (None, ""):
        return default
    return str(value)


def get_bool_setting(name: str, default: bool) -> bool:
    value = get_setting(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def registration_enabled() -> bool:
    """Public self-registration is on unless SNP_ALLOW_REGISTRATION is false."""
    return get_bool_setting(ALLOW_REGISTRATION_KEY, default=True)
