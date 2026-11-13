
"""
Admin Data Ingestion Pipeline
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import re
from typing import Dict, Any, Tuple, Optional

import pandas as pd
from core.diseases import resolve_disease_or_trait as resolve_disease
from core.paths import get_project_root
from core.admin.common import get_registry_path


REQUIRED_STANDARD_COLUMNS = [
    "rsid",
    "disease_name",
    "gene_symbol",
    "p_value",
]

OPTIONAL_STANDARD_COLUMNS = [
    "study_title",
    "pubmed_id",
    "publication_year",
    "population",
    "region",
    "country",
    "odds_ratio",
    "effect_size",
    "risk_allele",
    "effect_allele",
    "source_database",
]

ALL_STANDARD_COLUMNS = REQUIRED_STANDARD_COLUMNS + OPTIONAL_STANDARD_COLUMNS


COLUMN_ALIASES = {
    "rsid": [
        "rsid", "rs_id", "snp", "snp_id", "variant", "variant_id",
        "strongest snp-risk allele", "strongest_snp_risk_allele",
        "SNPS", "SNP_ID_CURRENT"
    ],
    "disease_name": [
        "disease", "trait", "disease_name", "reported trait",
        "mapped trait", "disease/trait", "phenotype", "condition"
    ],
    "gene_symbol": [
        "gene", "gene_symbol", "mapped_gene", "mapped gene",
        "nearest_gene", "nearest gene", "reported gene(s)", "reported genes"
    ],
    "p_value": [
        "p_value", "p-value", "pvalue", "p",
    ],
    "study_title": [
        "study_title", "title", "study", "initial sample description",
        "discovery sample ancestry"
    ],
    "pubmed_id": [
        "pubmed_id", "pubmedid", "pubmed", "pmid"
    ],
    "publication_year": [
        "publication_year", "year", "pub_year", "date", "publication date"
    ],
    "population": [
        "population", "ancestry", "sample ancestry", "initial sample size",
        "discovery sample ancestry"
    ],
    "region": [
        "region", "geographic_region", "area"
    ],
    "country": [
        "country", "nation"
    ],
    "odds_ratio": [
        "odds_ratio", "or", "odds ratio", "or or beta"
    ],
    "effect_size": [
        "effect_size", "beta", "effect", "beta coefficient"
    ],
    "risk_allele": [
        "risk_allele", "risk allele", "strongest snp-risk allele"
    ],
    "effect_allele": [
        "effect_allele", "effect allele", "allele"
    ],
    "source_database": [
        "source_database", "source", "database"
    ],
}


def normalize_column_name(name: str) -> str:
    return (
        str(name)
        .strip()
        .lower()
        .replace("\n", " ")
        .replace("\t", " ")
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
    )


def normalize_text_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def extract_rsid(value: Any) -> str:
    text = normalize_text_value(value)

    if not text:
        return ""

    match = re.search(r"rs\d+", text, flags=re.IGNORECASE)

    if match:
        return match.group(0).lower()

    return text.lower()


def clean_gene_symbol(value: Any) -> str:
    text = normalize_text_value(value)

    if not text:
        return ""

    if "," in text:
        text = text.split(",")[0]

    if ";" in text:
        text = text.split(";")[0]

    return text.strip().upper()


def clean_disease_name(value: Any) -> str:
    text = normalize_text_value(value)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def parse_numeric(value: Any) -> Optional[float]:
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text == "":
        return None

    text = text.replace(",", "")

    try:
        return float(text)
    except Exception:
        pass

    # handle scientific notation inside messy text
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)

    if match:
        try:
            return float(match.group(0))
        except Exception:
            return None

    return None


def ensure_registry_columns() -> pd.DataFrame:
    registry_path = get_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)

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
    ]

    if registry_path.exists():
        registry_df = pd.read_csv(registry_path)
    else:
        registry_df = pd.DataFrame(columns=required_columns)

    for col in required_columns:
        if col not in registry_df.columns:
            registry_df[col] = ""

    registry_df = registry_df[required_columns + [c for c in registry_df.columns if c not in required_columns]]
    registry_df.to_csv(registry_path, index=False, encoding="utf-8-sig")

    return registry_df


def update_registry_status(
    source_id: str,
    updates: Dict[str, Any],
) -> pd.DataFrame:
    registry_df = ensure_registry_columns()
    registry_path = get_registry_path()

    if "source_id" not in registry_df.columns:
        registry_df["source_id"] = ""

    mask = registry_df["source_id"].astype(str) == str(source_id)

    if not mask.any():
        new_row = {col: "" for col in registry_df.columns}
        new_row["source_id"] = source_id
        registry_df = pd.concat([registry_df, pd.DataFrame([new_row])], ignore_index=True)
        mask = registry_df["source_id"].astype(str) == str(source_id)

    for key, value in updates.items():
        if key not in registry_df.columns:
            registry_df[key] = ""
        registry_df.loc[mask, key] = value

    registry_df.to_csv(registry_path, index=False, encoding="utf-8-sig")
    return registry_df


def register_uploaded_source(
    source_name: str,
    raw_path: Path,
    uploaded_by: str = "admin",
    notes: str = "",
) -> str:
    ensure_registry_columns()

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", Path(source_name).stem).strip("_")
    source_id = f"admin_upload_{safe_name}_{now}"

    update_registry_status(
        source_id,
        {
            "source_name": source_name,
            "source_type": "admin_uploaded",
            "source_path": str(raw_path.relative_to(get_project_root())),
            "status": "uploaded",
            "enabled": "N",
            "uploaded_by": uploaded_by,
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "notes": notes,
        }
    )

    return source_id


def read_uploaded_source(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Uploaded source not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)

    if suffix in [".tsv", ".txt"]:
        return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)

    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(path, dtype=str).fillna("")

    raise ValueError(f"Unsupported file type: {suffix}")


def infer_column_mapping(df: pd.DataFrame) -> Dict[str, str]:
    """Infer mapping from uploaded columns to standard schema."""
    normalized_to_original = {
        normalize_column_name(col): col
        for col in df.columns
    }

    mapping = {}

    for standard_col, aliases in COLUMN_ALIASES.items():
        normalized_aliases = [normalize_column_name(a) for a in aliases]

        for alias in normalized_aliases:
            if alias in normalized_to_original:
                mapping[standard_col] = normalized_to_original[alias]
                break

    return mapping


def _add_p_from_mlog(df: pd.DataFrame, mapping: Dict[str, str]) -> None:
    """GWAS files may only give -log10(p) (PVALUE_MLOG); convert it to a real p-value."""
    if "p_value" in mapping:
        return
    mlog = next((c for c in df.columns if normalize_column_name(c) in {"pvalue_mlog", "p_value_mlog", "mlog10p"}), None)
    if mlog:
        df["__p_from_mlog"] = df[mlog].apply(
            lambda v: 10 ** -parse_numeric(v) if parse_numeric(v) is not None else "")
        mapping["p_value"] = "__p_from_mlog"


def validate_uploaded_source(df: pd.DataFrame, mapping: Optional[Dict[str, str]] = None) -> Tuple[bool, Dict[str, Any]]:
    if mapping is None:
        mapping = infer_column_mapping(df)
    _add_p_from_mlog(df, mapping)

    missing_required = [
        col for col in REQUIRED_STANDARD_COLUMNS
        if col not in mapping
    ]

    report = {
        "is_valid": len(missing_required) == 0,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": list(df.columns),
        "mapping": mapping,
        "missing_required_columns": missing_required,
        "required_standard_columns": REQUIRED_STANDARD_COLUMNS,
        "optional_standard_columns": OPTIONAL_STANDARD_COLUMNS,
    }

    return report["is_valid"], report


def map_uploaded_columns(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    mapped_df = pd.DataFrame()

    for standard_col in ALL_STANDARD_COLUMNS:
        uploaded_col = mapping.get(standard_col)

        if uploaded_col and uploaded_col in df.columns:
            mapped_df[standard_col] = df[uploaded_col]
        else:
            mapped_df[standard_col] = ""

    return mapped_df


def clean_uploaded_source(mapped_df: pd.DataFrame) -> pd.DataFrame:
    df = mapped_df.copy()

    df["rsid"] = df["rsid"].apply(extract_rsid)
    df["disease_name"] = df["disease_name"].apply(clean_disease_name)
    df["gene_symbol"] = df["gene_symbol"].apply(clean_gene_symbol)

    df["p_value"] = df["p_value"].apply(parse_numeric)
    df["odds_ratio"] = df["odds_ratio"].apply(parse_numeric)
    df["effect_size"] = df["effect_size"].apply(parse_numeric)

    df["publication_year"] = df["publication_year"].apply(
        lambda x: int(parse_numeric(x)) if parse_numeric(x) is not None else ""
    )

    for col in [
        "study_title", "pubmed_id", "population", "region", "country",
        "risk_allele", "effect_allele", "source_database"
    ]:
        df[col] = df[col].apply(normalize_text_value)

    return df


def normalize_uploaded_source(clean_df: pd.DataFrame) -> pd.DataFrame:
    df = clean_df.copy()

    df["disease_name_normalized"] = df["disease_name"].str.strip().str.lower()
    df["gene_symbol_normalized"] = df["gene_symbol"].str.strip().str.upper()
    df["rsid_normalized"] = df["rsid"].str.strip().str.lower()

    if "source_database" in df.columns:
        df["source_database"] = df["source_database"].replace("", "admin_upload")
    else:
        df["source_database"] = "admin_upload"

    df["ingestion_created_at"] = datetime.now().isoformat(timespec="seconds")

    return df


def _row_rejection_reasons(row) -> list:
    reasons = []
    if not re.match(r"^rs\d+$", str(row.get("rsid_normalized", ""))):
        reasons.append("invalid_or_missing_rsid")
    if not str(row.get("disease_name", "")).strip():
        reasons.append("missing_disease_name")
    elif resolve_disease(str(row.get("disease_name"))) is None:
        reasons.append("disease_not_on_platform")
    if not str(row.get("gene_symbol", "")).strip():
        reasons.append("missing_gene_symbol")
    p_value = row.get("p_value")
    if p_value is None or pd.isna(p_value):
        reasons.append("missing_or_invalid_p_value")
    elif not 0 < float(p_value) <= 1:
        reasons.append("p_value_out_of_range")
    return reasons


def split_accepted_rejected_rows(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Keep rows that are complete, valid and about one of the platform's diseases."""
    reasons = df.apply(_row_rejection_reasons, axis=1) if not df.empty else pd.Series(dtype=object)
    accepted_mask = reasons.apply(len) == 0 if not df.empty else pd.Series(dtype=bool)

    accepted = df[accepted_mask].copy()
    rejected = df[~accepted_mask].copy()

    if not accepted.empty:
        accepted["disease_name"] = accepted["disease_name"].apply(lambda name: resolve_disease(name).name_en)
        accepted["disease_name_normalized"] = accepted["disease_name"].str.lower()

    if not rejected.empty:
        rejected["rejection_reason"] = reasons[~accepted_mask].apply(";".join)

    return accepted, rejected


def deduplicate_uploaded_source(accepted_df: pd.DataFrame) -> pd.DataFrame:
    if accepted_df.empty:
        return accepted_df.copy()

    df = accepted_df.copy()

    sort_cols = ["disease_name_normalized", "rsid_normalized", "gene_symbol_normalized", "p_value"]
    df = df.sort_values(sort_cols, ascending=[True, True, True, True])

    df = df.drop_duplicates(
        subset=["disease_name_normalized", "rsid_normalized", "gene_symbol_normalized"],
        keep="first"
    )

    return df.reset_index(drop=True)


def save_validation_report(source_id: str, report: Dict[str, Any]) -> Path:
    output_dir = get_project_root() / "outputs" / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"validation_report_{source_id}.csv"

    rows = []

    rows.append({"field": "source_id", "value": source_id})
    rows.append({"field": "is_valid", "value": report.get("is_valid")})
    rows.append({"field": "row_count", "value": report.get("row_count")})
    rows.append({"field": "column_count", "value": report.get("column_count")})
    rows.append({"field": "missing_required_columns", "value": ", ".join(report.get("missing_required_columns", []))})

    mapping = report.get("mapping", {})

    for standard_col, uploaded_col in mapping.items():
        rows.append({"field": f"mapping.{standard_col}", "value": uploaded_col})

    pd.DataFrame(rows).to_csv(report_path, index=False, encoding="utf-8-sig")

    return report_path


def save_processed_source(
    source_id: str,
    processed_df: pd.DataFrame,
    rejected_df: pd.DataFrame,
) -> Tuple[Path, Path]:
    processed_dir = get_project_root() / "data" / "processed" / "admin_sources"
    output_dir = get_project_root() / "outputs" / "tables"

    processed_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    processed_path = processed_dir / f"{source_id}_processed.csv"
    rejected_path = output_dir / f"rejected_rows_{source_id}.csv"

    processed_df.to_csv(processed_path, index=False, encoding="utf-8-sig")
    rejected_df.to_csv(rejected_path, index=False, encoding="utf-8-sig")

    return processed_path, rejected_path


def run_uploaded_source_pipeline(
    raw_file_path: str | Path,
    uploaded_by: str = "admin",
    source_name: Optional[str] = None,
    notes: str = "",
) -> Dict[str, Any]:
    raw_path = Path(raw_file_path)

    if source_name is None:
        source_name = raw_path.name

    # Register as uploaded
    source_id = register_uploaded_source(
        source_name=source_name,
        raw_path=raw_path,
        uploaded_by=uploaded_by,
        notes=notes,
    )

    # Read
    raw_df = read_uploaded_source(raw_path)

    # Validate + map
    mapping = infer_column_mapping(raw_df)
    is_valid, report = validate_uploaded_source(raw_df, mapping=mapping)
    report["is_valid"] = is_valid

    validation_report_path = save_validation_report(source_id, report)

    if not is_valid:
        update_registry_status(
            source_id,
            {
                "status": "validation_failed",
                "validation_report_path": str(validation_report_path.relative_to(get_project_root())),
                "row_count": int(len(raw_df)),
                "processed_at": datetime.now().isoformat(timespec="seconds"),
                "notes": "Missing required columns. Source was not processed.",
            }
        )

        return {
            "source_id": source_id,
            "status": "validation_failed",
            "validation_report_path": validation_report_path,
            "report": report,
        }

    update_registry_status(
        source_id,
        {
            "status": "validated",
            "validation_report_path": str(validation_report_path.relative_to(get_project_root())),
            "row_count": int(len(raw_df)),
        }
    )

    # Mapping
    mapped_df = map_uploaded_columns(raw_df, mapping=mapping)

    # Cleaning
    clean_df = clean_uploaded_source(mapped_df)

    # Normalization
    normalized_df = normalize_uploaded_source(clean_df)

    # Split accepted/rejected
    accepted_df, rejected_df = split_accepted_rejected_rows(normalized_df)

    # Deduplication
    processed_df = deduplicate_uploaded_source(accepted_df)

    # Save processed
    processed_path, rejected_path = save_processed_source(
        source_id=source_id,
        processed_df=processed_df,
        rejected_df=rejected_df,
    )

    update_registry_status(
        source_id,
        {
            "status": "processed",
            "processed_path": str(processed_path.relative_to(get_project_root())),
            "rejected_rows_path": str(rejected_path.relative_to(get_project_root())),
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "accepted_rows": int(len(processed_df)),
            "rejected_rows": int(len(rejected_df)),
            "enabled": "N",
            "notes": "Processed. Waiting for admin approval.",
        }
    )

    return {
        "source_id": source_id,
        "status": "processed",
        "raw_rows": int(len(raw_df)),
        "accepted_rows": int(len(processed_df)),
        "rejected_rows": int(len(rejected_df)),
        "processed_path": processed_path,
        "rejected_rows_path": rejected_path,
        "validation_report_path": validation_report_path,
        "mapping": mapping,
    }
