"""Attachment search test - RAG workflow using attachments parameter."""

import tempfile
import os
import json
import sys
import time

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


def test_attachment_search_workflow(claude):
    """Test RAG workflow using attachments parameter for automatic vector store creation."""

    # Step 1: Create test documents with unique, identifiable content
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create test files with distinctive technical content
        doc1 = os.path.join(tmp_dir, "quantum_algorithm.md")
        with open(doc1, "w") as f:
            f.write("""# Quantum Computing Algorithm QALG-9000
            
The QALG-9000 quantum algorithm implements a novel approach to factorization.
Key specifications:
- Operates on 256-qubit systems
- Uses Shor's algorithm as base framework  
- Efficiency rating: O(log³ n)
- Required coherence time: 15.7 microseconds
- Works with dilution refrigerator cooling

## Implementation Details
The algorithm requires specific quantum gates: Hadamard, CNOT, and Toffoli gates.
Calibration constant: ZEBRA-FLUX-42 must be set to 3.14159 for proper operation.
""")

        doc2 = os.path.join(tmp_dir, "neural_network.md")
        with open(doc2, "w") as f:
            f.write("""# Neural Network Architecture NET-X7

NET-X7 is a transformer-based architecture for natural language processing.
Architecture details:
- 48 attention heads
- 512-dimensional embeddings
- Uses ReLU activation functions
- Training dataset: 50TB of text data
- Convergence time: 72 hours on TPU-v4

## Training Parameters
Learning rate starts at 0.001 with cosine decay schedule.
Special token: ALPHA-PRIME-99 used for sequence boundaries.
""")

        # Define schemas for structured responses
        search_schema = {
            "type": "object",
            "properties": {
                "algorithm_name": {"type": "string"},
                "key_specification": {"type": "string"},
                "found_in_docs": {"type": "boolean"},
            },
            "required": ["algorithm_name", "key_specification", "found_in_docs"],
            "additionalProperties": False,
        }

        # Step 2: Test RAG query for quantum algorithm content
        args = {
            "instructions": "What quantum algorithm is described in these documents and what is its efficiency rating?",
            "output_format": "JSON object with algorithm details found in the documents",
            "context": [],
            "attachments": [tmp_dir],  # Directory containing our test files
            "session_id": "rag-quantum-test",
            "structured_output_schema": search_schema,
        }

        # retry loop – reasonable timeout for E2E testing
        MAX_ATTEMPTS = 8  # Reduced from 25 for faster testing
        for attempt in range(MAX_ATTEMPTS):
            response = claude(
                f"Use second-brain chat_with_gpt4_1 with {json.dumps(args)} and respond ONLY with the JSON."
            )

            # Parse response - handle execution errors
            try:
                result = safe_json(response)
                # If found, break out of retry loop
                if result.get("found_in_docs"):
                    break
            except AssertionError:
                # If we got an execution error, treat as not found and continue
                if "execution error" in response.lower():
                    result = {
                        "found_in_docs": False,
                        "algorithm_name": "",
                        "key_specification": "",
                    }
                else:
                    raise

            # If not found and not last attempt, wait and retry
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(2)  # Fixed 2-second delay instead of progressive

        # Validate quantum algorithm response (after retries)
        assert (
            result["found_in_docs"] is True
        ), f"Failed to find content after {MAX_ATTEMPTS} attempts. Last result: {result}"
        assert "QALG-9000" in result["algorithm_name"]
        assert (
            "log³ n" in result["key_specification"]
            or "O(log³ n)" in result["key_specification"]
        )

        # Step 3: Test RAG query for neural network content
        args = {
            "instructions": "What neural network architecture is documented and how many attention heads does it have?",
            "output_format": "JSON object with neural network details",
            "context": [],
            "attachments": [tmp_dir],
            "session_id": "rag-neural-test",
            "structured_output_schema": {
                "type": "object",
                "properties": {
                    "architecture_name": {"type": "string"},
                    "attention_heads": {"type": "integer"},
                    "found_in_docs": {"type": "boolean"},
                },
                "required": ["architecture_name", "attention_heads", "found_in_docs"],
                "additionalProperties": False,
            },
        }

        response = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args)} and respond ONLY with the JSON."
        )

        # Parse and validate neural network response
        result = safe_json(response)
        assert result["found_in_docs"] is True
        assert "NET-X7" in result["architecture_name"]
        assert result["attention_heads"] == 48

        # Step 4: Test query for specific unique tokens
        args = {
            "instructions": "Find any special tokens or constants mentioned in these documents. Look for anything with ZEBRA, ALPHA, or PRIME in the name.",
            "output_format": "JSON object listing any special tokens found",
            "context": [],
            "attachments": [tmp_dir],
            "session_id": "rag-tokens-test",
            "structured_output_schema": {
                "type": "object",
                "properties": {
                    "tokens_found": {"type": "array", "items": {"type": "string"}},
                    "total_count": {"type": "integer"},
                },
                "required": ["tokens_found", "total_count"],
                "additionalProperties": False,
            },
        }

        response = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args)} and respond ONLY with the JSON."
        )

        # Parse and validate token search response
        result = safe_json(response)
        assert (
            result["total_count"] >= 2
        )  # Should find ZEBRA-FLUX-42 and ALPHA-PRIME-99
        found_tokens = " ".join(result["tokens_found"]).upper()
        assert "ZEBRA-FLUX-42" in found_tokens or "ZEBRA" in found_tokens
        assert "ALPHA-PRIME-99" in found_tokens or "ALPHA" in found_tokens

        # Step 5: Test negative case - query for non-existent content
        args = {
            "instructions": "What blockchain consensus algorithm is described in these documents?",
            "output_format": "JSON object indicating if blockchain content was found",
            "context": [],
            "attachments": [tmp_dir],
            "session_id": "rag-negative-test",
            "structured_output_schema": {
                "type": "object",
                "properties": {
                    "blockchain_found": {"type": "boolean"},
                    "explanation": {"type": "string"},
                },
                "required": ["blockchain_found", "explanation"],
                "additionalProperties": False,
            },
        }

        response = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args)} and respond ONLY with the JSON."
        )

        # Parse and validate negative response
        result = safe_json(response)
        assert result["blockchain_found"] is False
        assert len(result["explanation"]) > 10  # Should have meaningful explanation
