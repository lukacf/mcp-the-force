"""Unit tests for capability formatter."""

from dataclasses import dataclass

from mcp_the_force.utils.capability_formatter import format_capabilities
from mcp_the_force.adapters.capabilities import AdapterCapabilities


class TestCapabilityFormatter:
    """Test capability formatting functionality."""

    def test_basic_capabilities(self):
        """Test formatting basic capabilities."""

        @dataclass
        class TestCapabilities(AdapterCapabilities):
            max_context_window: int = 200_000
            supports_tools: bool = True
            supports_web_search: bool = True
            supports_temperature: bool = True

        capabilities = TestCapabilities()
        result = format_capabilities(capabilities)

        assert "context: 200k tokens" in result
        assert "capabilities: tools, web search, temperature control" in result

    def test_large_context_formatting(self):
        """Test context window formatting for different sizes."""

        @dataclass
        class TestCapabilities(AdapterCapabilities):
            max_context_window: int = 1_000_000

        capabilities = TestCapabilities()
        result = format_capabilities(capabilities)
        assert "context: 1M tokens" in result

        # Test smaller context
        capabilities.max_context_window = 32_768
        result = format_capabilities(capabilities)
        assert "context: 32k tokens" in result

        # Test very small context
        capabilities.max_context_window = 512
        result = format_capabilities(capabilities)
        assert "context: 512 tokens" in result

    def test_all_capabilities(self):
        """Test formatting all possible capabilities."""

        @dataclass
        class TestCapabilities(AdapterCapabilities):
            max_context_window: int = 400_000
            supports_tools: bool = True
            supports_web_search: bool = True
            supports_live_search: bool = True  # Should not show if web_search is True
            supports_reasoning_effort: bool = True
            supports_vision: bool = True
            supports_temperature: bool = True
            supports_structured_output: bool = True
            parallel_function_calls: int = -1  # Unlimited

        capabilities = TestCapabilities()
        result = format_capabilities(capabilities)

        assert "context: 400k tokens" in result
        assert "tools" in result
        assert "web search" in result
        assert "Live Search" not in result  # web_search takes precedence
        assert "reasoning effort" in result
        assert "multimodal (vision)" in result
        assert "temperature control" in result
        assert "structured output" in result
        assert "parallel function calls" in result

    def test_live_search_only(self):
        """Test Live Search shows when web_search is False."""

        @dataclass
        class TestCapabilities(AdapterCapabilities):
            supports_web_search: bool = False
            supports_live_search: bool = True

        capabilities = TestCapabilities()
        result = format_capabilities(capabilities)

        assert "Live Search (X/Twitter)" in result
        assert "web search" not in result

    def test_parallel_function_calls(self):
        """Test different parallel function call configurations."""

        @dataclass
        class TestCapabilities(AdapterCapabilities):
            parallel_function_calls: int = 5

        capabilities = TestCapabilities()
        result = format_capabilities(capabilities)
        assert "parallel function calls (max 5)" in result

        # Test unlimited
        capabilities.parallel_function_calls = -1
        result = format_capabilities(capabilities)
        assert "parallel function calls" in result
        assert "(max" not in result

        # Test None (no parallel calls)
        capabilities.parallel_function_calls = None
        result = format_capabilities(capabilities)
        assert "parallel function calls" not in result

    def test_special_attributes(self):
        """Test special attributes like force_background and max_output_tokens."""

        @dataclass
        class TestCapabilities(AdapterCapabilities):
            force_background: bool = True
            max_output_tokens: int = 32_000

        capabilities = TestCapabilities()
        result = format_capabilities(capabilities)

        assert "runtime: asynchronous" in result
        assert "max output: 32k tokens" in result

    def test_empty_capabilities(self):
        """Test formatting when no special capabilities."""

        @dataclass
        class TestCapabilities(AdapterCapabilities):
            max_context_window: int = None
            supports_tools: bool = False
            supports_web_search: bool = False
            supports_temperature: bool = False
            supports_structured_output: bool = False
            supports_streaming: bool = False
            supports_functions: bool = False

        capabilities = TestCapabilities()
        result = format_capabilities(capabilities)

        # Should return empty string when no capabilities
        assert result == ""

    def test_capability_order(self):
        """Test that capabilities appear in consistent order."""

        @dataclass
        class TestCapabilities(AdapterCapabilities):
            max_context_window: int = 200_000
            supports_tools: bool = True
            supports_structured_output: bool = True
            supports_temperature: bool = True

        capabilities = TestCapabilities()
        result = format_capabilities(capabilities)

        # Context should come first
        assert result.startswith("context: 200k tokens")

        # Capabilities should be in the middle
        assert " | capabilities: " in result

        # Check order within capabilities
        caps_part = result.split("capabilities: ")[1]
        assert caps_part == "tools, temperature control, structured output"

    def test_real_model_examples(self):
        """Test with real model capability patterns."""

        # OpenAI GPT-5 style
        @dataclass
        class GPT5Capabilities(AdapterCapabilities):
            max_context_window: int = 400_000
            supports_tools: bool = True
            supports_web_search: bool = True
            supports_reasoning_effort: bool = True
            supports_temperature: bool = False  # GPT-5 doesn't support temperature
            supports_structured_output: bool = True
            parallel_function_calls: int = -1

        result = format_capabilities(GPT5Capabilities())
        assert (
            result
            == "context: 400k tokens | capabilities: tools, web search, reasoning effort, structured output, parallel function calls"
        )

        # Gemini style
        @dataclass
        class GeminiCapabilities(AdapterCapabilities):
            max_context_window: int = 1_000_000
            supports_tools: bool = True
            supports_vision: bool = True
            supports_reasoning_effort: bool = True
            supports_temperature: bool = True
            supports_structured_output: bool = True

        result = format_capabilities(GeminiCapabilities())
        assert "context: 1M tokens" in result
        assert "multimodal (vision)" in result

        # Anthropic style
        @dataclass
        class AnthropicCapabilities(AdapterCapabilities):
            max_context_window: int = 200_000
            max_output_tokens: int = 32_000
            supports_tools: bool = True
            supports_vision: bool = True
            supports_temperature: bool = True
            supports_structured_output: bool = True

        result = format_capabilities(AnthropicCapabilities())
        assert "context: 200k tokens" in result
        assert "max output: 32k tokens" in result

        # Research model style
        @dataclass
        class ResearchCapabilities(AdapterCapabilities):
            max_context_window: int = 200_000
            supports_web_search: bool = True
            force_background: bool = True
            supports_tools: bool = False  # Research models don't support custom tools

        result = format_capabilities(ResearchCapabilities())
        assert "context: 200k tokens" in result
        assert "web search" in result
        assert "runtime: asynchronous" in result
        assert "tools" not in result

    def test_integration_with_description(self):
        """Test how formatted capabilities integrate with descriptions."""

        @dataclass
        class TestCapabilities(AdapterCapabilities):
            max_context_window: int = 200_000
            supports_tools: bool = True
            supports_temperature: bool = False  # Override default
            supports_structured_output: bool = False  # Override default
            description: str = "Test model for unit testing"

        capabilities = TestCapabilities()
        capability_info = format_capabilities(capabilities)

        # Simulate what happens in blueprint generation
        full_description = capabilities.description
        if capability_info:
            full_description = f"{capabilities.description} [{capability_info}]"

        assert (
            full_description
            == "Test model for unit testing [context: 200k tokens | capabilities: tools]"
        )
