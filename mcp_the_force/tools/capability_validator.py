"""Capability validation for tool parameters."""

import logging
from typing import Any, Dict, Optional
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

            # Execute the capability check lambda
            try:
                if not param_info.requires_capability(capabilities):
                    # Find which capability attribute returned False
                    # This is a bit of introspection to provide better error messages
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
        self, capability_check: Any, capabilities: AdapterCapabilities
    ) -> str:
        """Try to infer the capability name from the lambda.

        This is a best-effort approach to provide meaningful error messages.
        """
        # Try to extract the attribute name from the lambda
        # This works for simple lambdas like: lambda c: c.supports_temperature
        try:
            import dis
            import io
            from contextlib import redirect_stdout

            # Capture disassembly output
            output = io.StringIO()
            with redirect_stdout(output):
                dis.dis(capability_check)

            disasm = output.getvalue()

            # Look for LOAD_ATTR instructions which indicate attribute access
            for line in disasm.split("\n"):
                if "LOAD_ATTR" in line:
                    # Extract the attribute name (it's usually in parentheses)
                    parts = line.split("(")
                    if len(parts) > 1:
                        attr_name = parts[1].split(")")[0]
                        # Verify this attribute exists and is False
                        if hasattr(capabilities, attr_name):
                            if getattr(capabilities, attr_name) is False:
                                return attr_name

            # Fallback: check all False boolean attributes
            for attr_name in dir(capabilities):
                if not attr_name.startswith("_"):
                    value = getattr(capabilities, attr_name)
                    if isinstance(value, bool) and value is False:
                        # Try executing the lambda to see if this is the one
                        try:
                            # Create a test object with this attribute True
                            test_caps = type(capabilities)()
                            for a in dir(capabilities):
                                if not a.startswith("_"):
                                    setattr(test_caps, a, getattr(capabilities, a))
                            setattr(test_caps, attr_name, True)

                            # If the lambda returns True with this change,
                            # this is likely the capability
                            if capability_check(test_caps):
                                return attr_name
                        except Exception:
                            pass

        except Exception as e:
            logger.debug(f"Could not infer capability name: {e}")

        return "required capability"
