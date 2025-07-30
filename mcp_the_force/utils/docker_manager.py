"""Docker container management for MCP server dependencies."""

import asyncio
import logging
import subprocess
import time
from typing import List
import httpx

logger = logging.getLogger(__name__)


class DockerManager:
    """Manages Docker containers required by the MCP server."""

    def __init__(self):
        self.compose_file = "docker-compose.yaml"
        self.required_services = {
            "victorialogs": {
                "health_url": "http://localhost:9428/health",
                "health_timeout": 30,
                "required": False,  # Nice to have, but not critical
            },
        }

    async def ensure_services_running(self) -> bool:
        """Ensure all required Docker services are running.

        Returns:
            True if all required services are healthy, False otherwise.
        """
        # Check if docker and docker-compose are available
        if not self._check_docker_available():
            logger.warning("Docker not available, skipping container management")
            return False

        # Check which services need to be started
        services_to_start = []
        for service_name, config in self.required_services.items():
            if not await self._is_service_healthy(service_name, config["health_url"]):
                services_to_start.append(service_name)

        if not services_to_start:
            logger.info("All required Docker services are already running")
            return True

        # Start services
        logger.info(f"Starting Docker services: {', '.join(services_to_start)}")
        if not self._start_services(services_to_start):
            return False

        # Wait for services to become healthy
        all_healthy = True
        for service_name in services_to_start:
            config = self.required_services[service_name]
            if not await self._wait_for_healthy(
                service_name, config["health_url"], config["health_timeout"]
            ):
                if config["required"]:
                    logger.error(f"Required service {service_name} failed to start")
                    all_healthy = False
                else:
                    logger.warning(f"Optional service {service_name} failed to start")

        return all_healthy

    def _check_docker_available(self) -> bool:
        """Check if Docker and docker-compose are available."""
        try:
            # Check Docker
            result = subprocess.run(
                ["docker", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return False

            # Check docker-compose (try both variants)
            for cmd in [
                ["docker-compose", "--version"],
                ["docker", "compose", "version"],
            ]:
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        return True
                except (subprocess.SubprocessError, FileNotFoundError):
                    continue

            return False
        except Exception as e:
            logger.debug(f"Docker check failed: {e}")
            return False

    async def _is_service_healthy(self, service_name: str, health_url: str) -> bool:
        """Check if a service is healthy via its health endpoint."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(health_url)
                return bool(response.status_code == 200)
        except Exception:
            return False

    def _start_services(self, services: List[str]) -> bool:
        """Start specified Docker services."""
        try:
            # Try docker-compose first, then docker compose
            for cmd_base in [["docker-compose"], ["docker", "compose"]]:
                try:
                    cmd = cmd_base + ["-f", self.compose_file, "up", "-d"] + services

                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=60
                    )

                    if result.returncode == 0:
                        logger.info(
                            f"Successfully started services: {', '.join(services)}"
                        )
                        return True
                    else:
                        logger.debug(
                            f"Failed with {' '.join(cmd_base)}: {result.stderr}"
                        )
                except (subprocess.SubprocessError, FileNotFoundError):
                    continue

            logger.error("Failed to start Docker services")
            return False
        except Exception as e:
            logger.error(f"Error starting Docker services: {e}")
            return False

    async def _wait_for_healthy(
        self, service_name: str, health_url: str, timeout: int
    ) -> bool:
        """Wait for a service to become healthy."""
        start_time = time.time()
        logger.info(f"Waiting for {service_name} to become healthy...")

        # Give the service a moment to start before checking
        await asyncio.sleep(3)

        while time.time() - start_time < timeout:
            if await self._is_service_healthy(service_name, health_url):
                logger.info(f"{service_name} is healthy")
                return True
            await asyncio.sleep(2)

        logger.error(f"{service_name} failed to become healthy within {timeout}s")
        return False

    async def stop_services(self):
        """Stop all managed Docker services (for cleanup)."""
        if not self._check_docker_available():
            return

        try:
            for cmd_base in [["docker-compose"], ["docker", "compose"]]:
                try:
                    cmd = cmd_base + ["-f", self.compose_file, "down"]

                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30
                    )

                    if result.returncode == 0:
                        logger.info("Successfully stopped Docker services")
                        return
                except (subprocess.SubprocessError, FileNotFoundError):
                    continue
        except Exception as e:
            logger.error(f"Error stopping Docker services: {e}")


# Global instance
docker_manager = DockerManager()
