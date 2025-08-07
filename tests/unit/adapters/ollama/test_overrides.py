"""Unit tests for Ollama overrides module."""

import pytest
from unittest.mock import patch, AsyncMock

from mcp_the_force.config import ModelOverride
from mcp_the_force.adapters.ollama.overrides import (
    resolve_override,
    resolve_model_capabilities,
)


class TestResolveOverride:
    """Tests for resolve_override function."""

    def test_exact_match_priority(self):
        """Test that exact match has highest priority."""
        overrides = [
            ModelOverride(match="llama*", max_context_window=16384),
            ModelOverride(match="llama3:latest", max_context_window=32768),
            ModelOverride(regex=r"llama\d+", max_context_window=8192),
        ]

        override = resolve_override("llama3:latest", overrides)
        assert override is not None
        assert override.max_context_window == 32768

    def test_glob_match(self):
        """Test glob pattern matching."""
        overrides = [
            ModelOverride(match="mistral*", max_context_window=16384),
            ModelOverride(match="llama*", max_context_window=32768),
        ]

        # Test matching patterns
        override = resolve_override("mistral-7b:latest", overrides)
        assert override is not None
        assert override.max_context_window == 16384

        override = resolve_override("llama3:q4", overrides)
        assert override is not None
        assert override.max_context_window == 32768

        # Test non-matching
        override = resolve_override("gpt-oss:120b", overrides)
        assert override is None

    def test_regex_match(self):
        """Test regex pattern matching."""
        overrides = [
            ModelOverride(
                regex=r".*:q[48]_.*",
                max_context_window=8192,
                description="Quantized models",
            ),
            ModelOverride(regex=r"gpt-oss:\d+b", max_context_window=65536),
        ]

        # Test matching patterns
        override = resolve_override("llama3:q4_0", overrides)
        assert override is not None
        assert override.max_context_window == 8192
        assert override.description == "Quantized models"

        override = resolve_override("gpt-oss:120b", overrides)
        assert override is not None
        assert override.max_context_window == 65536

        # Test non-matching
        override = resolve_override("llama3:latest", overrides)
        assert override is None

    def test_first_match_wins(self):
        """Test that first matching override in category wins."""
        overrides = [
            ModelOverride(match="llama*", max_context_window=16384),
            ModelOverride(
                match="llama3*", max_context_window=32768
            ),  # More specific but later
        ]

        override = resolve_override("llama3:latest", overrides)
        assert override is not None
        assert override.max_context_window == 16384  # First match wins

    def test_no_matching_regex_falls_back_to_glob(self):
        """Test that non-matching regex patterns fall back to glob matches."""
        overrides = [
            ModelOverride(
                regex=r"mistral.*", max_context_window=8192
            ),  # Valid regex, but won't match
            ModelOverride(
                match="llama*", max_context_window=16384
            ),  # Glob that will match
        ]

        # Should skip non-matching regex and use glob match
        override = resolve_override("llama3", overrides)
        assert override is not None
        assert override.max_context_window == 16384

    def test_empty_overrides(self):
        """Test with empty override list."""
        override = resolve_override("any-model", [])
        assert override is None


class TestResolveModelCapabilities:
    """Tests for resolve_model_capabilities function."""

    @pytest.mark.asyncio
    async def test_discovered_context_no_override(self):
        """Test using discovered context when no override exists."""
        model_info = {
            "context_window": 131072,
            "family": "llama",
            "parameter_size": "8B",
        }

        caps = await resolve_model_capabilities(
            "llama3:latest",
            model_info,
            [],  # No overrides
            memory_aware=False,
            memory_safety_margin=0.8,
        )

        assert caps.max_context_window == 131072
        assert caps.source == "discovered"
        assert caps.description == "llama3:latest (Llama 8B)"
        assert caps.memory_warning is None

    @pytest.mark.asyncio
    async def test_override_takes_precedence(self):
        """Test that override takes precedence over discovered."""
        model_info = {
            "context_window": 131072,
            "family": "llama",
        }
        overrides = [
            ModelOverride(
                match="llama3:latest",
                max_context_window=65536,
                description="Custom Llama3",
            )
        ]

        caps = await resolve_model_capabilities(
            "llama3:latest",
            model_info,
            overrides,
            memory_aware=False,
            memory_safety_margin=0.8,
        )

        assert caps.max_context_window == 65536
        assert caps.source == "override"
        assert caps.description == "Custom Llama3"

    @pytest.mark.asyncio
    async def test_memory_constraint_applied(self):
        """Test memory-aware context limiting."""
        model_info = {
            "context_window": 131072,
            "parameter_size": "8B",
        }

        # Mock memory calculation to return smaller context
        with patch(
            "mcp_the_force.adapters.ollama.overrides.calculate_viable_context",
            AsyncMock(return_value=32768),
        ) as mock_calc:
            caps = await resolve_model_capabilities(
                "llama3:latest",
                model_info,
                [],
                memory_aware=True,
                memory_safety_margin=0.8,
            )

            assert caps.max_context_window == 32768
            assert caps.source == "memory-limited"
            assert "exceeds memory-safe limit" in caps.memory_warning
            mock_calc.assert_called_once_with(4.0, 0.8)  # 8B params * 0.5 GB/B = 4.0 GB

    @pytest.mark.asyncio
    async def test_default_context_window(self):
        """Test default context window when nothing is discovered."""
        model_info = {}  # No context info

        caps = await resolve_model_capabilities(
            "unknown:model",
            model_info,
            [],
            memory_aware=False,
            memory_safety_margin=0.8,
        )

        assert caps.max_context_window == 16384  # Config default
        assert caps.source == "discovered"
        assert caps.description == "unknown:model"

    @pytest.mark.asyncio
    async def test_parameter_size_parsing(self):
        """Test parsing different parameter size formats."""
        test_cases = [
            ("8B", 4.0),  # 8 * 0.5 (4-bit quantization) = 4.0
            ("120B", 60.0),  # 120 * 0.5 = 60.0
            ("7.5B", 3.75),  # 7.5 * 0.5 = 3.75
            ("13b", 6.5),  # 13 * 0.5 = 6.5 (lowercase)
            ("70.2B", 35.1),  # 70.2 * 0.5 = 35.1
            ("invalid", 3.5),  # Falls back to 7B default * 0.5 = 3.5
            (None, 3.5),  # No parameter size, uses 7B default * 0.5 = 3.5
        ]

        for param_str, expected_gb in test_cases:
            model_info = {"parameter_size": param_str} if param_str else {}

            with patch(
                "mcp_the_force.adapters.ollama.overrides.calculate_viable_context",
                AsyncMock(return_value=16384),
            ) as mock_calc:
                await resolve_model_capabilities(
                    "test:model",
                    model_info,
                    [],
                    memory_aware=True,
                    memory_safety_margin=0.8,
                )

                if param_str and param_str != "invalid":
                    mock_calc.assert_called_once_with(expected_gb, 0.8)

    @pytest.mark.asyncio
    async def test_description_formatting(self):
        """Test description formatting with various model info."""
        # With family and parameter size
        model_info = {
            "family": "llama",
            "parameter_size": "70B",
        }
        caps = await resolve_model_capabilities(
            "llama3:latest", model_info, [], False, 0.8
        )
        assert caps.description == "llama3:latest (Llama 70B)"

        # With family only
        model_info = {"family": "mistral"}
        caps = await resolve_model_capabilities(
            "mistral:7b", model_info, [], False, 0.8
        )
        assert caps.description == "mistral:7b (Mistral)"

        # Model name only
        model_info = {}
        caps = await resolve_model_capabilities(
            "custom:model", model_info, [], False, 0.8
        )
        assert caps.description == "custom:model"

    @pytest.mark.asyncio
    async def test_memory_warning_threshold(self):
        """Test memory warning for large models."""
        model_info = {
            "context_window": 131072,
            "parameter_size": "120B",  # Very large model
        }

        with patch(
            "mcp_the_force.adapters.ollama.overrides.calculate_viable_context",
            AsyncMock(return_value=8192),  # Severely limited
        ):
            caps = await resolve_model_capabilities(
                "gpt-oss:120b",
                model_info,
                [],
                memory_aware=True,
                memory_safety_margin=0.8,
            )

            assert "exceeds memory-safe limit" in caps.memory_warning
            assert "131072" in caps.memory_warning  # Original context
            assert "8192" in caps.memory_warning  # Limited context
