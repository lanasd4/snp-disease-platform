"""
Project paths: the single source of truth for every file location.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Top-level folders
APP_DIR = PROJECT_ROOT / "app"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
METADATA_DIR = DATA_DIR / "metadata"
DATABASE_DIR = PROJECT_ROOT / "database"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUT_TABLES_DIR = OUTPUTS_DIR / "tables"
OUTPUT_MODELS_DIR = OUTPUTS_DIR / "models"
DOCS_DIR = PROJECT_ROOT / "docs"

# Database (override with the SNP_DATABASE_PATH env var, e.g. for tests or hosting)
# (a relative value is resolved from the project root).
DATABASE_PATH = Path(os.environ.get("SNP_DATABASE_PATH") or DATABASE_DIR / "snp_platform.db")
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = (PROJECT_ROOT / DATABASE_PATH).resolve()

# Core data files
MASTER_DISEASES_FILE = DATA_DIR / "master_diseases.csv"
DISEASE_SYNONYMS_FILE = DATA_DIR / "disease_synonyms.csv"
RANKED_ASSOCIATIONS_FILE = PROCESSED_DATA_DIR / "ranked_associations_initial.csv"
REGIONAL_TAGGED_FILE = PROCESSED_DATA_DIR / "regional_tagged_associations.csv"
DATA_SOURCES_REGISTRY_FILE = METADATA_DIR / "data_sources_registry.csv"
DISEASE_PROFILES_FILE = METADATA_DIR / "disease_profiles.csv"
ML_REGION_MODEL_FILE = OUTPUT_MODELS_DIR / "ml_region_classifier_pipeline.joblib"

# UI assets
STYLES_FILE = APP_DIR / "ui" / "styles.css"
LOGO_FILE = APP_DIR / "assets" / "logo_web.png"  # trimmed, 520 px copy of logo.png
FAVICON_FILE = APP_DIR / "assets" / "favicon.png"


def get_project_root() -> Path:
    """Return the project root folder (kept for modules that call it as a function)."""
    return PROJECT_ROOT
