"""Tests for core collaboration data types."""

import pytest
from datetime import datetime

from mcp_the_force.types.collaboration import (
    CollaborationMessage,
    CollaborationSession,
    CollaborationConfig,
)


class TestCollaborationMessage:
    """Test CollaborationMessage dataclass."""

    def test_message_creation(self):
        """Test basic message creation."""
        msg = CollaborationMessage(
            speaker="user", content="Hello world", timestamp=datetime.now()
        )

        assert msg.speaker == "user"
        assert msg.content == "Hello world"
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}  # Default empty dict

    def test_message_with_metadata(self):
        """Test message with custom metadata."""
        metadata = {"model": "gpt-5", "turn": 1}
        msg = CollaborationMessage(
            speaker="chat_with_gpt5",
            content="AI response",
            timestamp=datetime.now(),
            metadata=metadata,
        )

        assert msg.metadata == metadata
        assert msg.metadata["model"] == "gpt-5"

    def test_message_serialization(self):
        """Test message can be converted to/from dict."""
        timestamp = datetime.now()
        msg = CollaborationMessage(
            speaker="user",
            content="test",
            timestamp=timestamp,
            metadata={"key": "value"},
        )

        # Convert to dict
        msg_dict = msg.to_dict()
        expected_keys = {"speaker", "content", "timestamp", "metadata"}
        assert set(msg_dict.keys()) == expected_keys

        # Convert back from dict
        msg_restored = CollaborationMessage.from_dict(msg_dict)
        assert msg_restored.speaker == msg.speaker
        assert msg_restored.content == msg.content
        assert msg_restored.metadata == msg.metadata
        # Note: datetime serialization might change precision


class TestCollaborationSession:
    """Test CollaborationSession dataclass."""

    def test_session_creation(self):
        """Test basic session creation."""
        session = CollaborationSession(
            session_id="test-session-123",
            objective="Solve a complex problem",
            models=["chat_with_gpt5", "chat_with_gemini25_pro"],
            messages=[],
            current_step=0,
            mode="round_robin",
            max_steps=10,
            status="active",
        )

        assert session.session_id == "test-session-123"
        assert session.objective == "Solve a complex problem"
        assert len(session.models) == 2
        assert session.messages == []
        assert session.current_step == 0
        assert session.mode == "round_robin"
        assert session.status == "active"

    def test_session_add_message(self):
        """Test adding messages to session."""
        session = CollaborationSession(
            session_id="test",
            objective="test",
            models=["model1"],
            messages=[],
            current_step=0,
            mode="round_robin",
            max_steps=5,
            status="active",
        )

        msg = CollaborationMessage(
            speaker="user", content="Initial message", timestamp=datetime.now()
        )

        session.add_message(msg)
        assert len(session.messages) == 1
        assert session.messages[0] == msg

    def test_session_next_model_round_robin(self):
        """Test round-robin model selection."""
        session = CollaborationSession(
            session_id="test",
            objective="test",
            models=["model1", "model2", "model3"],
            messages=[],
            current_step=0,
            mode="round_robin",
            max_steps=10,
            status="active",
        )

        # Test round-robin progression
        assert session.get_next_model() == "model1"  # Step 0 -> model[0]

        session.advance_step()
        assert session.current_step == 1
        assert session.get_next_model() == "model2"  # Step 1 -> model[1]

        session.advance_step()
        assert session.current_step == 2
        assert session.get_next_model() == "model3"  # Step 2 -> model[2]

        session.advance_step()
        assert session.current_step == 3
        assert session.get_next_model() == "model1"  # Step 3 -> model[0] (wrap around)

    def test_session_max_steps_reached(self):
        """Test session completion when max steps reached."""
        session = CollaborationSession(
            session_id="test",
            objective="test",
            models=["model1"],
            messages=[],
            current_step=4,  # At max-1
            mode="round_robin",
            max_steps=5,
            status="active",
        )

        assert not session.is_completed()

        session.advance_step()  # Now at max steps
        assert session.current_step == 5
        assert session.is_completed()

    def test_session_serialization(self):
        """Test session can be converted to/from dict."""
        msg = CollaborationMessage(
            speaker="user", content="test", timestamp=datetime.now()
        )

        session = CollaborationSession(
            session_id="test-123",
            objective="Test objective",
            models=["model1", "model2"],
            messages=[msg],
            current_step=1,
            mode="orchestrator",
            max_steps=10,
            status="active",
        )

        # Convert to dict
        session_dict = session.to_dict()
        expected_keys = {
            "session_id",
            "objective",
            "models",
            "messages",
            "current_step",
            "mode",
            "max_steps",
            "status",
        }
        assert set(session_dict.keys()) == expected_keys
        assert isinstance(session_dict["messages"], list)

        # Convert back from dict
        session_restored = CollaborationSession.from_dict(session_dict)
        assert session_restored.session_id == session.session_id
        assert session_restored.objective == session.objective
        assert session_restored.models == session.models
        assert len(session_restored.messages) == 1
        assert session_restored.current_step == session.current_step


class TestCollaborationConfig:
    """Test CollaborationConfig dataclass."""

    def test_config_defaults(self):
        """Test default configuration values."""
        config = CollaborationConfig()

        assert config.max_steps == 10
        assert config.parallel_limit == 1
        assert config.timeout_per_step == 300
        assert config.summarization_threshold == 50
        assert config.cost_limit_usd is None

    def test_config_custom_values(self):
        """Test custom configuration values."""
        config = CollaborationConfig(
            max_steps=20,
            parallel_limit=3,
            timeout_per_step=600,
            summarization_threshold=100,
            cost_limit_usd=50.0,
        )

        assert config.max_steps == 20
        assert config.parallel_limit == 3
        assert config.timeout_per_step == 600
        assert config.summarization_threshold == 100
        assert config.cost_limit_usd == 50.0

    def test_config_validation(self):
        """Test configuration validation."""
        # Test invalid max_steps
        with pytest.raises(ValueError, match="max_steps must be positive"):
            CollaborationConfig(max_steps=0)

        # Test invalid parallel_limit
        with pytest.raises(ValueError, match="parallel_limit must be positive"):
            CollaborationConfig(parallel_limit=0)

        # Test invalid timeout
        with pytest.raises(ValueError, match="timeout_per_step must be positive"):
            CollaborationConfig(timeout_per_step=-1)

        # Test invalid threshold
        with pytest.raises(
            ValueError, match="summarization_threshold must be positive"
        ):
            CollaborationConfig(summarization_threshold=0)

    def test_config_serialization(self):
        """Test config can be converted to/from dict."""
        config = CollaborationConfig(
            max_steps=15, parallel_limit=2, cost_limit_usd=25.50
        )

        # Convert to dict
        config_dict = config.to_dict()
        assert config_dict["max_steps"] == 15
        assert config_dict["parallel_limit"] == 2
        assert config_dict["cost_limit_usd"] == 25.50

        # Convert back from dict
        config_restored = CollaborationConfig.from_dict(config_dict)
        assert config_restored.max_steps == config.max_steps
        assert config_restored.parallel_limit == config.parallel_limit
        assert config_restored.cost_limit_usd == config.cost_limit_usd
