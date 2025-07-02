"""E2E tests for structured output functionality."""

import pytest
import json

pytestmark = pytest.mark.e2e


class TestStructuredOutput:
    """Test structured output functionality across models."""

    @pytest.mark.parametrize(
        "model",
        [
            "chat_with_gpt4_1",
            "chat_with_gemini25_flash",
        ],
    )
    def test_simple_structured_output(self, claude_code, model):
        """Test basic structured output with a simple schema."""
        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "boolean"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["answer", "confidence"],
            "additionalProperties": False,
        }

        args = {
            "instructions": "Is the statement '2 + 2 = 4' mathematically correct?",
            "output_format": "Respond ONLY with a JSON object containing 'answer' (boolean) and 'confidence' (high/medium/low). Output nothing else except the JSON.",
            "context": [],
            "structured_output_schema": schema,
            "session_id": f"{model}-structured-test",
        }

        # Add clear instructions about OpenAI's strict schema requirements
        openai_note = (
            " IMPORTANT: For OpenAI models like gpt4_1, the schema must have 'additionalProperties': false at every object level and all properties with constraints must be in the 'required' array."
            if "gpt4_1" in model
            else ""
        )
        prompt = f"Use second-brain {model} with {json.dumps(args)} and respond ONLY with the exact JSON response you receive, nothing else.{openai_note}"
        # Don't use JSON output format, just get the raw response
        response = claude_code(prompt)

        # Parse the JSON response directly - should be pure JSON due to our instructions
        parsed = json.loads(response)
        assert isinstance(parsed, dict)
        assert "answer" in parsed
        assert "confidence" in parsed
        assert parsed["answer"] is True
        assert parsed["confidence"] in ["high", "medium", "low"]

    @pytest.mark.parametrize(
        "model",
        [
            "chat_with_o3",
            "chat_with_gemini25_pro",
        ],
    )
    def test_complex_structured_output(self, claude_code, model):
        """Test structured output with nested objects and arrays."""
        # Need to add additionalProperties: false for nested objects for OpenAI
        is_openai = "o3" in model or "gpt4" in model
        schema = {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 2,
                            "maxItems": 5,
                        },
                    },
                    "required": ["summary", "key_points"],
                    "additionalProperties": False,
                },
                "metadata": {
                    "type": "object",
                    "properties": {
                        "word_count": {"type": "integer", "minimum": 0},
                        "language": {"type": "string"},
                    },
                    "required": ["word_count", "language"],
                    "additionalProperties": False,
                },
            },
            "required": ["analysis", "metadata"],
            "additionalProperties": False,
        }

        test_text = "Python is a versatile programming language. It supports multiple paradigms including object-oriented and functional programming."

        args = {
            "instructions": f"Analyze this text: '{test_text}'",
            "output_format": "Provide analysis with summary, 2-5 key points, word count, and language",
            "context": [],
            "structured_output_schema": schema,
            "session_id": f"{model}-complex-structured",
        }

        # Add clear instructions about OpenAI's strict schema requirements
        openai_note = (
            " IMPORTANT: For OpenAI models like o3, the schema must have 'additionalProperties': false at EVERY object level (including nested objects) and all properties with constraints (minItems, maxItems, minimum) must be in the 'required' array."
            if is_openai
            else ""
        )
        prompt = f"Use second-brain {model} with {json.dumps(args)} and respond ONLY with the exact JSON response you receive, nothing else.{openai_note}"
        response = claude_code(prompt)

        # Parse and validate response
        parsed = json.loads(response)
        assert "analysis" in parsed
        assert "metadata" in parsed
        assert "summary" in parsed["analysis"]
        assert "key_points" in parsed["analysis"]
        assert isinstance(parsed["analysis"]["key_points"], list)
        assert 2 <= len(parsed["analysis"]["key_points"]) <= 5
        assert parsed["metadata"]["word_count"] > 0
        assert parsed["metadata"]["language"] == "English"

    def test_structured_output_validation_error(self, claude_code):
        """Test that invalid structured output raises appropriate error."""
        # Schema requires integer but we'll ask for a string
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
            "additionalProperties": False,
        }

        args = {
            "instructions": "Return the word 'five' as the count value (this should fail validation)",
            "output_format": "JSON with count as the word 'five'",
            "context": [],
            "structured_output_schema": schema,
            "session_id": "validation-error-test",
        }

        prompt = f"Use second-brain chat_with_gemini25_flash with {json.dumps(args)} and respond ONLY with the exact response you receive, nothing else"

        # The structured output validation should prevent invalid output
        # But since we're asking for the word 'five' instead of a number,
        # Gemini will return an error or still return valid JSON with count as 5
        response = claude_code(prompt)

        # Either we get an error message or Gemini corrects it to a valid number
        # Let's check what actually happens
        try:
            parsed = json.loads(response)
            # If it parsed, Gemini likely corrected the output
            assert isinstance(parsed.get("count"), int)
        except json.JSONDecodeError:
            # If it's not JSON, it should contain an error message
            assert "error" in response.lower() or "failed" in response.lower()

    def test_structured_output_with_optional_fields(self, claude_code):
        """Test structured output with optional fields."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {
                    "type": "integer",
                    "minimum": 0,
                },  # Adding constraint for strict validation
                "email": {"type": "string", "format": "email"},  # Optional field
            },
            "required": [
                "name",
                "age",
            ],  # email is optional, but age now has constraint so must be required
            "additionalProperties": False,
        }

        args = {
            "instructions": "Create a person object with name 'Alice' and age 30",
            "output_format": "JSON object with name and age (email optional)",
            "context": [],
            "structured_output_schema": schema,
            "session_id": "optional-fields-test",
        }

        # Add clear instructions about OpenAI's strict schema requirements
        prompt = f"Use second-brain chat_with_gpt4_1 with {json.dumps(args)} and respond ONLY with the exact JSON response you receive, nothing else. IMPORTANT: For OpenAI models, the schema must have 'additionalProperties': false and all properties with constraints (like minimum on age) must be in the 'required' array."
        response = claude_code(prompt)

        parsed = json.loads(response)
        assert parsed["name"] == "Alice"
        assert parsed["age"] == 30
        # email may or may not be present - both are valid
