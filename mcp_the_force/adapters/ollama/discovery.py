"""Ollama model discovery with context detection."""

import re
import logging
from typing import Dict, Any, List, Optional

import httpx
from ...config import get_settings

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)


async def list_models(host: str) -> List[Dict[str, Any]]:
    """
    List available models from Ollama API.

    Returns list of models with basic info from /api/tags endpoint.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{host}/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
    except Exception as e:
        logger.warning(f"Failed to list Ollama models from {host}: {e}")
        return []


async def discover_model_details(host: str, model_name: str) -> Dict[str, Any]:
    """
    Get detailed model info including actual context window.

    Uses /api/show endpoint to get model metadata including context length.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{host}/api/show", json={"name": model_name})
            response.raise_for_status()
            data = response.json()

            # Extract context window from model_info
            model_info = data.get("model_info", {})
            context_window = None

            # Look for family.context_length pattern (e.g., "llama.context_length")
            for key, value in model_info.items():
                if key.endswith(".context_length"):
                    context_window = int(value)
                    break

            # Fallback to parsing parameters string
            if not context_window:
                params = data.get("parameters", "")
                match = re.search(r"num_ctx\s+(\d+)", params)
                if match:
                    context_window = int(match.group(1))

            settings = get_settings()
            return {
                "name": model_name,
                "context_window": context_window
                or settings.ollama.default_context_window,
                "model_info": model_info,
                "quantization": data.get("details", {}).get(
                    "quantization_level", "unknown"
                ),
                "parameter_size": data.get("details", {}).get(
                    "parameter_size", "unknown"
                ),
            }
    except Exception as e:
        logger.warning(f"Failed to get details for {model_name}: {e}")
        settings = get_settings()
        return {
            "name": model_name,
            "context_window": settings.ollama.default_context_window,
            "model_info": {},
            "quantization": "unknown",
            "parameter_size": "unknown",
        }


def estimate_model_memory_gb(model_name: str, parameter_size: str) -> float:
    """
    Estimate model memory usage based on parameter size and quantization.

    This is a rough estimate - actual usage varies.
    """
    # Try to extract parameter count from name or size string
    param_match = re.search(r"(\d+(?:\.\d+)?)[bB]", parameter_size)
    if not param_match:
        # Try model name
        param_match = re.search(r"(\d+)[bB]", model_name)

    if param_match:
        param_billions = float(param_match.group(1))
    else:
        # Default estimate based on common model sizes
        if "7b" in model_name.lower():
            param_billions = 7
        elif "13b" in model_name.lower():
            param_billions = 13
        elif "20b" in model_name.lower():
            param_billions = 20
        elif "70b" in model_name.lower():
            param_billions = 70
        elif "120b" in model_name.lower():
            param_billions = 120
        else:
            param_billions = 7  # Conservative default

    # Rough memory estimate based on quantization
    # 4-bit quantization ~ 0.5GB per billion parameters
    # 8-bit quantization ~ 1GB per billion parameters
    # 16-bit ~ 2GB per billion parameters
    if "q4" in model_name.lower() or "4bit" in model_name.lower():
        gb_per_billion = 0.5
    elif "q8" in model_name.lower() or "8bit" in model_name.lower():
        gb_per_billion = 1.0
    else:
        # Default to 4-bit for most Ollama models
        gb_per_billion = 0.5

    return param_billions * gb_per_billion


async def calculate_viable_context(
    model_memory_gb: float, safety_margin: float = 0.8
) -> int:
    """
    Calculate maximum viable context based on system memory.

    Args:
        model_memory_gb: Estimated model memory usage in GB
        safety_margin: Fraction of available memory to use (0.0-1.0)

    Returns:
        Maximum viable context size in tokens
    """
    if not PSUTIL_AVAILABLE:
        # Default to conservative context when psutil not available
        logger.warning("psutil not available, using conservative context size")
        return 8192

    mem = psutil.virtual_memory()
    available_gb = mem.available / (1024**3)

    # Reserve memory for OS and other applications
    reserved_gb = 20  # Conservative reservation

    # Available for KV cache after model and reservations
    available_for_kv = (available_gb - reserved_gb) * safety_margin

    # Estimate: ~0.5-0.6 GB per 1K context for large models
    # This is a rough approximation that varies by model architecture
    gb_per_1k_context = 0.55
    max_context = int((available_for_kv / gb_per_1k_context) * 1000)

    # Round down to standard sizes for better performance
    standard_sizes = [4096, 8192, 16384, 32768, 65536, 131072]
    for size in reversed(standard_sizes):
        if size <= max_context:
            return size

    return 4096  # Minimum fallback


async def get_running_context(host: str) -> Optional[int]:
    """
    Check if an Ollama runner is currently active and get its context size.

    Returns the context size if a runner is active, None otherwise.
    """
    if not PSUTIL_AVAILABLE:
        return None

    try:
        # Check for running ollama processes
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if "ollama" in proc.info["name"] and proc.info["cmdline"]:
                    cmdline = " ".join(proc.info["cmdline"])
                    if "runner" in cmdline and "--ctx-size" in cmdline:
                        match = re.search(r"--ctx-size\s+(\d+)", cmdline)
                        if match:
                            return int(match.group(1))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.debug(f"Failed to check running Ollama context: {e}")

    return None
