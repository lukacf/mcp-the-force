.PHONY: help lint test test-all test-unit test-integration test-e2e e2e-setup e2e ci install-hooks clean

help:
	@echo "Available targets:"
	@echo "  make install-hooks  - Install pre-commit hooks"
	@echo "  make lint          - Run ruff and mypy"
	@echo "  make test          - Run fast unit tests only"
	@echo "  make test-all      - Run all tests (unit + integration + e2e)"
	@echo "  make test-unit     - Run all unit tests"
	@echo "  make test-integration - Run integration tests"
	@echo "  make test-e2e      - Run e2e tests (legacy, deprecated)"
	@echo "  make e2e-setup     - Test Docker-in-Docker Claude MCP setup in parallel"
	@echo "  make e2e           - Run new Docker-in-Docker e2e tests"
	@echo "  make ci            - Run full CI suite locally"
	@echo "  make clean         - Clean up generated files"

install-hooks:
	@echo "Installing pre-commit hooks..."
	pre-commit install
	pre-commit install --hook-type pre-push
	@echo "✓ Pre-commit hooks installed!"
	@echo "  - Fast checks will run on every commit"
	@echo "  - Full unit tests will run on push (skip with --no-verify)"

lint:
	@echo "Running linting checks..."
	ruff check .
	mypy --install-types --non-interactive mcp_second_brain

test:
	@echo "Running fast unit tests..."
	pytest tests/unit -q -m "not slow and not e2e and not integration" --tb=short

test-all: test-unit test-integration test-e2e
	@echo "✓ All tests passed!"

test-unit:
	@echo "Running all unit tests..."
	pytest tests/unit -v --cov=mcp_second_brain --cov-report=term

test-integration:
	@echo "Running integration tests..."
	pytest tests/internal -v --tb=short
	pytest tests/integration_mcp -v -p no:asyncio --tb=short

test-e2e:
	@echo "Running legacy e2e tests (deprecated)..."
	@echo "Use 'make e2e' for new Docker-in-Docker tests"
	cd tests/e2e && docker-compose up --build --abort-on-container-exit --exit-code-from test-runner

e2e-setup:
	@echo "Testing Docker-in-Docker Claude setup..."
	@# Check for Google Cloud credentials like the old E2E system
	@PROJECT_CREDS_PATH="$(PWD)/.gcloud/king_credentials.json"; \
	GLOBAL_ADC_PATH="$$HOME/.config/gcloud/application_default_credentials.json"; \
	if [ -f "$$PROJECT_CREDS_PATH" ]; then \
		ADC_PATH="$$PROJECT_CREDS_PATH"; \
		echo "Found project-specific credentials at $$ADC_PATH"; \
	elif [ -f "$$GLOBAL_ADC_PATH" ]; then \
		ADC_PATH="$$GLOBAL_ADC_PATH"; \
		echo "Using global ADC credentials at $$ADC_PATH"; \
	else \
		echo "Error: No Google Cloud credentials found"; \
		echo "Run 'gcloud auth application-default login' first"; \
		exit 1; \
	fi; \
	docker build -f tests/e2e_dind/Dockerfile.runner -t mcp-e2e-runner .; \
	echo "Testing Claude MCP configuration in parallel..."; \
	( \
		for scenario in smoke memory attachments cross_model failures stable_list; do \
			( \
				echo "Starting setup test: $$scenario"; \
				docker run --rm \
					--name e2e-test-$$scenario \
					-v /var/run/docker.sock:/var/run/docker.sock \
					-v "$$ADC_PATH:/home/claude/.config/gcloud/application_default_credentials.json:ro" \
					-w /host-project \
					-e OPENAI_API_KEY="$${OPENAI_API_KEY}" \
					-e ANTHROPIC_API_KEY="$${ANTHROPIC_API_KEY}" \
					-e VERTEX_PROJECT="$${VERTEX_PROJECT:-mcp-test-project}" \
					-e VERTEX_LOCATION="$${VERTEX_LOCATION:-us-central1}" \
					-e GOOGLE_APPLICATION_CREDENTIALS="/home/claude/.config/gcloud/application_default_credentials.json" \
					--entrypoint=/bin/bash \
					mcp-e2e-runner -c " \
						echo '=== Testing $$scenario ===' && \
						gosu claude claude mcp add-json second-brain '{ \
							\"command\": \"mcp-second-brain\", \
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
							\"description\": \"MCP Second-Brain server\" \
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
	@# Check for Google Cloud credentials like the old E2E system
	@PROJECT_CREDS_PATH="$(PWD)/.gcloud/king_credentials.json"; \
	GLOBAL_ADC_PATH="$$HOME/.config/gcloud/application_default_credentials.json"; \
	if [ -f "$$PROJECT_CREDS_PATH" ]; then \
		ADC_PATH="$$PROJECT_CREDS_PATH"; \
		echo "Found project-specific credentials at $$ADC_PATH"; \
	elif [ -f "$$GLOBAL_ADC_PATH" ]; then \
		ADC_PATH="$$GLOBAL_ADC_PATH"; \
		echo "Using global ADC credentials at $$ADC_PATH"; \
	else \
		echo "Error: No Google Cloud credentials found"; \
		echo "Run 'gcloud auth application-default login' first"; \
		exit 1; \
	fi; \
	docker build -f tests/e2e_dind/Dockerfile.runner -t mcp-e2e-runner .; \
	echo "Running all e2e scenarios in parallel..."; \
	( \
		for scenario in smoke memory attachments cross_model failures stable_list; do \
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
					-e VERTEX_PROJECT="$${VERTEX_PROJECT:-mcp-test-project}" \
					-e VERTEX_LOCATION="$${VERTEX_LOCATION:-us-central1}" \
					-e GOOGLE_APPLICATION_CREDENTIALS="/home/claude/.config/gcloud/application_default_credentials.json" \
					-e SHARED_TMP_VOLUME="$$VOL" \
					mcp-e2e-runner scenarios/test_$$scenario.py -v --tb=short; \
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
	echo "✓ All e2e scenarios completed!"

ci: lint test-unit test-integration
	@echo "✓ CI checks passed locally!"
	@echo "Note: Full CI also runs on multiple Python versions and e2e tests"

clean:
	@echo "Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache .coverage coverage.xml .mypy_cache
	rm -rf htmlcov
	@echo "✓ Clean complete!"