import json
import uuid
import pytest

pytestmark = pytest.mark.e2e


class TestCrossModelSession:
    """Verify sessions persist across different model adapters."""

    @pytest.mark.timeout(300)
    def test_gpt4_to_gemini_session(self, claude_code):
        """Store a fact with GPT-4.1 and retrieve it with Gemini 2.5 Flash."""
        session_id = f"cross-model-{uuid.uuid4().hex[:8]}"
        secret_word = f"SECRET_{uuid.uuid4().hex[:4]}"

        args1 = {
            "instructions": f"Remember this secret word: {secret_word}. Just acknowledge.",
            "output_format": "text",
            "context": [],
            "session_id": session_id,
        }
        output1 = claude_code(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args1)}"
        )
        print(f"GPT-4.1 output: {output1}")
        assert output1.strip()

        args2 = {
            "instructions": "What secret word did I give you earlier? Just say the word.",
            "output_format": "text",
            "context": [],
            "session_id": session_id,
        }
        output2 = claude_code(
            f"Use second-brain chat_with_gemini25_flash with {json.dumps(args2)}"
        )
        print(f"Gemini output: {output2}")

        assert secret_word.lower() in output2.lower()
