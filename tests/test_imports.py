"""
Every module in app/, core/ and pipeline/ must import cleanly (catches broken paths/imports).
"""

import importlib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# app/main.py is the Streamlit entry script (calls st.set_page_config at import),
# it is covered by test_pages_smoke.py instead.
SKIP = {"app.main"}


def _all_modules():
    for package in ("app", "core", "pipeline"):
        for path in sorted((PROJECT_ROOT / package).rglob("*.py")):
            module = ".".join(path.relative_to(PROJECT_ROOT).with_suffix("").parts)
            module = module.removesuffix(".__init__")
            if module not in SKIP:
                yield module


@pytest.mark.parametrize("module_name", list(_all_modules()))
def test_module_imports(module_name):
    importlib.import_module(module_name)


def test_core_paths_point_to_existing_files():
    from core import paths

    for name in ("DATABASE_PATH", "RANKED_ASSOCIATIONS_FILE", "DATA_SOURCES_REGISTRY_FILE",
                 "STYLES_FILE", "LOGO_FILE", "MASTER_DISEASES_FILE"):
        assert getattr(paths, name).exists(), f"core.paths.{name} is missing"
