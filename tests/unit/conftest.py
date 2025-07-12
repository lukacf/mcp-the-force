"""Unit test specific configuration."""

import os

# Set test mode before any imports to speed up tests
os.environ["FASTMCP_TEST_MODE"] = "1"


# Import mock_env from parent conftest
from tests.conftest import mock_env  # noqa: F401, E402
