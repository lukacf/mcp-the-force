"""Capability validation for tool parameters."""

import logging
from typing import Any, Callable, Dict, Optional
from ..adapters.capabilities import AdapterCapabilities
from .registry import ToolMetadata

logger = logging.getLogger(__name__)


class CapabilityValidator:
    """Validates tool parameters against model capabilities."""

    def validate_against_capabilities(
        self,
        metadata: ToolMetadata,
        kwargs: Dict[str, Any],
        capabilities: Optional[AdapterCapabilities],
    ) -> None:
        """Validate parameters against model capabilities.

        Args:
            metadata: Tool metadata containing parameter definitions
            kwargs: Actual parameter values passed to the tool
            capabilities: Model capabilities (None for local tools)

        Raises:
            ValueError: If a parameter requires a capability the model doesn't have
        """
        # Skip capability checks for local tools
        if capabilities is None:
            logger.debug("Skipping capability validation for local tool")
            return

        # Check each parameter that has a capability requirement
        for param_name, param_info in metadata.parameters.items():
            if param_info.requires_capability is None:
                continue

            # Skip if parameter wasn't provided (will use default)
            if param_name not in kwargs:
                continue

            param_value = kwargs[param_name]

            # Skip if value is None - universally means "no value provided"
            # This handles cases where default_factory=list but user passes None
            if param_value is None:
                logger.debug(
                    f"Skipping capability check for {param_name} - value is None"
                )
                continue

            # Skip if parameter value equals the parameter's default value.
            # This correctly handles all cases:
            # - default=None, default_factory=list, value=[] → skip ([] == [])
            # - default=None, default_factory=None, value=[] → validate ([] != None)
            # - default=0.5, default_factory=None, value=0.5 → skip
            param_default = param_info.get_default_value()
            if param_value == param_default:
                logger.debug(
                    f"Skipping capability check for {param_name} - value equals default {param_default!r}"
                )
                continue

            # Execute the capability check lambda
            try:
                if not param_info.requires_capability(capabilities):
                    # Find which capability attribute returned False
                    capability_name = self._infer_capability_name(
                        param_info.requires_capability, capabilities
                    )

                    model_name = getattr(capabilities, "model_name", "unknown")

                    raise ValueError(
                        f"Parameter '{param_name}' is not supported by model '{model_name}' "
                        f"because its '{capability_name}' is False"
                    )
            except Exception as e:
                if isinstance(e, ValueError):
                    raise
                logger.error(f"Error checking capability for {param_name}: {e}")
                raise ValueError(
                    f"Failed to validate capability for parameter '{param_name}': {str(e)}"
                )

    def _infer_capability_name(
        self, capability_check: Callable[[Any], bool], capabilities: AdapterCapabilities
    ) -> str:
        """Infer the capability name from the lambda.

        Uses code object inspection to extract attribute names accessed by the lambda.
        This is more reliable than bytecode disassembly as it uses stable Python APIs.

        Args:
            capability_check: Lambda like `lambda c: c.supports_vision`
            capabilities: The capabilities object to check against

        Returns:
            The capability name, or "required capability" if unable to determine
        """
        try:
            # Method 1: Extract attribute names from lambda's code object
            # For `lambda c: c.supports_vision`, co_names contains ('supports_vision',)
            code = getattr(capability_check, "__code__", None)
            if code is not None:
                names: tuple[str, ...] = code.co_names
                # Check each name to see if it's a False capability
                for attr_name in names:
                    if hasattr(capabilities, attr_name):
                        value = getattr(capabilities, attr_name)
                        if value is False:
                            return attr_name

            # Method 2: Check all False boolean capabilities
            # This handles complex lambdas that access multiple attributes
            false_capabilities = []
            for attr_name in dir(capabilities):
                if attr_name.startswith("_"):
                    continue
                try:
                    value = getattr(capabilities, attr_name)
                    if isinstance(value, bool) and value is False:
                        false_capabilities.append(attr_name)
                except Exception:
                    continue

            # If there's only one False capability, it's likely the one
            if len(false_capabilities) == 1:
                return false_capabilities[0]

            # If multiple False capabilities, return a descriptive list
            if false_capabilities:
                return " or ".join(false_capabilities)

        except Exception as e:
            logger.debug(f"Could not infer capability name: {e}")

        return "required capability"
