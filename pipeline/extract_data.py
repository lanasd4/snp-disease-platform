"""
Data Extraction Script
"""

from pathlib import Path
from datetime import datetime
from urllib.error import HTTPError, URLError
import urllib.request
import gzip
import json
import pandas as pd
from core.paths import get_project_root


GWAS_DOWNLOAD_URLS = [
    # Stable FTP-style latest release candidates
    "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/gwas-catalog-associations.tsv",
    "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/gwas-catalog-associations_ontology-annotated.tsv",

    # HTTP versions, in case HTTPS has an issue in the runtime
    "http://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/gwas-catalog-associations.tsv",
    "http://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/gwas-catalog-associations_ontology-annotated.tsv",

    # Historical known GWAS Catalog release fallback
    "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/2020/05/20/gwas-catalog-associations.tsv",
    "http://ftp.ebi.ac.uk/pub/databases/gwas/releases/2020/05/20/gwas-catalog-associations.tsv",

    # API-style endpoints as lower-priority fallback
    "https://www.ebi.ac.uk/gwas/api/search/downloads/alternative",
    "https://www.ebi.ac.uk/gwas/api/search/downloads/full"
]


def get_data_paths() -> dict:
    """Return important project folders used by the extraction pipeline."""
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "raw": project_root / "data" / "raw",
        "processed": project_root / "data" / "processed",
        "outputs_tables": project_root / "outputs" / "tables",
    }


def ensure_data_directories() -> dict:
    """Create required folders if they do not exist."""
    paths = get_data_paths()

    paths["raw"].mkdir(parents=True, exist_ok=True)
    paths["processed"].mkdir(parents=True, exist_ok=True)
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)

    return paths


def save_metadata(metadata: dict, filename: str) -> Path:
    """Save metadata as a JSON file inside data/raw."""
    paths = ensure_data_directories()
    output_path = paths["raw"] / filename

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return output_path


def _response_looks_gzip(response) -> bool:
    """Detect whether the downloaded file is gzip-compressed."""
    content_type = response.headers.get("Content-Type", "").lower()
    content_encoding = response.headers.get("Content-Encoding", "").lower()
    content_disposition = response.headers.get("Content-Disposition", "").lower()

    return (
        "gzip" in content_type
        or "gzip" in content_encoding
        or ".gz" in content_disposition
    )


def _validate_first_line_is_gwas_tsv(first_line: bytes) -> None:
    """Make sure the downloaded content looks like a GWAS TSV file."""
    decoded = first_line.decode("utf-8", errors="replace")

    expected_tokens = [
        "DISEASE/TRAIT",
        "SNPS",
        "P-VALUE",
        "PUBMEDID",
        "MAPPED_GENE"
    ]

    if "\t" not in decoded:
        raise ValueError("Downloaded content does not look like TSV because the header has no tab separators.")

    if not any(token in decoded for token in expected_tokens):
        raise ValueError("Downloaded TSV header does not look like a GWAS Catalog associations file.")


def download_gwas_catalog_raw_sample(
    output_filename: str = "gwas_catalog_associations_sample_raw.tsv",
    max_lines: int = 5000
) -> dict:
    """Download a real raw sample from a GWAS Catalog associations file."""
    paths = ensure_data_directories()
    output_path = paths["raw"] / output_filename

    failed_urls = []
    selected_url = None
    final_url = None
    content_type = ""
    content_disposition = ""
    line_count = 0

    for url in GWAS_DOWNLOAD_URLS:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "SNP-Disease-Platform/1.0"
                }
            )

            with urllib.request.urlopen(request, timeout=180) as response:
                final_url = response.geturl()
                content_type = response.headers.get("Content-Type", "")
                content_disposition = response.headers.get("Content-Disposition", "")

                is_gzip = _response_looks_gzip(response)

                if is_gzip:
                    input_stream = gzip.GzipFile(fileobj=response)
                else:
                    input_stream = response

                first_line = input_stream.readline()

                if not first_line:
                    raise ValueError("Downloaded file is empty.")

                _validate_first_line_is_gwas_tsv(first_line)

                with open(output_path, "wb") as file:
                    file.write(first_line)
                    line_count = 1

                    while line_count < max_lines:
                        line = input_stream.readline()

                        if not line:
                            break

                        file.write(line)
                        line_count += 1

            selected_url = url
            break

        except HTTPError as e:
            failed_urls.append({
                "url": url,
                "error_type": "HTTPError",
                "status_code": e.code,
                "message": str(e)
            })

        except URLError as e:
            failed_urls.append({
                "url": url,
                "error_type": "URLError",
                "message": str(e)
            })

        except Exception as e:
            failed_urls.append({
                "url": url,
                "error_type": type(e).__name__,
                "message": str(e)
            })

    if selected_url is None:
        print("All candidate GWAS URLs failed:")
        for item in failed_urls:
            print("-", item)

        raise RuntimeError(
            "All GWAS download URLs failed. The runtime may not access the EBI FTP/download endpoints, or the endpoints changed."
        )

    metadata = {
        "file_name": output_path.name,
        "source_name": "GWAS Catalog",
        "selected_url": selected_url,
        "final_url": final_url,
        "tried_urls": GWAS_DOWNLOAD_URLS,
        "failed_urls": failed_urls,
        "content_type": content_type,
        "content_disposition": content_disposition,
        "is_real_data": True,
        "is_partial_sample": True,
        "max_lines_requested": max_lines,
        "lines_saved": line_count,
        "stage": "First Real Raw Data Sample",
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        "note": "This is a partial raw sample from GWAS Catalog. It is saved as plain TSV and has not been cleaned or normalized."
    }

    metadata_path = save_metadata(
        metadata,
        "gwas_catalog_associations_sample_metadata.json"
    )

    return {
        "raw_path": str(output_path),
        "metadata_path": str(metadata_path),
        "lines_saved": line_count,
        "selected_url": selected_url
    }


def create_preview_from_tsv(
    raw_filename: str,
    preview_filename: str = "gwas_raw_preview.csv",
    nrows: int = 20
) -> Path:
    """Read the first rows of a raw TSV file and save them as CSV preview."""
    paths = ensure_data_directories()

    raw_path = paths["raw"] / raw_filename
    preview_path = paths["outputs_tables"] / preview_filename

    df = pd.read_csv(raw_path, sep="\t", dtype=str, nrows=nrows)
    df.to_csv(preview_path, index=False, encoding="utf-8-sig")

    return preview_path


def profile_columns(
    raw_filename: str,
    profile_filename: str = "gwas_columns_profile.csv",
    nrows: int = 5000
) -> Path:
    """Create a simple column profile for the raw GWAS sample."""
    paths = ensure_data_directories()

    raw_path = paths["raw"] / raw_filename
    profile_path = paths["outputs_tables"] / profile_filename

    df = pd.read_csv(raw_path, sep="\t", dtype=str, nrows=nrows)

    rows = []

    for column in df.columns:
        non_empty_count = int(df[column].notna().sum())
        empty_count = int(df[column].isna().sum())

        examples = (
            df[column]
            .dropna()
            .astype(str)
            .head(3)
            .tolist()
        )

        rows.append({
            "column_name": column,
            "non_empty_count": non_empty_count,
            "empty_count": empty_count,
            "example_values": " | ".join(examples)
        })

    profile_df = pd.DataFrame(rows)
    profile_df.to_csv(profile_path, index=False, encoding="utf-8-sig")

    return profile_path


def run_gwas_sample_download(max_lines: int = 5000) -> dict:
    download_result = download_gwas_catalog_raw_sample(max_lines=max_lines)

    preview_path = create_preview_from_tsv(
        raw_filename="gwas_catalog_associations_sample_raw.tsv"
    )

    profile_path = profile_columns(
        raw_filename="gwas_catalog_associations_sample_raw.tsv"
    )

    return {
        **download_result,
        "preview_path": str(preview_path),
        "profile_path": str(profile_path)
    }


def main() -> None:
    result = run_gwas_sample_download(max_lines=5000)

    print("GWAS raw sample download completed.")
    print(f"Selected URL: {result['selected_url']}")
    print(f"Raw file: {result['raw_path']}")
    print(f"Metadata file: {result['metadata_path']}")
    print(f"Preview file: {result['preview_path']}")
    print(f"Columns profile: {result['profile_path']}")
    print(f"Lines saved: {result['lines_saved']}")


if __name__ == "__main__":
    main()
