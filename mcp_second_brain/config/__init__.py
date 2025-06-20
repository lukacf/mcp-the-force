"""Configuration module for MCP Second-Brain."""
from .model_loader import ModelConfig, load_models, get_model_by_alias

__all__ = ["ModelConfig", "load_models", "get_model_by_alias"]