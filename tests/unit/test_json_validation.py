"""Unit tests for JSON schema validation logic."""

import pytest
from jsonschema import ValidationError

# This will be the validation function we'll implement
from mcp_second_brain.utils.validation import validate_json_schema


class TestJSONValidation:
    """Test JSON schema validation functionality."""

    def test_validate_simple_object(self):
        """Test validation of a simple object schema."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }

        valid_data = {"name": "Alice", "age": 30}

        # Should not raise
        validate_json_schema(valid_data, schema)

    def test_validate_nested_object(self):
        """Test validation of nested object schemas."""
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "profile": {
                            "type": "object",
                            "properties": {
                                "email": {"type": "string", "format": "email"}
                            },
                            "required": ["email"],
                        },
                    },
                    "required": ["id", "profile"],
                }
            },
            "required": ["user"],
        }

        valid_data = {"user": {"id": "123", "profile": {"email": "alice@example.com"}}}

        # Should not raise
        validate_json_schema(valid_data, schema)

    def test_validate_array_schema(self):
        """Test validation of array schemas."""
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "value": {"type": "string"}},
                "required": ["id", "value"],
            },
            "minItems": 1,
        }

        valid_data = [{"id": 1, "value": "first"}, {"id": 2, "value": "second"}]

        # Should not raise
        validate_json_schema(valid_data, schema)

    def test_validation_fails_wrong_type(self):
        """Test that validation fails for wrong types."""
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }

        invalid_data = {"count": "not-a-number"}

        with pytest.raises(
            ValidationError, match="'not-a-number' is not of type 'integer'"
        ):
            validate_json_schema(invalid_data, schema)

    def test_validation_fails_missing_required(self):
        """Test that validation fails for missing required fields."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "email": {"type": "string"}},
            "required": ["name", "email"],
        }

        invalid_data = {"name": "Alice"}  # Missing email

        with pytest.raises(ValidationError, match="'email' is a required property"):
            validate_json_schema(invalid_data, schema)

    def test_validation_fails_additional_properties(self):
        """Test that validation fails for additional properties when not allowed."""
        schema = {
            "type": "object",
            "properties": {"allowed": {"type": "string"}},
            "additionalProperties": False,
        }

        invalid_data = {"allowed": "yes", "notAllowed": "no"}

        with pytest.raises(
            ValidationError, match="Additional properties are not allowed"
        ):
            validate_json_schema(invalid_data, schema)

    def test_validation_with_enum(self):
        """Test validation with enum constraints."""
        schema = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "approved", "rejected"],
                }
            },
            "required": ["status"],
        }

        valid_data = {"status": "approved"}
        validate_json_schema(valid_data, schema)  # Should not raise

        invalid_data = {"status": "unknown"}
        with pytest.raises(ValidationError, match="'unknown' is not one of"):
            validate_json_schema(invalid_data, schema)

    def test_validation_with_pattern(self):
        """Test validation with string pattern constraints."""
        schema = {
            "type": "object",
            "properties": {
                "code": {"type": "string", "pattern": "^[A-Z]{3}-[0-9]{3}$"}
            },
            "required": ["code"],
        }

        valid_data = {"code": "ABC-123"}
        validate_json_schema(valid_data, schema)  # Should not raise

        invalid_data = {"code": "abc-123"}  # Lowercase letters
        with pytest.raises(ValidationError, match="does not match"):
            validate_json_schema(invalid_data, schema)

    def test_empty_schema_allows_any_json(self):
        """Test that empty schema allows any valid JSON."""
        schema = {}

        # All of these should be valid
        validate_json_schema({"any": "object"}, schema)
        validate_json_schema([1, 2, 3], schema)
        validate_json_schema("string", schema)
        validate_json_schema(123, schema)
        validate_json_schema(True, schema)
        validate_json_schema(None, schema)

    def test_validation_with_numbers(self):
        """Test validation with number constraints."""
        schema = {
            "type": "object",
            "properties": {
                "temperature": {"type": "number", "minimum": -273.15, "maximum": 1000},
                "count": {"type": "integer", "minimum": 0, "exclusiveMaximum": 100},
            },
            "required": ["temperature", "count"],
        }

        valid_data = {"temperature": 22.5, "count": 50}
        validate_json_schema(valid_data, schema)  # Should not raise

        # Test temperature too low
        with pytest.raises(ValidationError, match="-300 is less than the minimum"):
            validate_json_schema({"temperature": -300, "count": 50}, schema)

        # Test count at exclusive maximum
        with pytest.raises(
            ValidationError, match="100 is greater than or equal to the maximum"
        ):
            validate_json_schema({"temperature": 22.5, "count": 100}, schema)
