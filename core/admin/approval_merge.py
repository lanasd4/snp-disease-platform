
"""
Admin Approval + Merge Staging
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import re

import pandas as pd
from core.paths import get_project_root
from core.admin.common import get_outputs_dir, get_registry_path, resolve_within_project


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


def _find_first_existing_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    normalized_map = {normalize_col_name(c): c for c in df.columns}

    for candidate in candidates:
        normalized_candidate = normalize_col_name(candidate)
        if normalized_candidate in normalized_map:
            return normalized_map[normalized_candidate]

    return None


def _series_or_blank(df: pd.DataFrame, candidates: List[str]) -> pd.Series:
    col = _find_first_existing_column(df, candidates)

    if col is None:
        return pd.Series([""] * len(df), index=df.index)

    return df[col]


def _map_processed_rows_to_ranked_schema(processed_df: pd.DataFrame, base_columns: List[str], source_id: str) -> pd.DataFrame:
    """Convert processed admin source rows into the current ranked file schema as much as possible."""
    output = pd.DataFrame(index=processed_df.index)

    source_candidate_map = {
        "rsid": ["rsid", "rsid_normalized", "rs_id", "snp", "snp_id", "variant_id"],
        "snp": ["rsid", "rsid_normalized", "snp", "snp_id"],
        "disease": ["disease_name", "disease_name_normalized", "disease", "trait", "mapped_trait"],
        "trait": ["disease_name", "disease_name_normalized", "trait", "disease"],
        "gene": ["gene_symbol", "gene_symbol_normalized", "gene", "mapped_gene"],
        "gene_symbol": ["gene_symbol", "gene_symbol_normalized", "gene"],
        "p_value": ["p_value", "pvalue", "p-value"],
        "pvalue": ["p_value", "pvalue", "p-value"],
        "study_title": ["study_title", "study", "title"],
        "pubmed_id": ["pubmed_id", "pubmed", "pmid"],
        "pmid": ["pubmed_id", "pubmed", "pmid"],
        "publication_year": ["publication_year", "year"],
        "year": ["publication_year", "year"],
        "population": ["population", "population_region", "ancestry"],
        "region": ["region", "country", "population"],
        "country": ["country", "region"],
        "odds_ratio": ["odds_ratio", "or"],
        "or": ["odds_ratio", "or"],
        "effect_size": ["effect_size", "beta"],
        "beta": ["effect_size", "beta"],
        "risk_allele": ["risk_allele", "effect_allele"],
        "effect_allele": ["effect_allele", "risk_allele"],
        "source_database": ["source_database"],
    }

    for base_col in base_columns:
        normalized_base_col = normalize_col_name(base_col)

        candidates = []

        # direct same-name match
        candidates.append(base_col)
        candidates.append(normalized_base_col)

        # semantic candidate match
        for key, values in source_candidate_map.items():
            if key in normalized_base_col or normalized_base_col in key:
                candidates.extend(values)

        output[base_col] = _series_or_blank(processed_df, candidates)

    # Try to set ranking-related columns for new admin-uploaded rows if they exist
    for col in output.columns:
        ncol = normalize_col_name(col)

        if "importance_score" in ncol and output[col].astype(str).str.strip().eq("").all():
            output[col] = 0

        if "rank_label" in ncol and output[col].astype(str).str.strip().eq("").all():
            output[col] = "Pending Review"

        if "source" == ncol or "source_database" in ncol:
            empty_mask = output[col].astype(str).str.strip().eq("")
            output.loc[empty_mask, col] = "admin_upload"

    output["admin_upload_source_id"] = source_id
    output["row_origin"] = "admin_uploaded_processed"
    output["merge_stage"] = "staging_only_not_active"

    return output


def create_staging_file(source_id: str, created_by: str = "admin") -> Path:
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

    base_df = pd.read_csv(ranked_path)
    processed_df = pd.read_csv(processed_path)

    staged_new_rows = _map_processed_rows_to_ranked_schema(
        processed_df=processed_df,
        base_columns=list(base_df.columns),
        source_id=source_id,
    )

    # Keep staging columns as union: base schema + review metadata columns
    staging_df = pd.concat([base_df, staged_new_rows], ignore_index=True, sort=False)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_source_id = re.sub(r"[^A-Za-z0-9_]+", "_", source_id)

    staging_path = get_staging_dir() / f"ranked_associations_staging_{safe_source_id}_{timestamp}.csv"
    staging_df.to_csv(staging_path, index=False, encoding="utf-8-sig")

    update_registry_row(
        source_id,
        {
            "staging_path": str(staging_path.relative_to(get_project_root())),
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
            "notes": "Approved and staging file created. Not merged into active Search yet.",
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
