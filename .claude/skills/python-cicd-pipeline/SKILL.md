---
name: python-cicd-pipeline
description: |
  Set up a professional Python CI/CD pipeline with pre-commit hooks, GitHub Actions,
  automated releases, changelog management, and version control. This skill should be
  used when creating a new Python project that needs CI/CD, when adding CI/CD to an
  existing project, or when troubleshooting CI/CD pipeline issues. The pipeline follows
  the "Makefile as single source of truth" pattern for consistent local and CI testing.
---

# Python CI/CD Pipeline Setup

This skill provides a complete, production-ready CI/CD pipeline for Python projects featuring:

- **Progressive Testing**: Fast tests on commit, full tests on push
- **Makefile as Single Source of Truth**: Identical commands locally and in CI
- **Automated Releases**: Tag-triggered releases with changelog extraction
- **Version Consistency**: Automatic verification between tag and pyproject.toml

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Pre-commit    │     │  GitHub Actions │     │    Release      │
│     Hooks       │     │       CI        │     │    Workflow     │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ On commit:      │     │ On push/PR:     │     │ On v* tag:      │
│ - ruff lint     │     │ - make lint     │     │ - Verify version│
│ - ruff format   │     │ - make test-unit│     │ - Extract notes │
│ - mypy          │     │ - make test-int │     │ - Create release│
│ - gitleaks      │     │                 │     │ - Upload assets │
│ - make test     │     │                 │     │                 │
├─────────────────┤     └─────────────────┘     └─────────────────┘
│ On push:        │              │
│ - make test-unit│              ▼
│ - make test-int │     ┌─────────────────┐
└─────────────────┘     │    Makefile     │
         │              │ (Single Source) │
         └──────────────┤ - test          │
                        │ - test-unit     │
                        │ - test-integration
                        │ - lint          │
                        │ - ci            │
                        └─────────────────┘
```

## Quick Setup

To set up a complete pipeline for a project:

### 1. Prerequisites

Ensure the project has:
- `pyproject.toml` with `[project.optional-dependencies]` for `test` and `dev`
- A `tests/` directory with `tests/unit/` and optionally `tests/integration/`
- `uv.lock` tracked in git (required for CI caching)

### 2. Create Required Files

Create these files from the reference templates:

| File | Purpose |
|------|---------|
| `Makefile` | Test command definitions |
| `.pre-commit-config.yaml` | Git hooks configuration |
| `.github/workflows/ci.yml` | CI pipeline |
| `.github/workflows/release.yml` | Automated releases |
| `CHANGELOG.md` | Release notes |

### 3. Install Hooks

```bash
pip install pre-commit
make install-hooks
```

### 4. Track uv.lock

The `setup-uv` GitHub Action requires `uv.lock` for caching:

```bash
# Remove from .gitignore if present
# Then track it:
git add uv.lock
git commit -m "chore: track uv.lock for CI caching"
```

## Detailed Configuration

### Makefile Setup

The Makefile defines all test commands. Customize the `SOURCE_DIR` variable and test markers:

```makefile
SOURCE_DIR := your_package_name
FAST_UNIT_MARKER := "not slow and not e2e and not integration"
```

Key targets:
- `make test`: Fast unit tests for pre-commit (~seconds)
- `make test-unit`: Full unit tests with coverage
- `make test-integration`: Integration tests
- `make ci`: Full CI suite (lint + all tests)
- `make install-hooks`: Install git hooks

See `references/makefile-template.md` for the complete template.

### Pre-commit Configuration

The `.pre-commit-config.yaml` runs:

**On every commit** (fast, <15s):
- Ruff linting and formatting
- MyPy type checking
- Gitleaks secret detection
- Fast unit tests via `make test`

**On push only** (thorough):
- Full unit test suite via `make test-unit`
- Integration tests via `make test-integration`

Customize the `files:` pattern for mypy to match your source directory.

See `references/pre-commit-config.yaml` for the template.

### CI Workflow

The CI workflow (`.github/workflows/ci.yml`) runs on push/PR with three jobs:

1. **lint**: Ruff + MyPy static analysis
2. **unit-tests**: Full test suite with coverage upload
3. **integration-tests**: Integration tests (requires unit tests to pass first)
4. **all-tests-passed**: Gate job for branch protection

Key customizations:
- Set `PYTHON_VERSION` env variable
- Add secrets for integration tests
- Adjust branch patterns as needed

See `references/ci-workflow.yaml` for the template.

### Release Workflow

The release workflow (`.github/workflows/release.yml`) triggers on `v*` tags:

1. Extracts version from tag (e.g., `v1.2.0` → `1.2.0`)
2. Verifies version matches `pyproject.toml`
3. Extracts changelog section for this version
4. Creates GitHub Release with notes
5. Builds wheel and source distribution
6. Uploads artifacts to release

See `references/release-workflow.yaml` for the template.

### Changelog Format

Maintain a `CHANGELOG.md` with version sections that the release workflow extracts:

```markdown
# Changelog

## [1.2.0] - 2024-12-10
### Added
- New feature X

### Fixed
- Bug in Y
```

See `references/changelog-format.md` for detailed formatting guidelines.

### pyproject.toml Configuration

Ensure your `pyproject.toml` includes:

```toml
[project]
version = "1.0.0"  # Single source of truth

[project.optional-dependencies]
test = ["pytest>=7.4", "pytest-cov>=4.0", ...]
dev = ["ruff>=0.4", "mypy>=1.10", "pre-commit>=3.5"]

[tool.pytest.ini_options]
markers = [
    "slow: Tests that take more than 10 seconds",
    "integration: Integration tests",
]
```

See `references/pyproject-example.toml` for complete configuration.

## Release Process

To create a new release:

1. **Update changelog** with all changes since last release
2. **Bump version** in `pyproject.toml`
3. **Commit**: `git commit -m "chore: bump version to X.Y.Z"`
4. **Tag**: `git tag -a vX.Y.Z -m "Release vX.Y.Z - description"`
5. **Push**: `git push origin main && git push origin vX.Y.Z`

The release workflow handles the rest automatically.

See `references/release-process.md` for detailed instructions and troubleshooting.

## Troubleshooting

### Pre-commit hooks not running
```bash
pre-commit install
pre-commit install --hook-type pre-push
```

### CI fails with "No virtual environment found"
Ensure `uv pip install` uses `--system` flag in workflows.

### Release fails with version mismatch
Ensure `pyproject.toml` version matches tag (without 'v' prefix).

### uv.lock not found in CI
Track `uv.lock` in git (remove from `.gitignore` if present).

### Skip hooks temporarily
```bash
git commit --no-verify -m "message"
git push --no-verify
```

## Static Analysis (Linting & Type Checking)

Static analysis runs before tests catch issues without executing code.

| Tool | Purpose | Speed | When Run |
|------|---------|-------|----------|
| **Ruff** | Linting + formatting | <1s | Every commit |
| **MyPy** | Static type checking | 2-5s | Every commit |
| **Gitleaks** | Secret detection | <1s | Every commit |

### Ruff

Fast Python linter and formatter. Replaces flake8, isort, black, and pyupgrade.

```bash
ruff check .                 # Lint (find issues)
ruff check . --fix           # Lint and auto-fix
ruff format .                # Format code
ruff format . --check        # Check formatting without changing
```

Configure in `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP"]  # Rules to enable
ignore = ["E501"]  # Line length handled by formatter
```

### MyPy

Static type checker. Catches type errors before runtime.

```bash
mypy --install-types --non-interactive your_package/
```

Configure in `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true  # For untyped dependencies
```

### Gitleaks

Prevents secrets (API keys, passwords) from being committed.

- Scans staged changes for patterns matching secrets
- Blocks commit if secrets detected
- No configuration needed - works out of the box

### Pipeline Integration

Static analysis runs at multiple points:

1. **Pre-commit hook**: Ruff + MyPy + Gitleaks on every commit
2. **CI lint job**: `make lint` runs ruff check + ruff format --check + mypy
3. **Pre-push hook**: Same checks (redundant but catches amended commits)

The lint job runs in parallel with tests in CI - failures block merge.

## Test Categories and Policy

The pipeline uses three test categories with clear boundaries:

| Category | Speed | I/O | Dependencies | When Run |
|----------|-------|-----|--------------|----------|
| **Unit** | <100ms each | None | All mocked | Every commit |
| **Integration** | <1s each | Mocked | Real components, mocked external | Every push |
| **E2E** | Minutes | Real | Full system | Manual / Release |

### Unit Tests (`tests/unit/`)

Pure logic tests with no I/O. All dependencies mocked.

- **Purpose**: Verify individual functions/classes in isolation
- **Speed**: Must complete in <100ms per test, total suite <10s
- **Mocking**: Mock everything external (DB, APIs, file system)
- **Run**: `make test` (pre-commit), `make test-unit` (full with coverage)

```python
# Example: Unit test with mocked dependency
def test_calculate_total(mocker):
    mocker.patch('myapp.db.get_prices', return_value=[10, 20])
    assert calculate_total() == 30
```

### Integration Tests (`tests/integration/`)

Test component interactions with mocked external services.

- **Purpose**: Verify components work together correctly
- **Speed**: <1s per test, real component wiring but mocked I/O
- **Mocking**: Mock external APIs, use test databases/fixtures
- **Run**: `make test-integration` (pre-push, CI)

```python
# Example: Integration test with mock adapter
@pytest.fixture
def mock_api(mocker):
    return mocker.patch('myapp.api.client', MockAPIClient())

def test_user_workflow(mock_api, test_db):
    result = create_and_fetch_user("test@example.com")
    assert result.email == "test@example.com"
```

### E2E Tests (`tests/e2e/`)

Full system tests with real external services.

- **Purpose**: Verify the complete system works in production-like environment
- **Speed**: Minutes (real API calls, real databases)
- **Mocking**: None - real services, real credentials
- **Run**: `make e2e` (manual, pre-release, separate CI job)

```python
# Example: E2E test requiring real credentials
@pytest.mark.e2e
def test_full_checkout_flow(live_api, real_db):
    # This hits real APIs - only run manually or in release CI
    order = complete_checkout(cart_items=[...])
    assert order.status == "confirmed"
```

### Pytest Markers

Configure markers in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "unit: Pure logic tests, no I/O (<100ms)",
    "integration: Component tests with mocked I/O (<1s)",
    "e2e: End-to-end tests with real services",
    "slow: Tests exceeding normal time limits",
]
```

### Directory Structure

```
tests/
├── unit/              # Fast, isolated tests
│   ├── test_core.py
│   └── test_utils.py
├── integration/       # Component interaction tests
│   └── test_api.py
├── e2e/               # Full system tests (optional)
│   └── test_checkout.py
└── conftest.py        # Shared fixtures
```

## Resources

This skill includes reference templates in the `references/` directory:

### references/

- **pre-commit-config.yaml**: Pre-commit hooks configuration template
- **makefile-template.md**: Makefile with all standard targets
- **ci-workflow.yaml**: GitHub Actions CI pipeline
- **release-workflow.yaml**: Automated release workflow
- **changelog-format.md**: Changelog formatting guide
- **pyproject-example.toml**: Complete pyproject.toml configuration
- **release-process.md**: Step-by-step release instructions

To use: Read the relevant template, customize placeholders (marked with `{{PLACEHOLDER}}`), and save to your project.
