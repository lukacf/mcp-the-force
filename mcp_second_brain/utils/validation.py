"""JSON schema validation utilities."""

import logging
from typing import Dict, Any
from jsonschema import validate

logger = logging.getLogger(__name__)


def validate_json_schema(json_data: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """
    Validates a JSON object against a given JSON schema.

    Args:
        json_data: The JSON object to validate.
        schema: The JSON schema to validate against.

    Raises:
        jsonschema.ValidationError: If the JSON data does not conform to the schema.
    """
    validate(instance=json_data, schema=schema)
    logger.debug("JSON data validated successfully against schema.")
