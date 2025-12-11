"""Core data types for multi-model collaboration."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Literal, Optional


@dataclass
class DeliverableContract:
    """Simple contract specifying what the group should deliver (assumption-free)."""

    objective: str
    output_format: str

    # Legacy fields kept for compatibility but not used in prompts
    deliverable_type: str = "user_specified"
    success_criteria: List = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "objective": self.objective,
            "output_format": self.output_format,
            "deliverable_type": self.deliverable_type,
            "success_criteria": self.success_criteria,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeliverableContract":
        """Create from dictionary."""
        return cls(
            objective=data["objective"],
            output_format=data["output_format"],
            deliverable_type=data.get("deliverable_type", "user_specified"),
            success_criteria=data.get("success_criteria", []),
        )


@dataclass
class CollaborationMessage:
    """A message in a multi-model collaboration."""

    speaker: str  # "user" | model_name (e.g., "chat_with_gpt5_pro")
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary for serialization."""
        return {
            "speaker": self.speaker,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CollaborationMessage:
        """Create message from dictionary."""
        return cls(
            speaker=data["speaker"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CollaborationSession:
    """State for a multi-model collaboration session."""

    session_id: str
    objective: str
    models: List[str]  # List of model tool names
    messages: List[CollaborationMessage]
    current_step: int
    mode: Literal["round_robin", "orchestrator"]
    max_steps: int
    status: Literal["active", "completed", "failed"]

    def add_message(self, message: CollaborationMessage) -> None:
        """Add a message to the collaboration."""
        self.messages.append(message)

    def advance_step(self) -> None:
        """Advance to the next collaboration step."""
        self.current_step += 1
        if self.current_step >= self.max_steps:
            self.status = "completed"

    def get_next_model(self) -> str:
        """Get the next model in the sequence based on mode."""
        if self.mode == "round_robin":
            return self.models[self.current_step % len(self.models)]
        else:
            # For orchestrator mode, this would be determined by the orchestrator
            # For now, return the first model as default
            return self.models[0] if self.models else ""

    def is_completed(self) -> bool:
        """Check if the collaboration is completed."""
        return self.current_step >= self.max_steps or self.status in [
            "completed",
            "failed",
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "objective": self.objective,
            "models": self.models,
            "messages": [msg.to_dict() for msg in self.messages],
            "current_step": self.current_step,
            "mode": self.mode,
            "max_steps": self.max_steps,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CollaborationSession:
        """Create session from dictionary."""
        messages = [
            CollaborationMessage.from_dict(msg_data)
            for msg_data in data.get("messages", [])
        ]

        return cls(
            session_id=data["session_id"],
            objective=data["objective"],
            models=data["models"],
            messages=messages,
            current_step=data["current_step"],
            mode=data["mode"],
            max_steps=data["max_steps"],
            status=data["status"],
        )


@dataclass
class CollaborationConfig:
    """Configuration for multi-model collaborations."""

    max_steps: int = 10
    parallel_limit: int = 1  # Number of models to run in parallel
    timeout_per_step: int = 600  # Seconds per step (10 min for heavyweight models)
    summarization_threshold: int = 50  # Messages before summarization
    cost_limit_usd: Optional[float] = None

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if self.parallel_limit <= 0:
            raise ValueError("parallel_limit must be positive")
        if self.timeout_per_step <= 0:
            raise ValueError("timeout_per_step must be positive")
        if self.summarization_threshold <= 0:
            raise ValueError("summarization_threshold must be positive")

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for serialization."""
        return {
            "max_steps": self.max_steps,
            "parallel_limit": self.parallel_limit,
            "timeout_per_step": self.timeout_per_step,
            "summarization_threshold": self.summarization_threshold,
            "cost_limit_usd": self.cost_limit_usd,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CollaborationConfig:
        """Create config from dictionary."""
        return cls(
            max_steps=data.get("max_steps", 10),
            parallel_limit=data.get("parallel_limit", 1),
            timeout_per_step=data.get("timeout_per_step", 600),
            summarization_threshold=data.get("summarization_threshold", 50),
            cost_limit_usd=data.get("cost_limit_usd"),
        )
