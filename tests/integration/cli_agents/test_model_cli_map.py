"""
Integration Tests: Model → CLI Plugin Resolution.

Choke Point: CP-MODEL-CLI-MAP
Phase 1: Real tests that fail because code not implemented yet.

This tests the internal routing logic that resolves model names to CLI plugins.
This is NOT an RCT test because it's internal logic, not an external contract.
"""

import pytest


@pytest.mark.integration
@pytest.mark.cli_agents
def test_openai_models_resolve_to_codex_cli():
    """
    CP-MODEL-CLI-MAP: OpenAI → Codex resolution.

    Given: An OpenAI model name
    When: The model registry is queried for CLI mapping
    Then: It resolves to 'codex' CLI plugin
    """
    from mcp_the_force.cli_agents.model_cli_resolver import resolve_model_to_cli

    # All OpenAI models should resolve to codex
    openai_models = [
        "gpt-5.2",
        "gpt-5.2-pro",
        "gpt-4.1",
        "gpt-5.1-codex-max",
    ]

    for model_name in openai_models:
        cli_name = resolve_model_to_cli(model_name)
        assert (
            cli_name == "codex"
        ), f"{model_name} should resolve to 'codex', got '{cli_name}'"


@pytest.mark.integration
@pytest.mark.cli_agents
def test_anthropic_models_resolve_to_claude_cli():
    """
    CP-MODEL-CLI-MAP: Anthropic → Claude resolution.

    Given: An Anthropic model name
    When: The model registry is queried for CLI mapping
    Then: It resolves to 'claude' CLI plugin
    """
    from mcp_the_force.cli_agents.model_cli_resolver import resolve_model_to_cli

    # All Anthropic models should resolve to claude
    # NOTE: claude-3-opus is NOT supported (deprecated per RCT 2026-01-18)
    anthropic_models = [
        "claude-sonnet-4-5",
        "claude-opus-4-5",
    ]

    for model_name in anthropic_models:
        cli_name = resolve_model_to_cli(model_name)
        assert (
            cli_name == "claude"
        ), f"{model_name} should resolve to 'claude', got '{cli_name}'"


@pytest.mark.integration
@pytest.mark.cli_agents
def test_google_models_resolve_to_gemini_cli():
    """
    CP-MODEL-CLI-MAP: Google → Gemini resolution.

    Given: A Google model name
    When: The model registry is queried for CLI mapping
    Then: It resolves to 'gemini' CLI plugin
    """
    from mcp_the_force.cli_agents.model_cli_resolver import resolve_model_to_cli

    # All Google models should resolve to gemini
    google_models = [
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
    ]

    for model_name in google_models:
        cli_name = resolve_model_to_cli(model_name)
        assert (
            cli_name == "gemini"
        ), f"{model_name} should resolve to 'gemini', got '{cli_name}'"


@pytest.mark.integration
@pytest.mark.cli_agents
def test_unknown_model_raises_error():
    """
    CP-MODEL-CLI-MAP: Unknown model handling.

    Given: An unknown model name
    When: The model registry is queried for CLI mapping
    Then: It raises ModelNotFoundError with helpful message
    """
    from mcp_the_force.cli_agents.model_cli_resolver import (
        ModelNotFoundError,
        resolve_model_to_cli,
    )

    with pytest.raises(ModelNotFoundError) as exc_info:
        resolve_model_to_cli("nonexistent-model-xyz")

    assert "nonexistent-model-xyz" in str(exc_info.value)


@pytest.mark.integration
@pytest.mark.cli_agents
def test_model_without_cli_raises_error():
    """
    CP-MODEL-CLI-MAP: Model without CLI attribute.

    Given: A model that exists but has no CLI mapping (API-only)
    When: The model registry is queried for CLI mapping
    Then: It raises NoCLIAvailableError

    Note: This tests models that exist in registry but are API-only
    (e.g., research models like o3-deep-research).
    """
    from mcp_the_force.cli_agents.model_cli_resolver import (
        NoCLIAvailableError,
        resolve_model_to_cli,
    )

    # o3-deep-research is API-only, no CLI
    with pytest.raises(NoCLIAvailableError) as exc_info:
        resolve_model_to_cli("o3-deep-research")

    assert "o3-deep-research" in str(exc_info.value)


@pytest.mark.integration
@pytest.mark.cli_agents
def test_resolver_uses_model_registry_blueprints():
    """
    CP-MODEL-CLI-MAP: Integration with model registry.

    Given: The model registry has blueprints with cli attributes
    When: We resolve a model name
    Then: The resolution uses the blueprint's cli attribute
    """
    from mcp_the_force.cli_agents.model_cli_resolver import resolve_model_to_cli
    from mcp_the_force.tools.blueprint_registry import get_blueprints

    # Get blueprints from the registry
    blueprints = get_blueprints()
    assert len(blueprints) > 0, "Blueprints should be registered"

    # Find gpt-5.2 blueprint
    gpt52_blueprint = None
    for bp in blueprints:
        if bp.model_name == "gpt-5.2":
            gpt52_blueprint = bp
            break

    assert gpt52_blueprint is not None, "gpt-5.2 should be in blueprint registry"
    assert hasattr(gpt52_blueprint, "cli"), "Blueprint should have cli attribute"
    assert gpt52_blueprint.cli == "codex", "gpt-5.2 blueprint should have cli='codex'"

    # Verify resolver returns the same value
    cli_name = resolve_model_to_cli("gpt-5.2")
    assert cli_name == gpt52_blueprint.cli


@pytest.mark.integration
@pytest.mark.cli_agents
def test_all_cli_mappings_are_valid_plugins():
    """
    CP-MODEL-CLI-MAP: CLI names map to valid plugins.

    Given: All models with CLI mappings
    When: We collect all unique CLI names
    Then: Each CLI name corresponds to a registered CLI plugin
    """
    from mcp_the_force.cli_agents.model_cli_resolver import get_all_cli_models
    from mcp_the_force.cli_plugins.registry import get_cli_plugin

    # Get all models that have CLI mappings
    cli_models = get_all_cli_models()

    # Collect unique CLI names
    cli_names = set()
    for model_name, cli_name in cli_models.items():
        cli_names.add(cli_name)

    # Verify each CLI name has a registered plugin
    for cli_name in cli_names:
        plugin = get_cli_plugin(cli_name)
        assert plugin is not None, f"CLI '{cli_name}' should have a registered plugin"


def test_model_cli_map_integration_tests_load():
    """Meta-test: Verify integration test file loads correctly."""
    assert True
