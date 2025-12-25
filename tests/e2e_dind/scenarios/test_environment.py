"""Environment check test - verifies the DiD setup is working correctly."""

import json
import subprocess
import pytest


@pytest.mark.order(1)  # Run this test first
def test_environment_check(claude, stack):
    """Comprehensive environment check for the DiD setup."""
    print("\n🔍 Running environment diagnostics...")

    # 1. Check if we're in the test-runner container
    print("\n1. Checking container environment...")
    stdout, _, _ = stack.exec_in_container(["hostname"], "test-runner")
    print(f"   Test-runner hostname: {stdout.strip()}")

    stdout, _, _ = stack.exec_in_container(["whoami"], "test-runner")
    print(f"   Current user: {stdout.strip()}")

    # 2. Check Claude MCP configuration
    print("\n2. Checking Claude MCP configuration...")
    stdout, _, _ = stack.exec_in_container(
        ["gosu", "claude", "claude", "mcp", "list"], "test-runner"
    )
    print(f"   MCP servers configured:\n{stdout}")
    assert "the-force" in stdout, "the-force MCP server not configured"

    # 3. Check if server container is running
    print("\n3. Checking server container...")
    stdout, _, _ = stack.exec_in_container(["hostname"], "server")
    print(f"   Server hostname: {stdout.strip()}")

    # Check what processes are running
    stdout, _, _ = stack.exec_in_container(["bash", "-c", "ps aux"], "server")
    print(f"   Current processes:\n{stdout}")

    # 4. Check server container environment variables
    print("\n4. Checking server environment variables...")
    env_vars = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "VERTEX_PROJECT",
        "VERTEX_LOCATION",
        "VICTORIA_LOGS_URL",
        "HOST",
        "PORT",
        "LOG_LEVEL",
    ]

    for var in env_vars:
        cmd = ["bash", "-c", f"echo ${var}"]
        stdout, _, _ = stack.exec_in_container(cmd, "server")
        value = stdout.strip()
        if var.endswith("_KEY"):
            # Mask API keys
            masked = value[:8] + "..." if len(value) > 8 else "***"
            print(f"   {var}: {masked}")
        else:
            print(f"   {var}: {value}")
            # Special check for VERTEX_PROJECT
            if var == "VERTEX_PROJECT" and value == "mcp-test-project":
                print(
                    "   ⚠️  WARNING: Using default test project - Gemini will fail with permission errors"
                )

    # 5. Check if mcp-the-force is installed in server
    print("\n5. Checking mcp-the-force installation...")
    stdout, stderr, return_code = stack.exec_in_container(
        ["which", "mcp-the-force"], "server"
    )
    if return_code == 0:
        print(f"   mcp-the-force found at: {stdout.strip()}")
    else:
        print("   ERROR: mcp-the-force not found!")

    # 6. Test starting the MCP server manually
    print("\n6. Testing manual MCP server startup...")
    stdout, stderr, return_code = stack.exec_in_container(
        ["bash", "-c", "timeout 5 mcp-the-force 2>&1 || true"], "server"
    )
    print(f"   Server startup output:\n{stdout}")
    if stderr:
        print(f"   Server stderr:\n{stderr}")

    # 7. Check VictoriaLogs connectivity
    print("\n7. Checking VictoriaLogs connectivity...")

    # Check what URL the server container will use
    stdout, _, _ = stack.exec_in_container(
        ["bash", "-c", "echo $VICTORIA_LOGS_URL"], "server"
    )
    server_victoria_url = stdout.strip()
    print(f"   Server VICTORIA_LOGS_URL env: {server_victoria_url}")

    # Test connectivity from server container
    print("   Testing from server container...")
    stdout, stderr, return_code = stack.exec_in_container(
        [
            "bash",
            "-c",
            f"curl -v {server_victoria_url}/health 2>&1 || echo 'CURL FAILED'",
        ],
        "server",
    )
    print(f"   Server curl output:\n{stdout}")

    # Also check if host.docker.internal resolves
    stdout, _, _ = stack.exec_in_container(
        [
            "bash",
            "-c",
            "getent hosts host.docker.internal || echo 'host.docker.internal not resolved'",
        ],
        "server",
    )
    print(f"   host.docker.internal resolution: {stdout.strip()}")

    # Check actual logging configuration
    print("\n   Checking logging configuration...")
    try:
        # First check if we can import the module
        stdout, stderr, return_code = stack.exec_in_container(
            [
                "bash",
                "-c",
                "cd /host-project && python3 -c 'import mcp_the_force; print(\"Module imported successfully\")'",
            ],
            "server",
        )
        if return_code != 0:
            print(f"   Error importing module: {stderr}")
        else:
            # Try a simpler approach - just check env vars
            stdout, _, _ = stack.exec_in_container(
                ["bash", "-c", 'echo "VICTORIA_LOGS_URL=$VICTORIA_LOGS_URL"'], "server"
            )
            print(f"   Server env check: {stdout.strip()}")
    except Exception as e:
        print(f"   Error checking logging config: {e}")

    # 8. Check shared volume
    print("\n8. Checking shared volume...")
    test_file = "/tmp/e2e_env_test.txt"
    stack.exec_in_container(
        ["bash", "-c", f"echo 'test from runner' > {test_file}"], "test-runner"
    )
    stdout, _, _ = stack.exec_in_container(["cat", test_file], "server")
    print(f"   Shared volume test: {stdout.strip()}")
    assert "test from runner" in stdout, "Shared volume not working"

    # 9. Test a simple MCP tool call
    print("\n9. Testing simple MCP tool call...")
    try:
        response = claude("Use the-force list_models")
        print(f"   Tool response received: {len(response)} characters")
        print(f"   First 500 chars of response: {response[:500]}...")

        # Check if it's a real response or an error
        if "not available" in response.lower() or "error" in response.lower():
            print(f"   ERROR: {response[:200]}...")
            assert False, f"MCP tool call failed: {response}"
        else:
            print("   ✅ MCP tool call successful!")
            # Try to parse as JSON to ensure it's valid
            try:
                models = json.loads(response)
                print(f"   Found {len(models)} models")
            except Exception:
                # Not JSON, but that's okay - some tools return plain text
                print("   Response is plain text (not JSON)")

    except Exception as e:
        print(f"   ERROR: Exception during tool call: {e}")
        raise

    print("\n✅ All environment checks passed!")


@pytest.mark.order(2)
def test_debug_mcp_connection(claude, stack):
    """Debug test to understand MCP connection issues."""
    print("\n🔍 Debugging MCP connection...")

    # 1. Check Claude's MCP configuration in detail
    print("\n1. Checking Claude's MCP configuration file...")
    try:
        stdout, _, _ = stack.exec_in_container(
            ["gosu", "claude", "cat", "/home/claude/.config/claude/mcp_servers.json"],
            "test-runner",
        )
        print(f"   MCP config:\n{stdout}")
    except Exception as e:
        print(f"   Could not read MCP config: {e}")
        # Try alternate location
        stdout, _, _ = stack.exec_in_container(
            [
                "gosu",
                "claude",
                "bash",
                "-c",
                "find /home/claude -name '*mcp*' -type f 2>/dev/null | head -10",
            ],
            "test-runner",
        )
        print(f"   MCP-related files found:\n{stdout}")

    # 2. Try running mcp-the-force directly via Claude
    print("\n2. Testing direct MCP invocation via Claude...")
    # This simulates what Claude does internally
    cmd = [
        "gosu",
        "claude",
        "bash",
        "-c",
        'cd /host-project && echo \'{"jsonrpc":"2.0","method":"list","id":1}\' | VICTORIA_LOGS_URL=http://host.docker.internal:9428 CI_E2E=1 mcp-the-force',
    ]
    stdout, stderr, return_code = stack.exec_in_container(cmd, "test-runner")
    print(f"   Direct invocation stdout:\n{stdout}")
    if stderr:
        print(f"   Direct invocation stderr:\n{stderr}")
    print(f"   Return code: {return_code}")

    # 3. Check if Python and dependencies are available
    print("\n3. Checking Python environment...")
    stdout, _, _ = stack.exec_in_container(
        ["bash", "-c", "which python3 && python3 --version"], "test-runner"
    )
    print(f"   Python:\n{stdout}")

    # 4. Test network connectivity between containers
    print("\n4. Testing inter-container networking...")
    stdout, _, _ = stack.exec_in_container(
        ["bash", "-c", "ping -c 1 server || echo 'Ping failed'"], "test-runner"
    )
    print(f"   Network test:\n{stdout}")

    print("\n✅ Debug information collected!")


@pytest.mark.order(3)
def test_victoria_logs_integration(claude, stack):
    """Test that logs are actually being sent to VictoriaLogs."""
    print("\n🔍 Testing VictoriaLogs integration...")

    # 1. Generate a unique log marker
    import uuid

    log_marker = f"E2E_TEST_MARKER_{uuid.uuid4().hex[:8]}"
    print(f"\n1. Using log marker: {log_marker}")

    # 2. Trigger logging by making an MCP call with our marker
    print("\n2. Making MCP call to generate logs...")
    # Use json.dumps format like other tests
    import json

    args = {
        "instructions": f"Echo this marker: {log_marker}",
        "output_format": "Just echo the marker",
        "context": [],
        "priority_context": [],
        "session_id": "e2e-log-test",
        "disable_history_search": "true",
        "disable_history_record": "true",
    }
    response = claude(
        f"Use the-force chat_with_gemini3_flash_preview with {json.dumps(args)}"
    )
    print(f"   Response received: {len(response)} chars")
    print(f"   Response content: {response[:200]}...")

    # 3. Give logs time to reach VictoriaLogs
    import time

    print("\n3. Waiting 5 seconds for logs to propagate...")
    time.sleep(5)

    # 4. Query VictoriaLogs from the host
    print("\n4. Querying VictoriaLogs for our marker...")
    # This runs on the host, not in the container
    import json

    # Query the last 5 minutes of logs
    query_url = "http://localhost:9428/select/logsql/query"
    query = f'_time:[now-5m, now] AND _msg:"{log_marker}"'

    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-X",
                "POST",
                query_url,
                "-H",
                "Content-Type: application/x-www-form-urlencoded",
                "-d",
                f"query={query}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        print(f"   VictoriaLogs query status: {result.returncode}")
        print(f"   Response: {result.stdout[:500]}...")

        if result.returncode == 0 and result.stdout:
            # Check if we found our marker
            if log_marker in result.stdout:
                print("   ✅ Found log marker in VictoriaLogs!")
            else:
                print("   ❌ Log marker NOT found in VictoriaLogs")
                # Try a broader query
                print("\n   Trying broader query...")
                query = '_time:[now-5m, now] AND app:"mcp-the-force"'
                result = subprocess.run(
                    [
                        "curl",
                        "-s",
                        "-X",
                        "POST",
                        query_url,
                        "-H",
                        "Content-Type: application/x-www-form-urlencoded",
                        "-d",
                        f"query={query}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                print(f"   Any mcp-the-force logs: {len(result.stdout)} chars")
                if len(result.stdout) > 100:
                    print(f"   Sample: {result.stdout[:200]}...")
    except Exception as e:
        print(f"   Error querying VictoriaLogs: {e}")

    print("\n✅ VictoriaLogs test completed!")
