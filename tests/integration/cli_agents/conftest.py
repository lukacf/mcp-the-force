"""
Conftest for CLI Agents integration tests.

Ensures all adapter blueprints are registered before tests run.
"""

import pytest


@pytest.fixture(autouse=True)
def register_all_blueprints():
    """Import all adapters to trigger blueprint registration.

    This is necessary because model_cli_resolver uses get_blueprints()
    which only returns blueprints that have been registered via adapter imports.
    """
    # Import all adapter definition modules to trigger blueprint registration
    # Order doesn't matter since blueprints are accumulated in a list
    from mcp_the_force.adapters.openai import definitions as openai_defs  # noqa: F401
    from mcp_the_force.adapters.google import definitions as google_defs  # noqa: F401
    from mcp_the_force.adapters.xai import definitions as xai_defs  # noqa: F401
    from mcp_the_force.adapters.anthropic import blueprints as anthropic_bps  # noqa: F401

    yield
