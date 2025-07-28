"""Parameter validation for tools."""

import os
import logging
from typing import Dict, Any, Union, Optional, get_origin, get_args
from .registry import ToolMetadata
from .base import ToolSpec

logger = logging.getLogger(__name__)


class ParameterValidator:
    """Handles parameter validation for tools."""

    def __init__(self, strict_mode: bool = False):
        """Initialize validator.

        Args:
            strict_mode: If True, raise errors for unknown parameters.
                        If False (default), log warnings only.
        """
        self.strict_mode = strict_mode

    def validate(
        self, tool_instance: ToolSpec, metadata: ToolMetadata, kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate parameters and set them on the tool instance.

        Args:
            tool_instance: Instance of the tool
            metadata: Tool metadata containing parameter info
            kwargs: User-provided arguments

        Returns:
            Dict of validated parameters

        Raises:
            ValueError: If required parameter missing or unknown parameter in strict mode
        """
        # Debug logging for E2E tests
        if os.getenv("CI_E2E") == "1":
            logger.info(f"Validating parameters for {tool_instance.__class__.__name__}")
            logger.info(f"Received kwargs: {kwargs}")
            logger.info(
                f"Kwargs types: {[(k, type(v).__name__) for k, v in kwargs.items()]}"
            )

        validated = {}

        # Check required parameters
        for name, param_info in metadata.parameters.items():
            if param_info.required and name not in kwargs:
                raise ValueError(f"Missing required parameter: {name}")

            # Get value or use default
            if name in kwargs:
                value = kwargs[name]
            else:
                # Check if this parameter has capability requirements before applying default
                if (
                    hasattr(param_info, "requires_capability")
                    and param_info.requires_capability
                ):
                    # If metadata has capabilities, check them
                    if hasattr(metadata, "capabilities") and metadata.capabilities:
                        try:
                            if not param_info.requires_capability(
                                metadata.capabilities
                            ):
                                # Skip this parameter - not supported by model
                                logger.debug(
                                    f"Skipping default for parameter {name} - not supported by model"
                                )
                                continue
                        except Exception as e:
                            # If capability check fails, skip the parameter
                            logger.debug(
                                f"Capability check failed for {name}: {e}, skipping default"
                            )
                            continue

                value = param_info.default

            # Check that required parameters are not None
            if param_info.required and value is None:
                raise ValueError(f"Required parameter '{name}' cannot be None")

            # Type validation and coercion for non-None values
            if (
                value is not None
                and hasattr(param_info, "type")
                and param_info.type is not Any
            ):
                # Try to coerce the value if needed
                coerced_value = self._coerce_type(value, param_info.type)
                if coerced_value is not None:
                    value = coerced_value
                elif not self._validate_type(value, param_info.type):
                    expected = getattr(param_info, "type_str", str(param_info.type))
                    actual = type(value).__name__

                    # Provide more helpful error message for list parameters
                    if get_origin(param_info.type) is list and isinstance(value, str):
                        raise TypeError(
                            f"Parameter '{name}' expected {expected}, got {actual}. "
                            f"List parameters must be provided as JSON arrays, not strings. "
                            f"Example: {name}=['item1', 'item2'] or {name}='[\"item1\", \"item2\"]'"
                        )
                    else:
                        raise TypeError(
                            f"Parameter '{name}' expected {expected}, got {actual}"
                        )

            # Set on instance (descriptor will handle storage)
            setattr(tool_instance, name, value)
            validated[name] = value

        # Check for unknown parameters
        known_params = set(metadata.parameters.keys())
        unknown = set(kwargs.keys()) - known_params
        if unknown:
            if self.strict_mode:
                raise ValueError(f"Unknown parameters: {unknown}")
            else:
                logger.warning(f"Unknown parameters will be ignored: {unknown}")

        return validated

    def _validate_type(self, value: Any, expected_type: type) -> bool:
        """Validate that a value matches the expected type.

        Handles:
        - Basic types (str, int, float, bool)
        - Generic types (List[str], Optional[int], etc.)
        - Union types
        - Literal types
        """
        # Get origin for generic types
        origin = get_origin(expected_type)

        # Handle None type
        if expected_type is type(None):
            return value is None

        # Handle Union types (including Optional)
        if origin is Union:
            args = get_args(expected_type)
            return any(self._validate_type(value, arg) for arg in args)

        # Handle List types
        if origin is list:
            if not isinstance(value, list):
                return False
            # If parameterized, check element types
            args = get_args(expected_type)
            if args:
                element_type = args[0]
                return all(self._validate_type(elem, element_type) for elem in value)
            return True

        # Handle Dict types
        if origin is dict:
            if not isinstance(value, dict):
                return False
            # Could add key/value type checking here if needed
            return True

        # Handle Literal types
        if (
            hasattr(expected_type, "__origin__")
            and expected_type.__origin__.__name__ == "Literal"
        ):
            return value in get_args(expected_type)

        # Handle basic types
        if origin is None:
            return isinstance(value, expected_type)

        # For other generic types, just check the origin
        return isinstance(value, origin)

    def _coerce_type(self, value: Any, expected_type: type) -> Optional[Any]:
        """Try to coerce a value to the expected type.

        Returns the coerced value if successful, None otherwise.
        Handles common cases like string to bool conversion.
        """
        # Get origin for generic types
        origin = get_origin(expected_type)

        # Handle Union types (including Optional)
        if origin is Union:
            args = get_args(expected_type)
            # Try each type in the union
            for arg in args:
                if arg is type(None) and value is None:
                    return None
                coerced = self._coerce_type(value, arg)
                if coerced is not None:
                    return coerced
            return None

        # Handle List types
        if origin is list or expected_type is list:
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                # Try to parse JSON string
                try:
                    import json

                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
            return None

        # Handle Dict types
        if origin is dict or expected_type is dict:
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                # Try to parse JSON string
                try:
                    import json

                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
            return None

        # Handle basic bool coercion
        if expected_type is bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                # Handle string to bool conversion
                lower_val = value.lower()
                if lower_val in ("true", "1", "yes", "on"):
                    return True
                elif lower_val in ("false", "0", "no", "off"):
                    return False
            if isinstance(value, (int, float)):
                # Handle numeric to bool conversion
                return bool(value)

        # Handle float coercion
        if expected_type is float:
            if isinstance(value, float):
                return value
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    pass
            if isinstance(value, int):
                return float(value)

        # No coercion performed
        return None
