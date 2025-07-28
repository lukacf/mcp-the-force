"""Test to ensure all database files in the codebase are covered by test isolation."""

import re
from pathlib import Path
import pytest


def find_database_references(project_root: Path) -> set[str]:
    """Find all database file references in the codebase."""
    db_patterns = [
        r'["\']([\w\-\.]+\.sqlite3)["\']',
        r'["\']([\w\-\.]+\.db)["\']',
    ]

    found_databases = set()

    # Walk through all Python files
    for py_file in project_root.rglob("*.py"):
        # Skip test files and virtual environments
        if (
            "test" in str(py_file)
            or ".venv" in str(py_file)
            or "__pycache__" in str(py_file)
        ):
            continue

        try:
            content = py_file.read_text()
            for pattern in db_patterns:
                matches = re.findall(pattern, content)
                found_databases.update(matches)
        except Exception:
            # Skip files we can't read
            continue

    return found_databases


def test_all_databases_are_isolated():
    """Ensure all database files mentioned in code are in the isolation set."""
    # Import the PRODUCTION_DBS set from conftest
    from tests.conftest import PRODUCTION_DBS

    # Find project root (parent of tests directory)
    project_root = Path(__file__).parent.parent.parent / "mcp_the_force"

    # Find all database references in the code
    found_databases = find_database_references(project_root)

    # Check if any databases are missing from isolation
    missing_databases = found_databases - PRODUCTION_DBS

    if missing_databases:
        pytest.fail(
            f"The following database files are referenced in code but not in "
            f"PRODUCTION_DBS isolation set in tests/conftest.py:\n"
            f"{missing_databases}\n\n"
            f"Add these to the PRODUCTION_DBS set to ensure proper test isolation."
        )


def test_production_dbs_export():
    """Ensure PRODUCTION_DBS is properly exported from conftest."""
    try:
        from tests.conftest import PRODUCTION_DBS

        assert isinstance(PRODUCTION_DBS, set)
        assert len(PRODUCTION_DBS) > 0
    except ImportError:
        pytest.fail("PRODUCTION_DBS must be exported from tests/conftest.py")
