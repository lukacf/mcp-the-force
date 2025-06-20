"""Model configuration loader for dynamic tool generation."""
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

class ModelConfig(BaseModel):
    """Configuration for a single model."""
    id: str
    aliases: list[str] = Field(default_factory=list)
    provider: str
    adapter: str
    model_name: str
    description: str
    context_window: int
    default_timeout: int
    supports_session: bool = False
    supports_vector_store: bool = False
    default_params: Dict[str, Any] = Field(default_factory=dict)

def load_models(config_path: Optional[str | Path] = None) -> Dict[str, ModelConfig]:
    """Load model configurations from YAML file.
    
    Args:
        config_path: Path to models.yaml. If None, uses default location.
        
    Returns:
        Dictionary mapping model ID to ModelConfig
    """
    if config_path is None:
        config_path = Path(__file__).parent / "models.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Model config not found: {config_path}")
    
    try:
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
        
        models = {}
        for model_data in data.get("models", []):
            config = ModelConfig(**model_data)
            models[config.id] = config
            logger.info(f"Loaded model config: {config.id}")
        
        return models
    except Exception as e:
        logger.error(f"Failed to load model config: {e}")
        raise

def get_model_by_alias(models: Dict[str, ModelConfig], alias: str) -> Optional[ModelConfig]:
    """Find a model by its alias.
    
    Args:
        models: Dictionary of loaded models
        alias: Alias to search for
        
    Returns:
        ModelConfig if found, None otherwise
    """
    # First check if it's a primary ID
    if alias in models:
        return models[alias]
    
    # Then check aliases
    for model in models.values():
        if alias in model.aliases:
            return model
    
    return None