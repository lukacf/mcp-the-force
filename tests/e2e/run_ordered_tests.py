#!/usr/bin/env python3
"""Run E2E tests in order from simplest to most complex."""

import subprocess
import sys

# Tests ordered from simplest to most complex
ORDERED_TESTS = [
    # 1. Basic smoke tests
    "tests/e2e/test_smoke.py",
    # 2. Simple tool tests
    "tests/e2e/test_token_counter.py",
    # 3. Session functionality
    "tests/e2e/test_session_debug.py",
    # 4. Multi-turn conversations
    "tests/e2e/test_multi_turn.py",
    # 5. Memory persistence
    "tests/e2e/test_memory.py",
    # 6. Structured outputs
    "tests/e2e/test_structured_output.py",
    # 7. Attachment handling
    "tests/e2e/test_attachment_search_real.py",
    # 8. Complex scenarios
    "tests/e2e/test_scenarios.py",
]


def main():
    """Run tests in order."""
    # Filter out duplicate pytest arguments
    extra_args = []
    for arg in sys.argv[1:]:
        # Skip pytest command itself and test paths
        if arg not in ["pytest", "tests/e2e"] and not arg.startswith("tests/e2e/"):
            extra_args.append(arg)

    # Build pytest command
    cmd = ["pytest", "-xv"] + extra_args + ORDERED_TESTS

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
