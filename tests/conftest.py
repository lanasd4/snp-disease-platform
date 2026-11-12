"""
Shared pytest setup.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_tmp_dir = Path(tempfile.mkdtemp(prefix="snp_tests_"))
_test_db = _tmp_dir / "snp_platform_test.db"
shutil.copy(PROJECT_ROOT / "database" / "snp_platform.db", _test_db)

# Must be set before core.paths is first imported.
os.environ["SNP_DATABASE_PATH"] = str(_test_db)
# Never read the developer's local .streamlit/secrets.toml (admin password etc.).
os.environ["SNP_IGNORE_SECRETS"] = "1"
