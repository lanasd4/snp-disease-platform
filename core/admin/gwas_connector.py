
"""
Online GWAS Update Connector
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import urllib.parse
import urllib.request
import pandas as pd

from core.diseases import resolve_disease_or_trait as resolve_disease
import re
import zipfile
from core.paths import get_project_root
from core.admin.common import get_outputs_dir, get_registry_path


DEFAULT_GWAS_ASSOCIATIONS_URL = "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/"

# Security allow-list for online source fetches (see run_gwas_online_update /...
ALLOWED_ONLINE_SOURCE_HOSTS = {
    "ftp.ebi.ac.uk",
    "www.ebi.ac.uk",
    "ebi.ac.uk",
}


class UnsafeOnlineSourceError(ValueError):
    """Raised when an online source URL fails the scheme/host allow-list check."""


# Hard ceiling for ZIP downloads so a huge or malicious (zip-bomb-style) remote
# file cannot exhaust local disk space. TSV/TXT downloads are already bounded
# by max_lines, so this only applies to the ZIP branch.
MAX_ZIP_DOWNLOAD_BYTES = 200 * 1024 * 1024


def validate_online_source_url(url: str) -> None:
    """Enforce https-only + known-host allow-list before any network fetch."""
    parsed = urllib.parse.urlparse(str(url))

    if parsed.scheme != "https":
        raise UnsafeOnlineSourceError(
            f"Only https:// online sources are allowed. Rejected scheme: '{parsed.scheme}'."
        )

    hostname = (parsed.hostname or "").lower()

    if hostname not in ALLOWED_ONLINE_SOURCE_HOSTS:
        raise UnsafeOnlineSourceError(
            f"'{hostname}' is not an approved online data source host. "
            f"Approved hosts: {', '.join(sorted(ALLOWED_ONLINE_SOURCE_HOSTS))}. "
            "Add trusted hosts to ALLOWED_ONLINE_SOURCE_HOSTS in "
            "core/admin/gwas_connector.py only after verifying the source."
        )


def get_raw_online_gwas_dir() -> Path:
    path = get_project_root() / "data" / "raw" / "online" / "gwas"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_")


def discover_latest_gwas_associations_url(base_url: str = DEFAULT_GWAS_ASSOCIATIONS_URL) -> str:
    """Discover a usable GWAS Catalog associations file from the latest FTP directory."""
    if not base_url.endswith("/"):
        base_url = base_url + "/"

    validate_online_source_url(base_url)

    request = urllib.request.Request(
        base_url,
        headers={"User-Agent": "SNP-Disease-Platform/1.0"}
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        html = response.read().decode("utf-8", errors="ignore")

    hrefs = re.findall(r'href=["\\\']([^"\\\']+)["\\\']', html, flags=re.IGNORECASE)

    candidates = []

    for href in hrefs:
        lower = href.lower()

        if "association" in lower and (
            lower.endswith(".tsv")
            or lower.endswith(".tsv.gz")
            or lower.endswith(".zip")
        ):
            candidates.append(href)

    if not candidates:
        raise RuntimeError(
            "Could not discover a GWAS associations TSV/ZIP file from the latest FTP directory."
        )

    preferred = [
        c for c in candidates
        if "ontology" in c.lower() and "association" in c.lower()
    ]

    selected = preferred[0] if preferred else candidates[0]

    if selected.startswith("http://") or selected.startswith("https://"):
        return selected

    return base_url + selected


def download_text_snapshot(
    url: str,
    max_lines: int = 5000,
    timeout: int = 120,
) -> tuple[Path, Dict[str, Any]]:
    """Download a controlled online snapshot."""
    validate_online_source_url(url)

    timestamp = _now_stamp()
    is_zip = str(url).lower().endswith(".zip")

    suffix = ".zip" if is_zip else ".tsv"
    raw_path = get_raw_online_gwas_dir() / f"gwas_online_snapshot_{timestamp}{suffix}"

    metadata = {
        "url": url,
        "raw_path": str(raw_path.relative_to(get_project_root())),
        "downloaded_at": _now_iso(),
        "max_lines": max_lines,
        "download_status": "started",
        "error": "",
        "line_count": 0,
        "file_size_bytes": 0,
        "is_zip": is_zip,
    }

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "SNP-Disease-Platform/1.0"}
        )

        with urllib.request.urlopen(request, timeout=timeout) as response:
            if is_zip:
                downloaded_bytes = 0

                with raw_path.open("wb") as out:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break

                        downloaded_bytes += len(chunk)

                        if downloaded_bytes > MAX_ZIP_DOWNLOAD_BYTES:
                            raise RuntimeError(
                                f"ZIP source exceeded the {MAX_ZIP_DOWNLOAD_BYTES // (1024 * 1024)}MB "
                                "download limit and was stopped."
                            )

                        out.write(chunk)

                metadata["line_count"] = "full_zip_download"

            else:
                with raw_path.open("wb") as out:
                    line_count = 0

                    for line in response:
                        out.write(line)
                        line_count += 1

                        if line_count >= int(max_lines):
                            break

                metadata["line_count"] = line_count

        metadata["download_status"] = "success"
        metadata["file_size_bytes"] = raw_path.stat().st_size

    except Exception as exc:
        metadata["download_status"] = "failed"
        metadata["error"] = str(exc)

        raw_path.write_text(
            "DOWNLOAD_FAILED\n"
            f"URL={url}\n"
            f"ERROR={exc}\n",
            encoding="utf-8"
        )

    return raw_path, metadata


def read_online_snapshot(raw_path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    """Read GWAS online snapshot."""
    if raw_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(raw_path, "r") as zf:
            members = zf.namelist()

            tabular_members = [
                m for m in members
                if m.lower().endswith(".tsv") or m.lower().endswith(".txt")
            ]

            if not tabular_members:
                raise RuntimeError("ZIP file does not contain TSV/TXT tabular files.")

            selected_member = tabular_members[0]

            with zf.open(selected_member) as file_obj:
                return pd.read_csv(file_obj, sep="\t", low_memory=False, nrows=nrows)

    text_head = raw_path.read_text(encoding="utf-8", errors="ignore")[:200]

    if text_head.startswith("DOWNLOAD_FAILED"):
        raise RuntimeError(raw_path.read_text(encoding="utf-8", errors="ignore"))

    return pd.read_csv(raw_path, sep="\t", low_memory=False, nrows=nrows)


def _find_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    normalized = {
        str(c).strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_"): c
        for c in df.columns
    }

    for candidate in candidates:
        key = str(candidate).strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")

        if key in normalized:
            return normalized[key]

    return None


def _series_or_blank(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    col = _find_column(df, candidates)

    if col and col in df.columns:
        return df[col]

    return pd.Series([""] * len(df), index=df.index)


def convert_gwas_snapshot_to_ingestion_format(
    raw_df: pd.DataFrame,
    max_rows: int = 1000,
) -> pd.DataFrame:
    # Keep only associations for the platform's diseases, then cap the row count.
    trait = _series_or_blank(raw_df, ["DISEASE/TRAIT", "MAPPED_TRAIT", "REPORTED TRAIT", "trait", "disease",
                                      "disease_name"])
    on_platform = trait.astype(str).apply(lambda t: resolve_disease(t) is not None)
    df = raw_df[on_platform].head(int(max_rows)).copy()

    converted = pd.DataFrame()

    converted["rsid"] = _series_or_blank(
        df,
        [
            "SNPS",
            "SNP_ID_CURRENT",
            "STRONGEST SNP-RISK ALLELE",
            "strongest_snp_risk_allele",
            "rsid",
            "snp",
        ]
    )

    converted["disease"] = _series_or_blank(
        df,
        [
            "DISEASE/TRAIT",
            "MAPPED_TRAIT",
            "REPORTED TRAIT",
            "trait",
            "disease",
            "disease_name",
        ]
    )

    converted["gene"] = _series_or_blank(
        df,
        [
            "MAPPED_GENE",
            "REPORTED GENE(S)",
            "gene",
            "gene_symbol",
            "mapped_gene",
        ]
    )

    converted["p-value"] = _series_or_blank(
        df,
        [
            "P-VALUE",
            "PVALUE",
            "p_value",
            "p-value",
        ]
    )

    converted["study_title"] = _series_or_blank(
        df,
        [
            "STUDY",
            "STUDY TITLE",
            "study_title",
            "title",
        ]
    )

    converted["pubmed_id"] = _series_or_blank(
        df,
        [
            "PUBMEDID",
            "PUBMED ID",
            "pubmed_id",
            "pmid",
        ]
    )

    converted["year"] = _series_or_blank(
        df,
        [
            "DATE",
            "PUBLICATION DATE",
            "publication_year",
            "year",
        ]
    )

    converted["population"] = _series_or_blank(
        df,
        [
            "INITIAL SAMPLE SIZE",
            "DISCOVERY SAMPLE ANCESTRY",
            "REPLICATION SAMPLE ANCESTRY",
            "population",
            "ancestry",
        ]
    )

    converted["country"] = _series_or_blank(
        df,
        [
            "COUNTRY",
            "country",
        ]
    )

    converted["odds_ratio"] = _series_or_blank(
        df,
        [
            "OR or BETA",
            "OR_OR_BETA",
            "odds_ratio",
            "or",
        ]
    )

    converted["risk_allele"] = _series_or_blank(
        df,
        [
            "STRONGEST SNP-RISK ALLELE",
            "risk_allele",
            "effect_allele",
        ]
    )

    converted["source_database"] = "GWAS Catalog online snapshot"

    return converted


def save_online_update_log(
    metadata: Dict[str, Any],
    pipeline_result: Optional[Dict[str, Any]] = None
) -> Path:
    output_path = get_outputs_dir() / f"gwas_online_update_log_{_now_stamp()}.csv"

    row = dict(metadata)

    if pipeline_result:
        for key, value in pipeline_result.items():
            if isinstance(value, Path):
                try:
                    row[f"pipeline_{key}"] = str(value.relative_to(get_project_root()))
                except Exception:
                    row[f"pipeline_{key}"] = str(value)
            elif isinstance(value, (dict, list)):
                row[f"pipeline_{key}"] = str(value)
            else:
                row[f"pipeline_{key}"] = value

    pd.DataFrame([row]).to_csv(output_path, index=False, encoding="utf-8-sig")

    return output_path


def run_gwas_online_update(
    url: str = DEFAULT_GWAS_ASSOCIATIONS_URL,
    max_lines: int = 5000,
    max_rows_for_processing: int = 1000,
    uploaded_by: str = "admin",
    notes: str = "Online GWAS Catalog snapshot. Not merged into Search.",
) -> Dict[str, Any]:
    """Controlled online update."""
    if str(url).endswith("/"):
        url = discover_latest_gwas_associations_url(url)

    raw_path, metadata = download_text_snapshot(
        url=url,
        max_lines=max_lines,
    )

    if metadata.get("download_status") != "success":
        log_path = save_online_update_log(metadata)

        return {
            "status": "download_failed",
            "raw_path": raw_path,
            "log_path": log_path,
            "metadata": metadata,
        }

    raw_df = read_online_snapshot(raw_path, nrows=max_rows_for_processing)

    converted_df = convert_gwas_snapshot_to_ingestion_format(
        raw_df=raw_df,
        max_rows=max_rows_for_processing,
    )

    converted_path = get_raw_online_gwas_dir() / f"gwas_online_converted_for_ingestion_{_now_stamp()}.csv"
    converted_df.to_csv(converted_path, index=False, encoding="utf-8-sig")

    from core.admin.data_ingestion import run_uploaded_source_pipeline

    pipeline_result = run_uploaded_source_pipeline(
        raw_file_path=converted_path,
        uploaded_by=uploaded_by,
        source_name=converted_path.name,
        notes=notes,
    )

    try:
        registry_path = get_registry_path()
        registry_df = pd.read_csv(registry_path)

        source_id = pipeline_result.get("source_id", "")
        mask = registry_df["source_id"].astype(str).eq(str(source_id))

        if mask.any():
            registry_df.loc[mask, "source_type"] = "online_gwas"
            registry_df.loc[mask, "notes"] = f"{notes} Original URL: {url}"
            registry_df.to_csv(registry_path, index=False, encoding="utf-8-sig")

    except Exception:
        pass

    log_path = save_online_update_log(metadata, pipeline_result=pipeline_result)

    return {
        "status": "processed",
        "raw_snapshot_path": raw_path,
        "converted_ingestion_path": converted_path,
        "online_update_log_path": log_path,
        "metadata": metadata,
        "pipeline_result": pipeline_result,
    }
