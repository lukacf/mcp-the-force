# Pre-Release Cleanup Plan

This document outlines the final cleanup tasks required before making the MCP The-Force repository public.

## ✅ Completed Tasks

### 1. Fixed Stable List Context Duplication Bug
- **Issue**: Stable list was only saved when files overflowed to vector store
- **Impact**: Entire codebase was re-sent on every call, causing token limit errors
- **Fix**: Always save stable list on first call to establish baseline
- **Files Modified**: 
  - `mcp_the_force/utils/context_builder.py` - Fixed the logic
  - `tests/unit/test_stable_list_regression.py` - Added regression tests

## ✅ Completed Critical Tasks

### 1. Fix Makefile Hardcoded Credentials Path
**Issue**: Makefile contains hardcoded path to developer-specific credentials
```makefile
PROJECT_CREDS_PATH="$(PWD)/.gcloud/king_credentials.json"
```

**Fix**: Update `Makefile` to use project-local ADC pattern:
```makefile
# Get ADC path from standard location
ADC_PATH="$(PWD)/.gcp/adc-credentials.json"
if [ -f "$$ADC_PATH" ]; then
    echo "Found project-local ADC at $$ADC_PATH"
elif [ -f "$$HOME/.config/gcloud/application_default_credentials.json" ]; then
    ADC_PATH="$$HOME/.config/gcloud/application_default_credentials.json"
    echo "Using global ADC credentials"
else
    echo "Error: No Google Cloud credentials found"
    echo "Run 'mcp-config setup-adc' or 'gcloud auth application-default login'"
    exit 1
fi
```

**Files to modify**:
- `Makefile` - Update both `e2e` and `e2e-setup` targets

## ✅ Completed High Priority Tasks

### 2. Delete Obsolete Code Files
**Files to delete**:
```bash
rm mcp_the_force/adapters/openai/cancel_aware_flow.py
rm mcp_the_force/patch_cancellation_handler.py
```

### 3. Delete Root-Level Debug Scripts
**Files to delete**:
```bash
rm debug_all_sessions.py
rm debug_describe_gemini.py
rm debug_session.py
rm restore_session.py
```

### 4. Delete Utility Scripts (except openai_cleanup_manager.py)
**Files to delete**:
```bash
rm utils/check_files_vs_relationship.py
rm utils/check_vs_count.py
# Keep: utils/openai_cleanup_manager.py
```

## ✅ Completed Medium Priority Tasks

### 5. Add Backup Configuration to Settings System

**Add to `mcp_the_force/config.py`**:
```python
class BackupConfig(BaseModel):
    """Configuration for backup scripts."""
    path: str = Field(
        default_factory=lambda: str(Path.home() / ".mcp_backups"),
        description="Directory for database backups"
    )

class Settings(BaseSettings):
    # ... existing fields ...
    backup: BackupConfig = Field(default_factory=BackupConfig)
```

### 6. Update Backup Script to Use Config System

**Modify `scripts/backup_databases.sh`**:
```bash
# Get backup directory from config, with fallback
BACKUP_DIR_FROM_CONFIG=$(mcp-config show backup.path 2>/dev/null)
BACKUP_DIR="${BACKUP_DIR_FROM_CONFIG:-$HOME/.mcp_backups}"
```

## 📋 Execution Order

1. **First**: Fix Makefile credentials (critical blocker)
2. **Second**: Delete all obsolete files (clean up codebase)
3. **Third**: Add backup config and update script (enhancement)

## 🧪 Testing After Cleanup

1. **Test E2E setup**: 
   ```bash
   make e2e-setup
   ```

2. **Test stable list fix**:
   - Create a session with large context
   - Make multiple calls with same session_id
   - Verify only changed files are sent

3. **Test backup script**:
   ```bash
   ./scripts/backup_databases.sh
   ```

## 📝 Documentation Updates Needed

After cleanup, update:
1. `README.md` - Ensure ADC setup instructions match new Makefile
2. `CONTRIBUTING.md` - Document E2E test setup without hardcoded paths
3. Remove references to deleted files from any documentation

## ✅ Definition of Done

- [x] All files listed for deletion have been removed
- [x] Makefile uses standard ADC discovery
- [x] Backup configuration integrated with settings
- [x] All tests pass (`make test`, `make test-unit`, `make test-integration`)
- [ ] E2E tests can be run by any developer with proper setup (needs verification)
- [x] No hardcoded paths remain in the codebase
- [ ] Documentation updated to reflect changes (README.md, CONTRIBUTING.md)