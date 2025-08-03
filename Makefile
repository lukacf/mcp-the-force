# Use .DEFAULT_GOAL to show help by default if no target is specified.
.DEFAULT_GOAL := help

# Define variables to avoid repetition
PYTEST := pytest
FAST_UNIT_MARKER := "not slow and not e2e and not integration"

# Docker image versioning based on Git SHA to avoid unnecessary rebuilds
SHA := $(shell git rev-parse --short HEAD)
RUNNER_IMG := the-force-e2e-runner:$(SHA)
SERVER_IMG := the-force-e2e-server:$(SHA)

# Phony targets ensure these are always run, regardless of file names.
.PHONY: help install-hooks lint test test-unit test-integration e2e test-all ci clean backup build-e2e-images

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Available targets:"
	@echo "  install-hooks    Install git pre-commit and pre-push hooks."
	@echo "  lint             Run static analysis (ruff, mypy)."
	@echo "  test             Run fast unit tests (for pre-commit)."
	@echo "  test-unit        Run the full unit test suite with coverage."
	@echo "  test-integration Run integration tests (uses mock adapters)."
	@echo "  e2e              Run e2e tests (all or specific: make e2e TEST=scenarios/test_smoke.py)."
	@echo "  test-all         Run all tests (unit, integration, e2e)."
	@echo "  ci               Run the main CI suite (lint, unit, integration)."
	@echo "  clean            Remove temporary files and caches."
	@echo "  backup           Manually backup SQLite databases."

install-hooks:
	@echo "Installing pre-commit hooks..."
	pre-commit install
	pre-commit install --hook-type pre-push
	@echo "✓ Pre-commit hooks installed!"
	@echo "  - Fast checks will run on every commit"
	@echo "  - Full unit tests will run on push (skip with --no-verify)"

build-e2e-images:
	@echo "Building E2E Docker images with SHA-based tags..."
	@if ! docker image inspect $(RUNNER_IMG) >/dev/null 2>&1 ; then \
		echo "🔨  Building $(RUNNER_IMG)..."; \
		docker build -f tests/e2e_dind/Dockerfile.runner -t $(RUNNER_IMG) . ; \
	else echo "✅  $(RUNNER_IMG) already present — skipping build"; fi
	@if ! docker image inspect $(SERVER_IMG) >/dev/null 2>&1 ; then \
		echo "🔨  Building $(SERVER_IMG)..."; \
		docker build -f tests/e2e_dind/Dockerfile.server -t $(SERVER_IMG) . ; \
	else echo "✅  $(SERVER_IMG) already present — skipping build"; fi

lint:
	@echo "Running linting and static analysis..."
	ruff check .
	ruff format . --check
	mypy --install-types --non-interactive mcp_the_force

test:
	@echo "Running fast unit tests..."
	$(PYTEST) tests/unit -q -m $(FAST_UNIT_MARKER) --tb=short

test-unit:
	@echo "Running all unit tests with coverage..."
	$(PYTEST) tests/unit -v --cov=mcp_the_force --cov-report=xml --cov-report=term

test-integration:
	@echo "Running integration tests with mock adapters..."
	MCP_ADAPTER_MOCK=1 $(PYTEST) tests/internal -v --tb=short
	MCP_ADAPTER_MOCK=1 $(PYTEST) tests/integration_mcp -v --tb=short

test-all: test-unit test-integration e2e
	@echo "✓ All tests passed!"

e2e-setup:
	@echo "Testing Docker-in-Docker Claude setup..."
	@# Check for Google Cloud credentials (ADC pattern)
	@ADC_PATH="$(PWD)/.gcp/adc-credentials.json"; \
	GLOBAL_ADC_PATH="$$HOME/.config/gcloud/application_default_credentials.json"; \
	if [ -f "$$ADC_PATH" ]; then \
		echo "Found project-local ADC at $$ADC_PATH"; \
	elif [ -f "$$GLOBAL_ADC_PATH" ]; then \
		ADC_PATH="$$GLOBAL_ADC_PATH"; \
		echo "Using global ADC credentials"; \
	else \
		echo "Error: No Google Cloud credentials found"; \
		echo "Run 'mcp-config setup-adc' or 'gcloud auth application-default login'"; \
		exit 1; \
	fi; \
	docker build -f tests/e2e_dind/Dockerfile.runner -t the-force-e2e-runner .; \
	docker build -f tests/e2e_dind/Dockerfile.server -t the-force-e2e-server .; \
	echo "Testing Claude MCP configuration in parallel..."; \
	( \
		for scenario in smoke history attachments cross_model failures stable_list; do \
			( \
				echo "Starting setup test: $$scenario"; \
				docker run --rm \
					--name e2e-test-$$scenario \
					-v /var/run/docker.sock:/var/run/docker.sock \
					-v "$$ADC_PATH:/home/claude/.config/gcloud/application_default_credentials.json:ro" \
					-w /host-project \
					-e OPENAI_API_KEY="$${OPENAI_API_KEY}" \
					-e ANTHROPIC_API_KEY="$${ANTHROPIC_API_KEY}" \
					-e XAI_API_KEY="$${XAI_API_KEY}" \
					-e VERTEX_PROJECT="$${VERTEX_PROJECT}" \
					-e VERTEX_LOCATION="$${VERTEX_LOCATION:-us-central1}" \
					-e GOOGLE_APPLICATION_CREDENTIALS="/home/claude/.config/gcloud/application_default_credentials.json" \
					--entrypoint=/bin/bash \
					the-force-e2e-runner -c " \
						echo '=== Testing $$scenario ===' && \
						gosu claude claude mcp add-json the-force '{ \
							\"command\": \"mcp-the-force\", \
							\"args\": [], \
							\"env\": { \
								\"OPENAI_API_KEY\": \"$$OPENAI_API_KEY\", \
								\"ANTHROPIC_API_KEY\": \"$$ANTHROPIC_API_KEY\", \
								\"VERTEX_PROJECT\": \"$$VERTEX_PROJECT\", \
								\"VERTEX_LOCATION\": \"$$VERTEX_LOCATION\", \
								\"GOOGLE_APPLICATION_CREDENTIALS\": \"/home/claude/.config/gcloud/application_default_credentials.json\", \
								\"LOG_LEVEL\": \"ERROR\", \
								\"CI_E2E\": \"1\", \
								\"PYTHONPATH\": \"/host-project\" \
							}, \
							\"timeout\": 60000, \
							\"description\": \"MCP The-Force server\" \
						}' && \
						echo 'MCP server configured for $$scenario' && \
						gosu claude claude mcp list && \
						echo '✓ $$scenario setup complete' \
					" \
					&& echo "✓ $$scenario SETUP OK" \
					|| echo "✗ $$scenario SETUP FAILED" \
			) & \
		done; \
		wait \
	); \
	echo "✓ All Claude MCP setups completed!"

e2e:
	@echo "Running Docker-in-Docker e2e tests..."
	@# Check for Google Cloud credentials (ADC pattern) and export image variables
	@export RUNNER_IMG=$(RUNNER_IMG) SERVER_IMG=$(SERVER_IMG); \
	ADC_PATH="$(PWD)/.gcp/adc-credentials.json"; \
	GLOBAL_ADC_PATH="$$HOME/.config/gcloud/application_default_credentials.json"; \
	if [ -f "$$ADC_PATH" ]; then \
		echo "Found project-local ADC at $$ADC_PATH"; \
	elif [ -f "$$GLOBAL_ADC_PATH" ]; then \
		ADC_PATH="$$GLOBAL_ADC_PATH"; \
		echo "Using global ADC credentials"; \
	else \
		echo "Error: No Google Cloud credentials found"; \
		echo "Run 'mcp-config setup-adc' or 'gcloud auth application-default login'"; \
		exit 1; \
	fi; \
	$(MAKE) build-e2e-images; \
	if [ -n "$(TEST)" ]; then \
		echo "Running specific e2e test: $(TEST)"; \
		TEST_NAME=$$(basename $(TEST) .py); \
		VOL="e2e-tmp-$$TEST_NAME-$$$$"; \
		docker volume create "$$VOL" >/dev/null; \
		docker run --rm \
			--name "e2e-test-$$TEST_NAME-$$$$" \
			-v /var/run/docker.sock:/var/run/docker.sock \
			-v "$$VOL":/tmp \
			-v "$$ADC_PATH:/home/claude/.config/gcloud/application_default_credentials.json:ro" \
			-w /host-project/tests/e2e_dind \
			-e OPENAI_API_KEY="$${OPENAI_API_KEY}" \
			-e ANTHROPIC_API_KEY="$${ANTHROPIC_API_KEY}" \
			-e XAI_API_KEY="$${XAI_API_KEY}" \
			-e VERTEX_PROJECT="$${VERTEX_PROJECT}" \
			-e VERTEX_LOCATION="$${VERTEX_LOCATION:-us-central1}" \
			-e GOOGLE_APPLICATION_CREDENTIALS="/home/claude/.config/gcloud/application_default_credentials.json" \
			-e SHARED_TMP_VOLUME="$$VOL" \
			-e RUNNER_IMG="$(RUNNER_IMG)" \
			-e SERVER_IMG="$(SERVER_IMG)" \
			$(RUNNER_IMG) $(TEST) -v -s --tb=short; \
		EXIT_CODE=$$?; \
		docker volume rm "$$VOL" >/dev/null 2>&1 || true; \
		exit $$EXIT_CODE; \
	else \
		echo "Running all e2e scenarios in parallel..."; \
		( \
			for scenario in smoke attachments stable_list priority_context session_management environment; do \
				( \
					echo "[$$scenario] Starting at $$(date)"; \
					VOL="e2e-tmp-$$scenario-$$$$"; \
					docker volume create "$$VOL" >/dev/null; \
					docker run --rm \
						--name "e2e-test-$$scenario-$$$$" \
						-v /var/run/docker.sock:/var/run/docker.sock \
						-v "$$VOL":/tmp \
						-v "$$ADC_PATH:/home/claude/.config/gcloud/application_default_credentials.json:ro" \
						-w /host-project/tests/e2e_dind \
						-e OPENAI_API_KEY="$${OPENAI_API_KEY}" \
						-e ANTHROPIC_API_KEY="$${ANTHROPIC_API_KEY}" \
						-e XAI_API_KEY="$${XAI_API_KEY}" \
						-e VERTEX_PROJECT="$${VERTEX_PROJECT}" \
						-e VERTEX_LOCATION="$${VERTEX_LOCATION:-us-central1}" \
						-e GOOGLE_APPLICATION_CREDENTIALS="/home/claude/.config/gcloud/application_default_credentials.json" \
						-e SHARED_TMP_VOLUME="$$VOL" \
						-e RUNNER_IMG="$(RUNNER_IMG)" \
						-e SERVER_IMG="$(SERVER_IMG)" \
						$(RUNNER_IMG) scenarios/test_$$scenario.py -v --tb=short; \
					EXIT_CODE=$$?; \
					docker volume rm "$$VOL" >/dev/null 2>&1 || true; \
					if [ $$EXIT_CODE -eq 0 ]; then \
						echo "[$$scenario] ✓ PASSED at $$(date)"; \
					else \
						echo "[$$scenario] ✗ FAILED at $$(date)"; \
					fi \
				) & \
			done; \
			echo "All scenarios launched, waiting for completion..."; \
			wait \
		); \
		echo "✓ All e2e scenarios completed!"; \
	fi

ci: lint test-unit test-integration
	@echo "✓ Main CI checks passed!"
	@echo "Note: E2E tests should run in a separate CI job."

clean:
	@echo "Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache .coverage coverage.xml .mypy_cache
	rm -rf htmlcov

backup:
	@echo "Backing up SQLite databases..."
	@scripts/backup_databases.sh
	@echo "✓ Clean complete!"

clean-e2e:
	@echo "Cleaning up E2E Docker resources..."
	@# Remove E2E Docker images
	docker rmi -f the-force-e2e-runner the-force-e2e-server 2>/dev/null || true
	@# Remove E2E volumes (e2e-tmp-*)
	docker volume ls --format '{{.Name}}' | grep '^e2e-tmp-' | xargs -r docker volume rm 2>/dev/null || true
	@# Remove E2E networks (compose-e2e_*)
	docker network ls --format '{{.Name}}' | grep '^compose-e2e_' | xargs -r docker network rm 2>/dev/null || true
	@# Remove temporary compose directories
	rm -rf /tmp/compose-e2e-* 2>/dev/null || true
	@# Remove any dangling E2E containers (shouldn't be any with --rm, but just in case)
	docker ps -a --format '{{.Names}}' | grep '^e2e-test-' | xargs -r docker rm -f 2>/dev/null || true
	@echo "✓ E2E cleanup complete!"