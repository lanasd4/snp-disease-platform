
"""
Admin Approval + Merge Staging
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any, Dict
import re

import pandas as pd
from core.paths import get_project_root
from core.admin.common import get_outputs_dir, get_registry_path, resolve_within_project
from core.admin.ranked_rows import add_source, build_source_rows


REVIEW_STATUSES = ["processed", "pending_approval", "approved", "rejected"]


def get_ranked_file_path() -> Path:
    return get_project_root() / "data" / "processed" / "ranked_associations_initial.csv"


def get_staging_dir() -> Path:
    staging_dir = get_project_root() / "data" / "processed" / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    return staging_dir


def normalize_col_name(col: str) -> str:
    return (
        str(col)
        .strip()
        .lower()
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
    )


def _ensure_registry_columns(registry_df: pd.DataFrame) -> pd.DataFrame:
    required_columns = [
        "source_id",
        "source_name",
        "source_type",
        "source_path",
        "processed_path",
        "validation_report_path",
        "rejected_rows_path",
        "status",
        "enabled",
        "uploaded_by",
        "uploaded_at",
        "processed_at",
        "row_count",
        "accepted_rows",
        "rejected_rows",
        "notes",
        "reviewed_by",
        "reviewed_at",
        "review_notes",
        "rejection_reason",
        "staging_path",
        "staging_created_at",
    ]

    for col in required_columns:
        if col not in registry_df.columns:
            registry_df[col] = ""

    return registry_df


def load_registry() -> pd.DataFrame:
    registry_path = get_registry_path()

    if not registry_path.exists():
        raise FileNotFoundError("data_sources_registry.csv not found.")

    registry_df = pd.read_csv(registry_path)
    registry_df = _ensure_registry_columns(registry_df)

    return registry_df


def save_registry(registry_df: pd.DataFrame) -> None:
    registry_path = get_registry_path()
    registry_df.to_csv(registry_path, index=False, encoding="utf-8-sig")


def update_registry_row(source_id: str, updates: Dict[str, Any]) -> pd.DataFrame:
    registry_df = load_registry()

    mask = registry_df["source_id"].astype(str) == str(source_id)

    if not mask.any():
        raise ValueError(f"source_id not found in registry: {source_id}")

    for key, value in updates.items():
        if key not in registry_df.columns:
            registry_df[key] = ""
        registry_df.loc[mask, key] = value

    save_registry(registry_df)

    return registry_df


def list_sources_for_review() -> pd.DataFrame:
    registry_df = load_registry()

    status_series = registry_df["status"].astype(str).str.lower()

    review_df = registry_df[status_series.isin(REVIEW_STATUSES)].copy()

    preferred_cols = [
        "source_id",
        "source_name",
        "status",
        "enabled",
        "row_count",
        "accepted_rows",
        "rejected_rows",
        "processed_path",
        "validation_report_path",
        "rejected_rows_path",
        "staging_path",
        "reviewed_by",
        "reviewed_at",
        "notes",
    ]

    cols = [c for c in preferred_cols if c in review_df.columns]
    other_cols = [c for c in review_df.columns if c not in cols]

    return review_df[cols + other_cols]


def get_source_row(source_id: str) -> pd.Series:
    registry_df = load_registry()
    match = registry_df[registry_df["source_id"].astype(str) == str(source_id)]

    if match.empty:
        raise ValueError(f"source_id not found: {source_id}")

    return match.iloc[0]


def mark_pending_approval(source_id: str, reviewed_by: str = "admin", notes: str = "") -> None:
    row = get_source_row(source_id)
    current_status = str(row.get("status", "")).lower()

    if current_status not in ["processed", "pending_approval"]:
        raise ValueError(f"Only processed sources can be moved to pending approval. Current status: {current_status}")

    update_registry_row(
        source_id,
        {
            "status": "pending_approval",
            "enabled": "N",
            "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            "review_notes": notes,
        }
    )


def reject_source(source_id: str, rejected_by: str = "admin", reason: str = "") -> None:
    row = get_source_row(source_id)
    current_status = str(row.get("status", "")).lower()

    if current_status not in ["processed", "pending_approval", "approved"]:
        raise ValueError(f"Source cannot be rejected from status: {current_status}")

    update_registry_row(
        source_id,
        {
            "status": "rejected",
            "enabled": "N",
            "reviewed_by": rejected_by,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            "rejection_reason": reason,
            "review_notes": reason,
        }
    )


def source_rows_path(source_id: str) -> Path:
    safe_source_id = re.sub(r"[^A-Za-z0-9_]+", "_", source_id)
    return get_staging_dir() / f"source_rows_{safe_source_id}.csv"


def create_staging_file(source_id: str, created_by: str = "admin") -> Path:
    """Convert the processed source into ranked rows and write a preview of the merged table."""
    row = get_source_row(source_id)

    processed_path_value = str(row.get("processed_path", "")).strip()

    if not processed_path_value:
        raise ValueError("Processed path is missing for this source.")

    processed_path = resolve_within_project(processed_path_value, what="processed_path")

    if not processed_path.exists():
        raise FileNotFoundError(f"Processed file not found: {processed_path}")

    ranked_path = get_ranked_file_path()

    if not ranked_path.exists():
        raise FileNotFoundError(f"Base ranked file not found: {ranked_path}")

    base_df = pd.read_csv(ranked_path, dtype=str, keep_default_na=False)
    processed_df = pd.read_csv(processed_path, dtype=str, keep_default_na=False)

    new_rows, skipped = build_source_rows(processed_df, source_id, base_df)
    if new_rows.empty:
        raise ValueError("No rows can be added: every row is for a disease outside the platform "
                         "or has an invalid p-value.")
    new_rows.to_csv(source_rows_path(source_id), index=False, encoding="utf-8-sig")

    staging_df = add_source(base_df, new_rows)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_source_id = re.sub(r"[^A-Za-z0-9_]+", "_", source_id)

    staging_path = get_staging_dir() / f"ranked_associations_staging_{safe_source_id}_{timestamp}.csv"
    staging_df.to_csv(staging_path, index=False, encoding="utf-8-sig")

    update_registry_row(
        source_id,
        {
            "staging_path": str(staging_path.relative_to(get_project_root())),
            "source_rows_path": str(source_rows_path(source_id).relative_to(get_project_root())),
            "staged_rows": int(len(new_rows)),
            "skipped_rows": int(len(skipped)),
            "staging_created_at": datetime.now().isoformat(timespec="seconds"),
            "reviewed_by": created_by,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        }
    )

    return staging_path


def approve_source(source_id: str, approved_by: str = "admin", notes: str = "") -> Path:
    row = get_source_row(source_id)
    current_status = str(row.get("status", "")).lower()

    if current_status not in ["processed", "pending_approval", "approved"]:
        raise ValueError(f"Source cannot be approved from status: {current_status}")

    staging_path = create_staging_file(source_id=source_id, created_by=approved_by)

    update_registry_row(
        source_id,
        {
            "status": "approved",
            "enabled": "N",
            "reviewed_by": approved_by,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            "review_notes": notes,
            "staging_path": str(staging_path.relative_to(get_project_root())),
            "notes": "Approved. Not live in Search until the final merge.",
        }
    )

    return staging_path


def load_validation_report_for_source(source_id: str) -> pd.DataFrame:
    row = get_source_row(source_id)
    path_value = str(row.get("validation_report_path", "")).strip()

    if not path_value:
        return pd.DataFrame()

    path = resolve_within_project(path_value, what="validation_report_path")

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def load_rejected_rows_for_source(source_id: str) -> pd.DataFrame:
    row = get_source_row(source_id)
    path_value = str(row.get("rejected_rows_path", "")).strip()

    if not path_value:
        return pd.DataFrame()

    path = resolve_within_project(path_value, what="rejected_rows_path")

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def load_processed_rows_for_source(source_id: str) -> pd.DataFrame:
    row = get_source_row(source_id)
    path_value = str(row.get("processed_path", "")).strip()

    if not path_value:
        return pd.DataFrame()

    path = resolve_within_project(path_value, what="processed_path")

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def export_review_snapshot() -> Path:
    review_df = list_sources_for_review()
    output_path = get_outputs_dir() / "sources_for_review_snapshot.csv"
    review_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path
