"""
RCT Tests: CLI Plugin Registration Pattern.

Choke Point: CP-CLI-PLUGIN
These tests validate the @cli_plugin decorator pattern contract.

RCT Invariants:
- @cli_plugin decorator registers plugin in CLI_PLUGIN_REGISTRY
- get_cli_plugin() returns registered plugin
- get_cli_plugin() returns None for unknown CLI (not exception)
- list_cli_plugins() returns all registered CLI names
"""

import pytest


@pytest.mark.rct
def test_cli_plugin_decorator_registers_plugin():
    """
    RCT: @cli_plugin decorator registers plugin in CLI_PLUGIN_REGISTRY.

    Given: A class decorated with @cli_plugin("test")
    When: The module is imported
    Then: The plugin is available in CLI_PLUGIN_REGISTRY under "test"
    """
    from mcp_the_force.cli_plugins.registry import (
        CLI_PLUGIN_REGISTRY,
        cli_plugin,
    )

    # Define a test plugin
    @cli_plugin("rct_test_plugin")
    class RCTTestPlugin:
        name = "rct_test_plugin"
        executable = "rct_test"

        def build_new_session_args(self, task, context_dirs):
            return ["--test", task]

        def build_resume_args(self, session_id, task):
            return ["--resume", session_id, task]

    # Verify registration
    assert "rct_test_plugin" in CLI_PLUGIN_REGISTRY
    plugin = CLI_PLUGIN_REGISTRY["rct_test_plugin"]
    assert plugin.name == "rct_test_plugin"
    assert plugin.executable == "rct_test"


@pytest.mark.rct
def test_cli_plugin_registry_roundtrip():
    """
    RCT: get_cli_plugin() returns the same instance registered by decorator.

    Given: A plugin registered via @cli_plugin
    When: get_cli_plugin() is called with the same name
    Then: The returned plugin is the same instance
    """
    from mcp_the_force.cli_plugins.registry import (
        CLI_PLUGIN_REGISTRY,
        cli_plugin,
        get_cli_plugin,
    )

    @cli_plugin("rct_roundtrip_test")
    class RCTRoundtripPlugin:
        name = "rct_roundtrip_test"
        executable = "roundtrip"

        def build_new_session_args(self, task, context_dirs):
            return [task]

        def build_resume_args(self, session_id, task):
            return [session_id, task]

    # Roundtrip: register → retrieve → equals
    registered = CLI_PLUGIN_REGISTRY["rct_roundtrip_test"]
    retrieved = get_cli_plugin("rct_roundtrip_test")

    assert retrieved is registered
    assert retrieved.name == "rct_roundtrip_test"


@pytest.mark.rct
def test_unknown_cli_returns_none():
    """
    RCT: get_cli_plugin() returns None for unknown CLI (not exception).

    Given: A CLI name that doesn't exist
    When: get_cli_plugin() is called
    Then: None is returned (no exception)
    """
    from mcp_the_force.cli_plugins.registry import get_cli_plugin

    result = get_cli_plugin("nonexistent_cli_xyz_123")
    assert result is None


@pytest.mark.rct
def test_list_cli_plugins_returns_all_registered():
    """
    RCT: list_cli_plugins() returns all registered CLI names.

    Given: Multiple plugins registered
    When: list_cli_plugins() is called
    Then: All plugin names are returned
    """
    from mcp_the_force.cli_plugins.registry import (
        cli_plugin,
        list_cli_plugins,
    )

    @cli_plugin("rct_list_test_a")
    class RCTListTestA:
        name = "rct_list_test_a"
        executable = "test_a"

        def build_new_session_args(self, task, context_dirs):
            return [task]

        def build_resume_args(self, session_id, task):
            return [session_id]

    @cli_plugin("rct_list_test_b")
    class RCTListTestB:
        name = "rct_list_test_b"
        executable = "test_b"

        def build_new_session_args(self, task, context_dirs):
            return [task]

        def build_resume_args(self, session_id, task):
            return [session_id]

    plugins = list_cli_plugins()

    assert "rct_list_test_a" in plugins
    assert "rct_list_test_b" in plugins


@pytest.mark.rct
def test_production_plugins_registered_on_package_import():
    """
    RCT: Importing cli_plugins package auto-registers production plugins.

    Given: The cli_plugins package __init__.py imports plugin submodules
    When: We import the package
    Then: Claude, Gemini, and Codex plugins are registered in CLI_PLUGIN_REGISTRY

    This validates the import-time registration mechanism that triggers
    @cli_plugin decorators when the package is imported.
    """
    # Import the package (this triggers __init__.py which imports plugin submodules)
    from mcp_the_force.cli_plugins import get_cli_plugin

    # These must be registered via __init__.py imports
    claude = get_cli_plugin("claude")
    gemini = get_cli_plugin("gemini")
    codex = get_cli_plugin("codex")

    assert claude is not None, "Claude plugin not auto-registered on package import"
    assert gemini is not None, "Gemini plugin not auto-registered on package import"
    assert codex is not None, "Codex plugin not auto-registered on package import"

    # Verify they have the expected executables
    assert claude.executable == "claude"
    assert gemini.executable == "gemini"
    assert codex.executable == "codex"


def test_cli_plugin_registration_rct_loads():
    """Meta-test: Verify RCT test file loads correctly."""
    assert True
