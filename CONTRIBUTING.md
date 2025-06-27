# Contributing to MCP Second-Brain

Thank you for your interest in contributing to MCP Second-Brain! This guide will help you set up your development environment and ensure your contributions meet our quality standards.

## Development Setup

### Prerequisites

- Python 3.10, 3.11, or 3.12
- [uv](https://github.com/astral-sh/uv) package manager
- Git

### Initial Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/luka-cf/mcp-second-brain.git
   cd mcp-second-brain
   ```

2. Set up the development environment:
   ```bash
   make dev
   ```
   This installs all dependencies using the frozen lockfile to ensure consistency.

3. Install pre-commit hooks:
   ```bash
   make install-hooks
   ```

## Testing Strategy

We maintain several test suites to ensure code quality:

### Unit Tests
Fast tests that run on every commit:
```bash
make test         # Fast unit tests only
make test-unit    # All unit tests with coverage
```

### Integration Tests
Tests that verify interaction between components:
```bash
make test-integration
```

### Multi-Python Testing
Test across all supported Python versions:
```bash
make test-matrix
```

### Full Test Suite
Run all tests (unit + integration + e2e):
```bash
make test-all
```

## Environment Consistency

To ensure your local environment matches CI/CD:

1. **Always use the frozen lockfile**:
   ```bash
   uv sync --frozen --all-extras
   ```

2. **Test with tox** before pushing:
   ```bash
   tox -e py311  # Test with specific Python version
   tox           # Test with all Python versions
   ```

3. **Use the same Python version as CI** (3.11 by default):
   ```bash
   python --version  # Should show Python 3.11.x
   ```

## Code Style

- We use `ruff` for linting and formatting
- Type hints are enforced with `mypy`
- Run linters before committing:
  ```bash
  make lint
  ```

## Making Changes

1. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and test locally

3. Ensure all tests pass:
   ```bash
   make ci  # Runs lint + unit + integration tests
   ```

4. Commit with a descriptive message

5. Push and create a pull request

## Troubleshooting

### CI/CD Failures

If tests pass locally but fail in CI:

1. **Check Python version**:
   CI uses Python 3.11 by default. Test with:
   ```bash
   tox -e py311
   ```

2. **Check for missing dependencies**:
   Ensure you're using the frozen lockfile:
   ```bash
   uv sync --frozen --extra test
   ```

3. **Environment differences**:
   Review the CI logs for environment diagnostics output

4. **Emoji/Unicode issues**:
   CI runs on Linux. Test locally with:
   ```bash
   LANG=C pytest tests/unit
   ```

### Common Issues

- **SQLite files in git**: Add `*.sqlite3*` files to `.gitignore`
- **Click/Typer version mismatches**: Use frozen dependencies
- **Missing API keys in tests**: Tests should mock external services

## Questions?

If you have questions or need help, please:
1. Check existing issues and pull requests
2. Review the [README](README.md) and documentation
3. Open an issue with a clear description

Thank you for contributing!