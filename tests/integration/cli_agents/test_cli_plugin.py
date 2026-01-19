"""
Integration Tests: CLI Plugin Registration and Discovery.

Choke Point: CP-CLI-PLUGIN
These tests verify CLI plugins are properly registered and discoverable.

Integration Invariants:
- Claude, Gemini, Codex plugins are registered at import time
- Each plugin implements the CLIPlugin protocol
- All model blueprints with `cli` attribute map to valid plugins
"""

import pytest


@pytest.mark.integration
@pytest.mark.cli_agents
def test_claude_plugin_registered():
    """
    CP-CLI-PLUGIN: Claude plugin is registered.

    Given: The cli_plugins package is imported
    When: get_cli_plugin("claude") is called
    Then: A valid Claude plugin is returned
    """
    from mcp_the_force.cli_plugins.registry import get_cli_plugin

    plugin = get_cli_plugin("claude")
    assert plugin is not None, "Claude plugin should be registered"
    assert plugin.executable == "claude"


@pytest.mark.integration
@pytest.mark.cli_agents
def test_gemini_plugin_registered():
    """
    CP-CLI-PLUGIN: Gemini plugin is registered.

    Given: The cli_plugins package is imported
    When: get_cli_plugin("gemini") is called
    Then: A valid Gemini plugin is returned
    """
    from mcp_the_force.cli_plugins.registry import get_cli_plugin

    plugin = get_cli_plugin("gemini")
    assert plugin is not None, "Gemini plugin should be registered"
    assert plugin.executable == "gemini"


@pytest.mark.integration
@pytest.mark.cli_agents
def test_codex_plugin_registered():
    """
    CP-CLI-PLUGIN: Codex plugin is registered.

    Given: The cli_plugins package is imported
    When: get_cli_plugin("codex") is called
    Then: A valid Codex plugin is returned
    """
    from mcp_the_force.cli_plugins.registry import get_cli_plugin

    plugin = get_cli_plugin("codex")
    assert plugin is not None, "Codex plugin should be registered"
    assert plugin.executable == "codex"


@pytest.mark.integration
@pytest.mark.cli_agents
def test_plugin_implements_protocol():
    """
    CP-CLI-PLUGIN: All registered plugins implement CLIPlugin protocol.

    Given: All registered plugins
    When: We check their methods
    Then: Each has executable, build_new_session_args, build_resume_args
    """
    from mcp_the_force.cli_plugins.registry import get_cli_plugin

    # Only check production plugins, not test plugins from RCT
    production_plugins = ["claude", "gemini", "codex"]

    for name in production_plugins:
        plugin = get_cli_plugin(name)
        assert plugin is not None

        # Check protocol methods exist
        assert hasattr(plugin, "executable"), f"{name} plugin missing executable"
        assert hasattr(
            plugin, "build_new_session_args"
        ), f"{name} plugin missing build_new_session_args"
        assert hasattr(
            plugin, "build_resume_args"
        ), f"{name} plugin missing build_resume_args"
        assert hasattr(plugin, "parse_output"), f"{name} plugin missing parse_output"

        # Check executable is a string
        assert isinstance(
            plugin.executable, str
        ), f"{name} plugin executable not a string"


@pytest.mark.integration
@pytest.mark.cli_agents
def test_all_blueprints_with_cli_have_valid_plugins():
    """
    CP-CLI-PLUGIN: All model blueprints with cli attribute map to valid plugins.

    Given: All model blueprints in the adapter registry
    When: We check those with `cli` attribute
    Then: Each cli value maps to a registered plugin
    """
    from mcp_the_force.cli_agents.model_cli_resolver import get_all_cli_models
    from mcp_the_force.cli_plugins.registry import get_cli_plugin

    # Get all models that have CLI mappings
    cli_models = get_all_cli_models()

    # Verify each CLI name has a registered plugin
    cli_names_seen = set()
    for model_name, cli_name in cli_models.items():
        cli_names_seen.add(cli_name)

    for cli_name in cli_names_seen:
        plugin = get_cli_plugin(cli_name)
        assert plugin is not None, f"CLI '{cli_name}' should have a registered plugin"


@pytest.mark.integration
@pytest.mark.cli_agents
def test_plugin_builds_valid_commands():
    """
    CP-CLI-PLUGIN: Plugins build valid command arguments.

    Given: A registered plugin
    When: We call build_new_session_args and build_resume_args
    Then: Valid command lists are returned
    """
    from mcp_the_force.cli_plugins.registry import get_cli_plugin

    # Test Claude plugin
    claude = get_cli_plugin("claude")
    new_args = claude.build_new_session_args(task="Test task", context_dirs=["/tmp"])
    resume_args = claude.build_resume_args(session_id="abc123", task="Continue")

    assert isinstance(new_args, list)
    assert isinstance(resume_args, list)
    assert "Test task" in new_args or any("Test task" in str(a) for a in new_args)
    assert "--resume" in resume_args  # Claude uses --resume flag

    # Test Codex plugin (different resume pattern!)
    codex = get_cli_plugin("codex")
    codex_resume = codex.build_resume_args(session_id="thread123", task="Continue")

    assert "exec" in codex_resume  # Codex uses 'exec resume', NOT --resume
    assert "resume" in codex_resume
    assert "--resume" not in codex_resume  # This would be wrong for Codex!


@pytest.mark.integration
@pytest.mark.cli_agents
def test_plugin_parse_output_delegates_to_parser():
    """
    CP-CLI-PLUGIN + CP-PARSER: Plugin.parse_output() delegates to its internal parser.

    Given: A CLI plugin with its internal parser
    When: parse_output is called with valid CLI output
    Then: It correctly extracts session_id and content via the parser
    """
    from mcp_the_force.cli_plugins.claude import ClaudePlugin
    from mcp_the_force.cli_plugins.gemini import GeminiPlugin
    from mcp_the_force.cli_plugins.codex import CodexPlugin

    # Claude: JSON array format
    claude_output = '[{"type":"system","subtype":"init","session_id":"claude-test-123","tools":[]},{"type":"result","subtype":"success","result":"Hello from Claude"}]'
    claude_plugin = ClaudePlugin()
    claude_result = claude_plugin.parse_output(claude_output)
    assert claude_result.session_id == "claude-test-123"
    assert "Hello" in claude_result.content

    # Gemini: JSON object format
    gemini_output = (
        '{"session_id":"gemini-test-456","response":"Hello from Gemini","stats":{}}'
    )
    gemini_plugin = GeminiPlugin()
    gemini_result = gemini_plugin.parse_output(gemini_output)
    assert gemini_result.session_id == "gemini-test-456"
    assert "Hello" in gemini_result.content

    # Codex: JSONL format with thread_id (NOT session_id)
    # Content is in item.text (agent_message type only)
    codex_output = '{"type":"thread.started","thread_id":"codex-thread-789"}\n{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Hello from Codex"}}'
    codex_plugin = CodexPlugin()
    codex_result = codex_plugin.parse_output(codex_output)
    assert (
        codex_result.session_id == "codex-thread-789"
    )  # thread_id mapped to session_id
    assert "Hello" in codex_result.content


def test_cli_plugin_integration_tests_load():
    """Meta-test: Verify integration test file loads correctly."""
    assert True
