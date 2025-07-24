# Project Rename Plan: mcp-second-brain → mcp-the-force

This document outlines the complete plan for renaming the project from `mcp-second-brain` to `mcp-the-force`.

## Overview

The rename involves changing:
- Package name from `mcp_second_brain` to `mcp_the_force`
- Repository name from `mcp-second-brain` to `mcp-the-force`
- All references throughout the codebase, documentation, and configuration

## Phase 1: Code and File Changes

### 1.1 Automated Rename Script

Create a Python script that performs the following operations:

```python
# rename_project.py
import os
import re
import shutil
from pathlib import Path

def rename_project(dry_run=False):
    # Step 1: Rename directories
    if not dry_run:
        if os.path.exists('mcp_second_brain'):
            shutil.move('mcp_second_brain', 'mcp_the_force')
        
        if os.path.exists('mcp_second_brain.egg-info'):
            shutil.move('mcp_second_brain.egg-info', 'mcp_the_force.egg-info')
    
    # Step 2: Update file contents
    # IMPORTANT: Order matters - most specific to least specific
    replacements = [
        (r'\bmcp_second_brain\b', 'mcp_the_force'),
        (r'\bmcp-second-brain\b', 'mcp-the-force'),
        (r'MCP Second-Brain', 'MCP The-Force'),
        (r'MCP Second Brain', 'MCP The Force'),
        (r'Second Brain', 'The Force'),  # Apply last, with caution
    ]
    
    # Walk through all files and apply replacements
    for path in Path('.').rglob('*'):
        if path.is_file() and should_process(path):
            if dry_run:
                print_planned_changes(path, replacements)
            else:
                update_file_content(path, replacements)
```

### 1.2 Files Requiring Special Attention

#### Package Configuration
- **`pyproject.toml`**:
  ```toml
  # Change:
  name = "mcp_second_brain" → "mcp_the_force"
  [project.scripts]
  mcp-second-brain = "mcp_second_brain.server:main" → mcp-the-force = "mcp_the_force.server:main"
  mcp-config = "mcp_second_brain.cli.config_cli:main" → mcp-config = "mcp_the_force.cli.config_cli:main"
  [tool.setuptools]
  packages = ["mcp_second_brain"] → ["mcp_the_force"]
  [tool.coverage.run]
  source = ["mcp_second_brain"] → ["mcp_the_force"]
  [tool.mypy.overrides]
  module = "mcp_second_brain.tools.definitions" → "mcp_the_force.tools.definitions"
  ```

#### Build System
- **`Makefile`**:
  - Update mypy target: `mcp_second_brain` → `mcp_the_force`
  - Update pytest coverage: `--cov=mcp_second_brain` → `--cov=mcp_the_force`

#### Git Configuration
- **`.pre-commit-config.yaml`**:
  - Update file filter: `files: ^mcp_second_brain/` → `files: ^mcp_the_force/`

- **`.repo_ignore`**:
  - Update: `mcp_second_brain.egg-info/` → `mcp_the_force.egg-info/`

#### GitHub Actions
- **`.github/workflows/e2e.yml`**:
  - Path filter: `mcp_second_brain/**` → `mcp_the_force/**`
  - Artifact name: `mcp-second-brain-debug.log` → `mcp-the-force-debug.log`

### 1.3 Python Code Updates

#### Import Statements
All files with imports need updating:
```python
# Before:
from mcp_second_brain.tools import executor
import mcp_second_brain.config

# After:
from mcp_the_force.tools import executor
import mcp_the_force.config
```

#### String Literals
- **`mcp_second_brain/__init__.py`**:
  ```python
  __version__ = version("mcp_second_brain") → version("mcp_the_force")
  ```

- **`mcp_second_brain/server.py`**:
  ```python
  mcp = FastMCP("mcp-second-brain") → FastMCP("mcp-the-force")
  ```

- **`mcp_second_brain/logging/setup.py`**:
  ```python
  logging.getLogger("mcp_second_brain") → logging.getLogger("mcp_the_force")
  os.getenv("LOKI_APP_TAG", "mcp-second-brain") → os.getenv("LOKI_APP_TAG", "mcp-the-force")
  ```

### 1.4 Scripts and Shell Files

- **`scripts/install-memory-hook.sh`**:
  ```bash
  python -m mcp_second_brain.memory.commit → python -m mcp_the_force.memory.commit
  ```

- **`scripts/create-gcp-service-account.sh`**:
  ```bash
  SERVICE_ACCOUNT_NAME="mcp-second-brain-e2e" → "mcp-the-force-e2e"
  --display-name="MCP Second Brain E2E Testing" → "MCP The Force E2E Testing"
  --description="Service account for MCP Second Brain E2E tests" → "Service account for MCP The Force E2E tests"
  ```

### 1.5 Documentation Updates

All documentation files need comprehensive search and replace:
- `README.md`
- `CLAUDE.md` (extensive references to "Second Brain")
- `CONTRIBUTING.md`
- All files in `docs/`
- `tests/e2e_dind/README.md`

Special attention for CLAUDE.md as it contains conceptual references to "Second Brain" that need context-aware replacement.

### 1.6 Docker and E2E Environment

- **`docker-compose.yaml`**:
  - Network name: `mcp-network` → `the-force-network`
  - Volume name: `mcp-logs-data` → `the-force-logs-data`

- **`Makefile`** (Docker image names):
  - `mcp-e2e-runner` → `the-force-e2e-runner`
  - `mcp-e2e-server` → `the-force-e2e-server`

- **`tests/e2e_dind/Dockerfile.runner` & `Dockerfile.server`**:
  - Update any `COPY mcp_second_brain` directives
  - Update image names in build commands

- **`tests/e2e_dind/compose/stack.yml`**:
  - Update hardcoded image names: `mcp-e2e-runner:latest` → `the-force-e2e-runner:latest`
  - Update service names if applicable

- **E2E Test Scenarios** (`tests/e2e_dind/scenarios/`):
  - Update all tool invocations: `claude("Use second-brain ...")` → `claude("Use the-force ...")`

### 1.7 Utility Scripts and Paths

- **`utils/openai_cleanup_manager.py`**:
  ```python
  cache_dir = home / ".cache" / "mcp-second-brain" → home / ".cache" / "mcp-the-force"
  ```

- **`mcp_second_brain/utils/debug_logger.py`**:
  ```python
  debug_dir = "~/.mcp_debug" → "~/.the_force_debug"
  ```

## Phase 2: Testing and Validation

### 2.1 Pre-Migration Testing

1. Create feature branch:
   ```bash
   git checkout -b rename-to-the-force
   ```

2. Run the rename script in dry-run mode first:
   ```bash
   python rename_project.py --dry-run > rename_changes.txt
   # Review the proposed changes carefully
   ```

3. Run the actual rename:
   ```bash
   python rename_project.py
   ```

3. Clean and rebuild:
   ```bash
   make clean
   rm -f uv.lock
   uv pip install -e ".[dev]"
   ```

4. Run full test suite:
   ```bash
   make ci
   make e2e  # Critical for Docker environment validation
   ```

5. Review all changes:
   ```bash
   git diff --stat  # Summary of changes
   git diff         # Detailed review
   ```

### 2.2 Validation Checklist

- [ ] All imports resolve correctly
- [ ] CLI command `mcp-the-force` works
- [ ] `mcp-config` command still works
- [ ] All tests pass
- [ ] Documentation is coherent
- [ ] No references to old name remain (use grep to verify)

## Phase 3: GitHub Repository Migration

### 3.1 Repository Rename

1. On GitHub.com:
   - Navigate to Settings → General
   - Change repository name to `mcp-the-force`
   - GitHub automatically creates redirects

2. Update local remotes:
   ```bash
   git remote set-url origin https://github.com/lukacf/mcp-the-force.git
   ```

### 3.2 Post-Rename Tasks

- Update any webhooks that don't auto-update
- Verify GitHub Actions still trigger
- Verify the new URL works correctly

## Phase 4: Deployment and Communication

### 4.1 Merge and Deploy

1. Create PR from rename branch
2. Ensure CI passes
3. Merge to main
4. Tag the commit for reference: `git tag pre-force-rename`

### 4.2 Documentation Updates

Update all references with:
- New repository URL
- New package name
- New CLI command
- Update local clone configuration

### 4.3 External Updates

- Update any deployment scripts
- Update documentation wikis
- Update Claude Desktop configuration examples
- Update any blog posts or external references

## Phase 5: Cleanup and Monitoring

### 5.1 Immediate Monitoring

- Watch GitHub Actions for any failures
- Test all functionality thoroughly
- Check that redirects work properly

### 5.2 Long-term Maintenance

- Keep note of the rename date for future reference
- Document any issues that arise
- Update any missed references as discovered

## Rollback Plan

If critical issues arise:

1. **Before GitHub rename**: Simply abandon the branch
2. **After GitHub rename**: Rename back on GitHub (instant)
3. **After merge**: Create a revert PR with the inverse replacements

## Verification Commands

Use these commands to verify the rename is complete:

```bash
# Check for any remaining old references
grep -r "second.brain" . --exclude-dir=.git --exclude-dir=.venv
grep -r "second_brain" . --exclude-dir=.git --exclude-dir=.venv

# Verify new package name works
python -c "import mcp_the_force; print(mcp_the_force.__version__)"

# Test CLI commands
mcp-the-force --help
mcp-config --help

# Run tests
make test

# Manual smoke test
mcp-the-force --help
python -c "from mcp_the_force.tools import list_tools; print(list_tools())"
```

## Script Safety Features

The rename script should include:
1. **Dry run mode** - Preview all changes without modifying files
2. **Word boundary matching** - Prevent partial replacements
3. **Error handling** - Abort on any filesystem errors
4. **Backup creation** - Optional backup before changes
5. **Verification step** - Confirm with user before proceeding

## Special Considerations

1. **Context-Aware Replacements**: The term "Second Brain" in CLAUDE.md has conceptual meaning. Some instances may need to remain or be replaced with appropriate "Force" metaphors.

2. **Thread Pool Names**: Consider if `thread_name_prefix="mcp-worker"` should become `thread_name_prefix="force-worker"` for consistency.

3. **Logger Hierarchies**: Ensure all child loggers follow the new naming pattern.

4. **External Integrations**: Any external services (Sentry, DataDog, etc.) referencing the old name need updates.

5. **PyPI Considerations**: If published to PyPI in the future, the old name cannot be reused.

6. **Database Migration**: Existing SQLite databases will be orphaned:
   - `.mcp_sessions.sqlite3`
   - `.mcp_logs.sqlite3`
   - `loiter_killer.db`
   - Delete these after successful migration

7. **Branch Protection Rules**: Update any GitHub branch protection rules that reference old paths.

8. **Open Pull Requests**: All open PRs will have massive conflicts and need rebasing after the rename.

## Success Criteria

The rename is complete when:
- [ ] All code references are updated
- [ ] All documentation is updated
- [ ] GitHub repository uses new name
- [ ] All tests pass
- [ ] Local repository is updated with new remote
- [ ] No broken links or references remain
- [ ] Claude Desktop integration works with new name