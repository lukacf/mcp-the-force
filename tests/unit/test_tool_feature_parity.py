"""Unit tests to ensure feature parity across tool definitions."""

import pytest

from mcp_second_brain.tools.definitions import (
    ChatWithGemini25Pro,
    ChatWithGemini25Flash,
    ChatWithO3,
    ChatWithO3Pro,
    ChatWithGPT4_1,
    ChatWithGrok4,
    ChatWithGrok3Reasoning,
)
from mcp_second_brain.tools.descriptors import RouteDescriptor, RouteType


# Define expected features for each model category
OPENAI_MODELS = [ChatWithO3, ChatWithO3Pro, ChatWithGPT4_1]
REASONING_MODELS = [ChatWithO3, ChatWithO3Pro]  # Only o3 models support reasoning
GEMINI_MODELS = [ChatWithGemini25Pro, ChatWithGemini25Flash]
GROK_MODELS = [ChatWithGrok4, ChatWithGrok3Reasoning]
ALL_CHAT_MODELS = OPENAI_MODELS + GEMINI_MODELS + GROK_MODELS

# Features that should be present in all chat models
REQUIRED_FEATURES = {
    "instructions": RouteType.PROMPT,
    "output_format": RouteType.PROMPT,
    "context": RouteType.PROMPT,
    "session_id": RouteType.SESSION,
}

# Optional features that should be consistent within model families
OPTIONAL_FEATURES = {
    "attachments": RouteType.VECTOR_STORE,
    "temperature": RouteType.ADAPTER,
}

# Model-specific features
OPENAI_SPECIFIC = {
    "reasoning_effort": RouteType.ADAPTER,
}


class TestToolFeatureParity:
    """Test that tool definitions have consistent features."""

    def test_all_models_have_required_features(self):
        """All chat models should have the required base features."""
        for model_class in ALL_CHAT_MODELS:
            for feature, expected_route_type in REQUIRED_FEATURES.items():
                # Check the attribute exists
                assert hasattr(model_class, feature), (
                    f"{model_class.__name__} missing required feature: {feature}"
                )

                # Check it's the right type of route
                attr = getattr(model_class, feature)
                if isinstance(attr, RouteDescriptor):
                    assert attr.route == expected_route_type, (
                        f"{model_class.__name__}.{feature} has wrong route type"
                    )

    def test_all_models_have_attachments_support(self):
        """All chat models should support attachments for RAG."""
        for model_class in ALL_CHAT_MODELS:
            assert hasattr(model_class, "attachments"), (
                f"{model_class.__name__} missing attachments parameter - cannot use RAG"
            )

            attr = getattr(model_class, "attachments")
            if isinstance(attr, RouteDescriptor):
                assert attr.route == RouteType.VECTOR_STORE, (
                    f"{model_class.__name__}.attachments should be Route.vector_store"
                )

    def test_reasoning_models_have_reasoning_effort(self):
        """O3 models should have reasoning_effort parameter."""
        for model_class in REASONING_MODELS:
            assert hasattr(model_class, "reasoning_effort"), (
                f"{model_class.__name__} missing reasoning_effort parameter"
            )

        # GPT-4.1 should NOT have reasoning_effort
        assert not hasattr(ChatWithGPT4_1, "reasoning_effort"), (
            "ChatWithGPT4_1 should not have reasoning_effort - it doesn't support reasoning parameters"
        )

    def test_gemini_models_have_reasoning_effort(self):
        """Gemini models should have reasoning_effort (now supported via thinking_budget)."""
        for model_class in GEMINI_MODELS:
            assert hasattr(model_class, "reasoning_effort"), (
                f"{model_class.__name__} should have reasoning_effort - Gemini now supports it via thinking_budget"
            )

    def test_consistent_parameter_ordering(self):
        """Positional parameters should be in consistent order across models."""
        for model_class in ALL_CHAT_MODELS:
            # Get all parameters with positions
            params_with_pos = []
            for name in dir(model_class):
                if name.startswith("_"):
                    continue
                attr = getattr(model_class, name)
                if (
                    isinstance(attr, RouteDescriptor)
                    and hasattr(attr, "position")
                    and attr.position is not None
                ):
                    params_with_pos.append((name, attr.position))

            # Sort by position
            params_with_pos.sort(key=lambda x: x[1])

            # Check expected order for positional params
            expected_order = ["instructions", "output_format", "context"]
            actual_order = [name for name, _ in params_with_pos]

            assert actual_order[:3] == expected_order, (
                f"{model_class.__name__} has incorrect parameter ordering: {actual_order}"
            )

    def test_all_models_have_descriptions(self):
        """All model classes should have docstrings describing their capabilities."""
        for model_class in ALL_CHAT_MODELS:
            assert model_class.__doc__ is not None, (
                f"{model_class.__name__} missing docstring"
            )
            assert len(model_class.__doc__) > 50, (
                f"{model_class.__name__} docstring too short"
            )
            assert "Example usage:" in model_class.__doc__, (
                f"{model_class.__name__} docstring missing usage examples"
            )

    def test_model_metadata_consistency(self):
        """Model metadata should be consistent within families."""
        # Check Gemini models
        for model_class in GEMINI_MODELS:
            assert model_class.adapter_class == "vertex", (
                f"{model_class.__name__} should use vertex adapter"
            )
            assert model_class.context_window == 1_000_000, (
                f"{model_class.__name__} should have 1M context window"
            )

        # Check OpenAI models
        for model_class in OPENAI_MODELS:
            assert model_class.adapter_class == "openai", (
                f"{model_class.__name__} should use openai adapter"
            )

            # O3 models should have 200k context
            if "O3" in model_class.__name__:
                assert model_class.context_window == 200_000, (
                    f"{model_class.__name__} should have 200k context window"
                )
            # GPT-4.1 should have 1M context
            elif "GPT4_1" in model_class.__name__:
                assert model_class.context_window == 1_000_000, (
                    f"{model_class.__name__} should have 1M context window"
                )

        # Check Grok models
        for model_class in GROK_MODELS:
            assert model_class.adapter_class == "xai", (
                f"{model_class.__name__} should use xai adapter"
            )

            # Grok 4 should have 256k context
            if "Grok4" in model_class.__name__:
                assert model_class.context_window == 256_000, (
                    f"{model_class.__name__} should have 256k context window"
                )
            # Other Grok models should have 131k context
            else:
                assert model_class.context_window == 131_000, (
                    f"{model_class.__name__} should have 131k context window"
                )

    def test_no_duplicate_parameter_positions(self):
        """No model should have duplicate position numbers for parameters."""
        for model_class in ALL_CHAT_MODELS:
            positions_used = {}

            for name in dir(model_class):
                if name.startswith("_"):
                    continue
                attr = getattr(model_class, name)
                if (
                    isinstance(attr, RouteDescriptor)
                    and hasattr(attr, "position")
                    and attr.position is not None
                ):
                    pos = attr.position
                    if pos in positions_used:
                        pytest.fail(
                            f"{model_class.__name__}: Position {pos} used by both "
                            f"'{positions_used[pos]}' and '{name}'"
                        )
                    positions_used[pos] = name
