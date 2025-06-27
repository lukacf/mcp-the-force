.PHONY: help dev lint test test-all test-unit test-integration test-e2e test-matrix ci install-hooks clean

help:
	@echo "Available targets:"
	@echo "  make dev           - Set up development environment with frozen deps"
	@echo "  make install-hooks - Install pre-commit hooks"
	@echo "  make lint          - Run ruff and mypy"
	@echo "  make test          - Run fast unit tests only"
	@echo "  make test-all      - Run all tests (unit + integration + e2e)"
	@echo "  make test-unit     - Run all unit tests"
	@echo "  make test-integration - Run integration tests"
	@echo "  make test-e2e      - Run e2e tests (requires Docker)"
	@echo "  make test-matrix   - Run tests across Python versions with tox"
	@echo "  make ci            - Run full CI suite locally"
	@echo "  make clean         - Clean up generated files"

dev:
	@echo "Setting up development environment..."
	@command -v uv >/dev/null 2>&1 || (echo "Installing uv..." && pip install uv)
	uv sync --frozen --all-extras
	@echo "✓ Development environment ready!"

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
	@echo "Running e2e tests (requires Docker)..."
	cd tests/e2e && docker-compose up --build --abort-on-container-exit --exit-code-from test-runner

test-matrix:
	@echo "Running tests across Python versions..."
	@command -v tox >/dev/null 2>&1 || (echo "Installing tox..." && pip install tox)
	tox

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