
"""
Admin Final Merge + Rollback
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import shutil
import pandas as pd
from core.paths import get_project_root
from core.admin.common import get_active_ranked_path, get_outputs_dir, get_registry_path, resolve_within_project


def get_backup_dir() -> Path:
    path = get_project_root() / "data" / "processed" / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_merge_log_dir() -> Path:
    path = get_project_root() / "data" / "processed" / "merge_logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_registry() -> pd.DataFrame:
    registry_path = get_registry_path()

    if not registry_path.exists():
        raise FileNotFoundError("data_sources_registry.csv not found.")

    registry_df = pd.read_csv(registry_path)

    required_columns = [
        "source_id",
        "status",
        "enabled",
        "staging_path",
        "merged_path",
        "backup_path",
        "merged_by",
        "merged_at",
        "merge_log_path",
        "rollback_status",
        "rollback_at",
        "rollback_by",
        "rollback_notes",
        "notes",
    ]

    for col in required_columns:
        if col not in registry_df.columns:
            registry_df[col] = ""

    return registry_df


def save_registry(registry_df: pd.DataFrame) -> None:
    registry_df.to_csv(get_registry_path(), index=False, encoding="utf-8-sig")


def update_registry(source_id: str, updates: Dict[str, Any]) -> pd.DataFrame:
    registry_df = load_registry()

    mask = registry_df["source_id"].astype(str).eq(str(source_id))

    if not mask.any():
        raise ValueError(f"source_id not found: {source_id}")

    for key, value in updates.items():
        if key not in registry_df.columns:
            registry_df[key] = ""
        registry_df.loc[mask, key] = value

    save_registry(registry_df)
    return registry_df


def list_approved_sources() -> pd.DataFrame:
    registry_df = load_registry()

    approved_df = registry_df[
        registry_df["status"].astype(str).str.lower().eq("approved")
    ].copy()

    preferred_cols = [
        "source_id",
        "source_name",
        "source_type",
        "status",
        "enabled",
        "accepted_rows",
        "rejected_rows",
        "staging_path",
        "processed_path",
        "reviewed_by",
        "reviewed_at",
        "notes",
    ]

    cols = [c for c in preferred_cols if c in approved_df.columns]
    other_cols = [c for c in approved_df.columns if c not in cols]

    return approved_df[cols + other_cols]


def list_merged_sources() -> pd.DataFrame:
    registry_df = load_registry()

    merged_df = registry_df[
        registry_df["status"].astype(str).str.lower().isin(["merged", "active"])
    ].copy()

    preferred_cols = [
        "source_id",
        "source_name",
        "source_type",
        "status",
        "enabled",
        "merged_path",
        "backup_path",
        "merged_by",
        "merged_at",
        "merge_log_path",
        "rollback_status",
        "notes",
    ]

    cols = [c for c in preferred_cols if c in merged_df.columns]
    other_cols = [c for c in merged_df.columns if c not in cols]

    return merged_df[cols + other_cols]


def get_source_row(source_id: str) -> pd.Series:
    registry_df = load_registry()
    match = registry_df[registry_df["source_id"].astype(str).eq(str(source_id))]

    if match.empty:
        raise ValueError(f"source_id not found: {source_id}")

    return match.iloc[0]


def create_active_ranked_backup(source_id: str) -> Path:
    active_path = get_active_ranked_path()

    if not active_path.exists():
        raise FileNotFoundError(f"Active ranked file not found: {active_path}")

    backup_path = get_backup_dir() / f"ranked_associations_before_merge_{source_id}_{now_stamp()}.csv"
    shutil.copy2(active_path, backup_path)

    return backup_path


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    return pd.read_csv(path)


def validate_staging_file(staging_path: Path) -> Dict[str, Any]:
    active_path = get_active_ranked_path()

    active_df = _load_csv(active_path)
    staging_df = _load_csv(staging_path)

    report = {
        "active_rows_before": int(len(active_df)),
        "staging_rows": int(len(staging_df)),
        "active_columns_before": int(len(active_df.columns)),
        "staging_columns": int(len(staging_df.columns)),
        "is_valid": True,
        "issues": [],
    }

    if staging_df.empty:
        report["is_valid"] = False
        report["issues"].append("staging_file_is_empty")

    if len(staging_df) < len(active_df):
        report["is_valid"] = False
        report["issues"].append("staging_has_fewer_rows_than_active_file")

    missing_active_columns = [
        col for col in active_df.columns
        if col not in staging_df.columns
    ]

    if missing_active_columns:
        report["is_valid"] = False
        report["issues"].append("staging_missing_active_columns:" + ",".join(missing_active_columns))

    return report


def write_merge_log(source_id: str, log_data: Dict[str, Any]) -> Path:
    log_path = get_merge_log_dir() / f"merge_log_{source_id}_{now_stamp()}.csv"

    rows = []

    for key, value in log_data.items():
        rows.append({"field": key, "value": value})

    pd.DataFrame(rows).to_csv(log_path, index=False, encoding="utf-8-sig")

    return log_path


def final_merge_source(
    source_id: str,
    merged_by: str = "admin",
    notes: str = "",
) -> Dict[str, Any]:
    """Final merge:"""
    row = get_source_row(source_id)
    status = str(row.get("status", "")).lower()

    if status != "approved":
        raise ValueError(f"Only approved sources can be merged. Current status: {status}")

    staging_path_value = str(row.get("staging_path", "")).strip()

    if not staging_path_value:
        raise ValueError("staging_path is missing. Approve source and create staging first.")

    staging_path = resolve_within_project(staging_path_value, what="staging_path")

    if not staging_path.exists():
        raise FileNotFoundError(f"staging file not found: {staging_path}")

    validation_report = validate_staging_file(staging_path)

    if not validation_report["is_valid"]:
        raise ValueError(f"Invalid staging file: {validation_report['issues']}")

    active_path = get_active_ranked_path()
    backup_path = create_active_ranked_backup(source_id)

    # Final merge operation: staging becomes active ranked file
    shutil.copy2(staging_path, active_path)

    merged_df = pd.read_csv(active_path)

    log_data = {
        "source_id": source_id,
        "action": "final_merge",
        "merged_by": merged_by,
        "merged_at": now_iso(),
        "active_file": str(active_path.relative_to(get_project_root())),
        "staging_path": str(staging_path.relative_to(get_project_root())),
        "backup_path": str(backup_path.relative_to(get_project_root())),
        "rows_after_merge": int(len(merged_df)),
        "notes": notes,
        "validation_report": validation_report,
    }

    merge_log_path = write_merge_log(source_id, log_data)

    update_registry(
        source_id,
        {
            "status": "active",
            "enabled": "Y",
            "merged_path": str(active_path.relative_to(get_project_root())),
            "backup_path": str(backup_path.relative_to(get_project_root())),
            "merged_by": merged_by,
            "merged_at": now_iso(),
            "merge_log_path": str(merge_log_path.relative_to(get_project_root())),
            "rollback_status": "available",
            "notes": notes if notes else "Final merge completed. Source is active in Search.",
        }
    )

    return {
        "source_id": source_id,
        "status": "active",
        "enabled": "Y",
        "active_path": active_path,
        "backup_path": backup_path,
        "staging_path": staging_path,
        "merge_log_path": merge_log_path,
        "rows_after_merge": int(len(merged_df)),
        "validation_report": validation_report,
    }


def rollback_source(
    source_id: str,
    rollback_by: str = "admin",
    notes: str = "",
) -> Dict[str, Any]:
    """Roll back active ranked file to the backup created before merge."""
    row = get_source_row(source_id)

    backup_path_value = str(row.get("backup_path", "")).strip()

    if not backup_path_value:
        raise ValueError("No backup_path found for this source.")

    backup_path = resolve_within_project(backup_path_value, what="backup_path")

    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    active_path = get_active_ranked_path()
    shutil.copy2(backup_path, active_path)

    restored_df = pd.read_csv(active_path)

    log_data = {
        "source_id": source_id,
        "action": "rollback",
        "rollback_by": rollback_by,
        "rollback_at": now_iso(),
        "restored_from_backup": str(backup_path.relative_to(get_project_root())),
        "active_file": str(active_path.relative_to(get_project_root())),
        "rows_after_rollback": int(len(restored_df)),
        "notes": notes,
    }

    rollback_log_path = write_merge_log(source_id, log_data)

    update_registry(
        source_id,
        {
            "status": "rolled_back",
            "enabled": "N",
            "rollback_status": "completed",
            "rollback_at": now_iso(),
            "rollback_by": rollback_by,
            "rollback_notes": notes,
            "merge_log_path": str(rollback_log_path.relative_to(get_project_root())),
            "notes": notes if notes else "Rollback completed. Source is no longer active in Search.",
        }
    )

    return {
        "source_id": source_id,
        "status": "rolled_back",
        "enabled": "N",
        "active_path": active_path,
        "backup_path": backup_path,
        "rollback_log_path": rollback_log_path,
        "rows_after_rollback": int(len(restored_df)),
    }


def export_merge_snapshot() -> Path:
    registry_df = load_registry()

    snapshot_path = get_outputs_dir() / "merge_registry_snapshot.csv"
    registry_df.to_csv(snapshot_path, index=False, encoding="utf-8-sig")

    return snapshot_path
