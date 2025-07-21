"""E2E DinD test configuration and fixtures."""

import json
import os
import time
import uuid
import base64
from pathlib import Path
from typing import Callable
import pytest
from testcontainers.compose import DockerCompose

# Base template directory
_TEMPLATE_DIR = Path("/compose-template")


@pytest.fixture(scope="function")
def stack(request):
    """Create an isolated Docker compose stack for each test."""
    project = f"e2e_{uuid.uuid4().hex[:6]}"

    # Create unique compose directory for this test to avoid conflicts
    import shutil

    stack_dir = Path(f"/tmp/compose-{project}")
    stack_dir.mkdir(parents=True, exist_ok=True)

    # Copy template files to isolated directory
    shutil.copytree(_TEMPLATE_DIR, stack_dir, dirs_exist_ok=True)

    # Set up environment variables for the stack
    env_vars = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
        "VERTEX_PROJECT": os.getenv("VERTEX_PROJECT", ""),  # Don't default yet
        "VERTEX_LOCATION": os.getenv("VERTEX_LOCATION", "us-central1"),
    }

    # Detect and prepare Google Cloud credentials for container injection
    creds_json = None

    # 1. explicit service-account JSON handed in as a secret
    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

    # 2. a file path supplied by GOOGLE_APPLICATION_CREDENTIALS
    if creds_json is None:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path and Path(cred_path).exists():
            creds_json = Path(cred_path).read_text()

    # 3. user's local ADC (~/.config/gcloud/…)
    if creds_json is None:
        adc_default = (
            Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
        )
        if adc_default.exists():
            creds_json = adc_default.read_text()

    # 4. build an authorised_user blob from refresh-token triplet
    if creds_json is None and all(
        os.getenv(v)
        for v in (
            "GCLOUD_USER_REFRESH_TOKEN",
            "GCLOUD_OAUTH_CLIENT_ID",
            "GCLOUD_OAUTH_CLIENT_SECRET",
        )
    ):
        creds_json = json.dumps(
            {
                "type": "authorized_user",
                "client_id": os.getenv("GCLOUD_OAUTH_CLIENT_ID"),
                "client_secret": os.getenv("GCLOUD_OAUTH_CLIENT_SECRET"),
                "refresh_token": os.getenv("GCLOUD_USER_REFRESH_TOKEN"),
            },
            indent=2,
        )

    # If we found credentials, prepare them for container injection
    if creds_json:
        env_vars["GOOGLE_APPLICATION_CREDENTIALS"] = (
            "/home/claude/.config/gcloud/application_default_credentials.json"
        )
        env_vars["ADC_JSON_B64"] = base64.b64encode(creds_json.encode()).decode()

        # ------------------------------------------------------------------
        # Load VERTEX_PROJECT from config.yaml/secrets.yaml if not set
        # ------------------------------------------------------------------
        if not env_vars["VERTEX_PROJECT"]:
            try:
                import yaml

                # Check for config files in the project root
                project_root = Path(
                    __file__
                ).parent.parent.parent  # tests/e2e_dind/conftest.py -> project root
                config_file = project_root / "config.yaml"
                secrets_file = project_root / "secrets.yaml"

                vertex_project = None

                # Try loading from config.yaml first
                if config_file.exists():
                    with open(config_file) as f:
                        config_data = yaml.safe_load(f) or {}
                        # Check both new and legacy formats
                        vertex_config = config_data.get(
                            "vertex", {}
                        ) or config_data.get("providers", {}).get("vertex", {})
                        vertex_project = vertex_config.get("project")
                        if vertex_project:
                            print(
                                f"✅ Loaded VERTEX_PROJECT from config.yaml: {vertex_project}"
                            )

                # Try secrets.yaml if not found
                if not vertex_project and secrets_file.exists():
                    with open(secrets_file) as f:
                        secrets_data = yaml.safe_load(f) or {}
                        # Check both new and legacy formats
                        vertex_config = secrets_data.get(
                            "vertex", {}
                        ) or secrets_data.get("providers", {}).get("vertex", {})
                        vertex_project = vertex_config.get("project")
                        if vertex_project:
                            print(
                                f"✅ Loaded VERTEX_PROJECT from secrets.yaml: {vertex_project}"
                            )

                if vertex_project:
                    env_vars["VERTEX_PROJECT"] = vertex_project
                else:
                    print("⚠️  No VERTEX_PROJECT found in config.yaml or secrets.yaml")

            except Exception as e:
                print(f"⚠️  Failed to load VERTEX_PROJECT from config files: {e}")

        # If we still don't have a project, default to test project
        if not env_vars["VERTEX_PROJECT"]:
            env_vars["VERTEX_PROJECT"] = "mcp-test-project"
            print(
                "⚠️  No VERTEX_PROJECT found, using default test project (Gemini will fail)"
            )
    else:
        # No credentials found, skip Gemini tests
        import pytest

        pytest.skip("No GCP credentials available – cannot run Gemini / Vertex tests")

    # Set environment variables in os.environ for Docker Compose interpolation
    os.environ.update(env_vars)
    print(
        f"DEBUG: Stack fixture VERTEX_PROJECT: {env_vars.get('VERTEX_PROJECT', 'NOT SET')}"
    )

    # Create compose instance using isolated directory
    compose = DockerCompose(
        stack_dir.as_posix(),
        compose_file_name="stack.yml",
        pull=False,
        wait=False,  # Don't use --wait since our container runs indefinitely
    )

    # Set project name BEFORE starting
    compose.project_name = project

    # Now start the compose stack
    try:
        compose.start()
    except Exception as e:
        # Capture detailed error information for debugging
        import subprocess

        try:
            # Try to manually run the compose command to see the error
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    "stack.yml",
                    "up",
                    "--detach",
                    "--no-color",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=stack_dir.as_posix(),
                env=os.environ,
            )
            print("=== Manual compose up output ===")
            print(f"Return code: {result.returncode}")
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}")

            # Also try to check if the image exists
            img_check = subprocess.run(
                ["docker", "images", "mcp-e2e-runner:latest"],
                capture_output=True,
                text=True,
                check=False,
            )
            print("=== Image check ===")
            print(f"Images: {img_check.stdout}")
        except Exception as log_err:
            print(f"Failed to debug compose: {log_err}")

        # Re-raise original error with context
        raise RuntimeError(f"Failed to start compose stack: {e}")

    try:
        # Give a moment for containers to fully start
        time.sleep(3)

        # Wait for server container to be ready
        print("Waiting for server container to be ready...")
        for i in range(30):
            try:
                # Try a simple command to check if container is responsive
                stdout, stderr, return_code = compose.exec_in_container(
                    ["echo", "ready"], "server"
                )
                if return_code == 0:
                    print("✅ Server container is ready")
                    break
            except Exception:
                pass

            if i == 29:
                print("⚠️  Server container failed to become ready")
                raise RuntimeError("Server container not responding after 30 seconds")

            time.sleep(1)

        # Inject Google Cloud credentials into the container if we found them
        if "ADC_JSON_B64" in env_vars:
            try:
                # Write the credentials directly using a simpler approach
                adc_b64 = env_vars["ADC_JSON_B64"]
                creds_path = (
                    "/home/claude/.config/gcloud/application_default_credentials.json"
                )

                # Create the directory first
                stdout, stderr, return_code = compose.exec_in_container(
                    [
                        "bash",
                        "-c",
                        "mkdir -p /home/claude/.config/gcloud && chown -R claude:claude /home/claude/.config",
                    ],
                    "test-runner",
                )

                if return_code != 0:
                    print(f"Warning: Failed to create gcloud directory: {stderr}")
                else:
                    # Now inject the credentials using echo with the base64 data
                    cmd = f'echo "{adc_b64}" | base64 -d > {creds_path} && chown claude:claude {creds_path} && chmod 600 {creds_path}'
                    stdout, stderr, return_code = compose.exec_in_container(
                        ["bash", "-c", cmd], "test-runner"
                    )

                    if return_code != 0:
                        print(f"Warning: Failed to inject ADC credentials: {stderr}")
                    else:
                        print("✅ Google Cloud ADC installed for claude user")

                        # Verify the file was created
                        stdout, stderr, return_code = compose.exec_in_container(
                            ["bash", "-c", f"ls -la {creds_path}"], "test-runner"
                        )
                        if return_code == 0:
                            print(f"Credentials file verified: {stdout.strip()}")

            except Exception as e:
                print(f"Warning: Failed to inject credentials: {e}")
        else:
            import pytest

            pytest.skip(
                "No GCP credentials available – cannot run Gemini / Vertex tests"
            )

        # Return compose instance for test use
        yield compose
    finally:
        # CRITICAL: Nuke all OpenAI resources before destroying containers
        try:
            print("\n🔥 NUKING all OpenAI vector stores created during E2E tests...")
            stdout, stderr, return_code = compose.exec_in_container(
                [
                    "curl",
                    "-s",
                    "-X",
                    "POST",
                    "-H",
                    "Content-Type: application/json",
                    "http://localhost:9876/nuke",
                ],
                "server",
            )
            if return_code == 0:
                try:
                    result = json.loads(stdout)
                    print(
                        f"✅ NUKE COMPLETE: {result.get('message', 'Unknown result')}"
                    )
                except Exception:
                    print(
                        f"✅ NUKE completed (raw response: {stdout.strip()[:200]}...)"
                    )
            else:
                print(f"⚠️  NUKE failed: {stderr}")
        except Exception as e:
            print(f"⚠️  Failed to nuke OpenAI resources: {e}")
            print("⚠️  WARNING: OpenAI vector stores may be orphaned!")

        # Clean up - testcontainers stop() doesn't accept extra parameters
        try:
            # Force stop and remove containers to prevent hanging
            compose.stop()
            # Additional cleanup to ensure containers are fully removed
            import subprocess

            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    "stack.yml",
                    "down",
                    "--remove-orphans",
                    "--volumes",
                ],
                cwd=stack_dir.as_posix(),
                capture_output=True,
                timeout=30,
            )
        except Exception as e:
            # Log cleanup errors but don't fail the test
            print(f"Warning: Failed to clean up compose stack: {e}")

        # Clean up temporary directory
        try:
            import shutil

            shutil.rmtree(stack_dir, ignore_errors=True)
        except Exception as e:
            print(f"Warning: Failed to clean up temporary directory {stack_dir}: {e}")


@pytest.fixture
def claude(stack, request) -> Callable[[str, int], str]:
    """
    Returns a callable `claude(prompt: str, timeout=60) -> str`
    with proper MCP configuration.
    """

    # Get the resolved VERTEX_PROJECT from the server container's environment
    stdout, _, _ = stack.exec_in_container(
        ["bash", "-c", "echo $VERTEX_PROJECT"], "server"
    )
    resolved_vertex_project = stdout.strip() or os.getenv(
        "VERTEX_PROJECT", "mcp-test-project"
    )
    print(f"DEBUG: Resolved VERTEX_PROJECT for Claude MCP: {resolved_vertex_project}")

    stdout, _, _ = stack.exec_in_container(
        ["bash", "-c", "echo $VERTEX_LOCATION"], "server"
    )
    resolved_vertex_location = stdout.strip() or os.getenv(
        "VERTEX_LOCATION", "us-central1"
    )

    # Configure MCP server using claude mcp add-json
    mcp_config = {
        "command": "mcp-second-brain",
        "args": [],
        "env": {
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
            "VERTEX_PROJECT": resolved_vertex_project,
            "VERTEX_LOCATION": resolved_vertex_location,
            "GOOGLE_APPLICATION_CREDENTIALS": "/home/claude/.config/gcloud/application_default_credentials.json",
            "LOG_LEVEL": "DEBUG",
            "CI_E2E": "1",  # This MUST be set for the MCP server to allow /tmp paths
            "PYTHONPATH": "/host-project",
            "VICTORIA_LOGS_URL": "http://host.docker.internal:9428",  # Critical for logging!
            "LOITER_KILLER_URL": "http://localhost:9876",  # LoiterKiller running in server container
            # Stable list is now always enabled - no feature flag needed
        },
        "timeout": 60000,
        "description": "MCP Second-Brain server",
    }

    # Configure MCP server
    config_cmd = [
        "gosu",
        "claude",
        "claude",
        "mcp",
        "add-json",
        "second-brain",
        json.dumps(mcp_config),
    ]

    try:
        stdout, stderr, return_code = stack.exec_in_container(config_cmd, "test-runner")
        if return_code != 0:
            print(f"MCP configuration failed: {stderr}")
            raise RuntimeError(f"Failed to configure MCP server: {stderr}")
        print(f"MCP server configured successfully: {stdout}")
    except Exception as e:
        print(f"Failed to configure MCP: {e}")
        raise

    def run_claude(prompt: str, timeout: int = 60) -> str:
        """Execute claude command."""
        import shlex

        # Build command with proper parameter order: command first, service name second
        # Use gosu to run Claude CLI as non-root user to allow --dangerously-skip-permissions
        cmd = [
            "gosu",
            "claude",
            "bash",
            "-c",
            f"cd /host-project && claude -p --dangerously-skip-permissions {shlex.quote(prompt)}",
        ]

        try:
            # Call exec_in_container with correct parameter order
            stdout, stderr, return_code = stack.exec_in_container(cmd, "test-runner")

            if return_code != 0:
                # Collect logs on failure
                _collect_failure_logs(stack)
                raise RuntimeError(
                    f"Claude Code failed (exit {return_code}): {stderr.strip()}"
                )

            return stdout

        except Exception as e:
            _collect_failure_logs(stack)
            # Try to extract stderr from CalledProcessError if available
            if hasattr(e, "stderr") and e.stderr:
                error_detail = f"stderr: {e.stderr.strip()}"
            elif hasattr(e, "stdout") and e.stdout:
                error_detail = f"stdout: {e.stdout.strip()}"
            else:
                error_detail = str(e)
            raise RuntimeError(f"Claude command failed: {error_detail}")

    return run_claude


def _collect_failure_logs(compose: DockerCompose) -> None:
    """Collect logs from all containers on test failure."""
    artifact_dir = os.getenv("E2E_ARTIFACT_DIR", "/tmp/artifacts")
    os.makedirs(artifact_dir, exist_ok=True)

    try:
        # Get logs from all services
        for service in ["test-runner"]:
            try:
                logs = compose.get_logs(service)
                log_file = Path(artifact_dir) / f"{compose.project_name}-{service}.log"
                log_file.write_text(logs[0] if logs else "No logs available")
            except Exception as e:
                print(f"Failed to collect logs for {service}: {e}")
    except Exception as e:
        print(f"Failed to collect failure logs: {e}")
