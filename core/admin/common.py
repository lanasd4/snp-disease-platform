"""
Helpers shared by every admin data workflow (ingestion, approval, final
merge, GWAS online updates): registry/output locations and the path
containment guard for registry-stored paths.
"""

from __future__ import annotations

from pathlib import Path

from core.paths import (
    DATA_SOURCES_REGISTRY_FILE,
    OUTPUT_TABLES_DIR,
    PROJECT_ROOT,
    RANKED_ASSOCIATIONS_FILE,
)


class PathContainmentError(ValueError):
    """Raised when a registry-stored path would resolve outside the project folder."""


def resolve_within_project(relative_value: str, what: str = "path") -> Path:
    """Join a registry-stored path value onto the project root and verify it stays inside."""
    project_root = PROJECT_ROOT.resolve()
    candidate = (project_root / str(relative_value)).resolve()

    try:
        candidate.relative_to(project_root)
    except ValueError:
        raise PathContainmentError(
            f"Registry {what} '{relative_value}' resolves outside the project "
            f"folder ({candidate}). Refusing to use it."
        )

    return candidate


def get_registry_path() -> Path:
    return DATA_SOURCES_REGISTRY_FILE


def get_active_ranked_path() -> Path:
    return RANKED_ASSOCIATIONS_FILE


def get_outputs_dir() -> Path:
    OUTPUT_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_TABLES_DIR
