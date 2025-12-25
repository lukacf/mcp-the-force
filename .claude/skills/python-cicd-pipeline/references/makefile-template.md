# Makefile Template

The Makefile serves as the **single source of truth** for all test commands, ensuring consistency across local development, pre-commit hooks, and CI/CD.

## Template

```makefile
# Use .DEFAULT_GOAL to show help by default
.DEFAULT_GOAL := help

# Define variables to avoid repetition
PYTEST := pytest
SOURCE_DIR := {{SOURCE_DIR}}  # CUSTOMIZE: your source directory
FAST_UNIT_MARKER := "not slow and not e2e and not integration"

# Phony targets ensure these are always run
.PHONY: help install-hooks lint test test-unit test-integration ci clean

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Available targets:"
	@echo "  install-hooks    Install git pre-commit and pre-push hooks."
	@echo "  lint             Run static analysis (ruff, mypy)."
	@echo "  test             Run fast unit tests (for pre-commit)."
	@echo "  test-unit        Run the full unit test suite with coverage."
	@echo "  test-integration Run integration tests."
	@echo "  ci               Run the main CI suite (lint, unit, integration)."
	@echo "  clean            Remove temporary files and caches."

install-hooks:
	@echo "Installing pre-commit hooks..."
	pre-commit install
	pre-commit install --hook-type pre-push
	@echo "Pre-commit hooks installed!"
	@echo "  - Fast checks will run on every commit"
	@echo "  - Full unit tests will run on push (skip with --no-verify)"

lint:
	@echo "Running linting and static analysis..."
	ruff check .
	ruff format . --check
	mypy --install-types --non-interactive $(SOURCE_DIR)

test:
	@echo "Running fast unit tests..."
	$(PYTEST) tests/unit -q -m $(FAST_UNIT_MARKER) --tb=short

test-unit:
	@echo "Running all unit tests with coverage..."
	$(PYTEST) tests/unit -v --cov=$(SOURCE_DIR) --cov-report=xml --cov-report=term

test-integration:
	@echo "Running integration tests..."
	$(PYTEST) tests/integration -v --tb=short

ci: lint test-unit test-integration
	@echo "Main CI checks passed!"

clean:
	@echo "Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache .coverage coverage.xml .mypy_cache htmlcov
```

## Key Design Principles

1. **Single Source of Truth**: All test commands defined once in Makefile
2. **Progressive Testing**: Fast tests on commit, full tests on push
3. **CI Parity**: Local `make ci` mirrors GitHub Actions exactly
4. **Help by Default**: Running `make` without arguments shows usage
5. **Markers for Speed**: Use pytest markers to categorize test speed
