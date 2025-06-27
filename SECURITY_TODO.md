# Security TODO Items

These security features are currently not implemented and are tracked for future development.
Tests for these features are marked with `@pytest.mark.xfail` to document the gaps.

## Priority 1 - Must Fix Before Public Release

### 1. Path Traversal Protection
**Issue**: The file gathering system does not validate that requested paths stay within project boundaries.
**Risk**: A malicious client could request files like `/etc/passwd` or `~/.ssh/private_key`
**Test**: `tests/unit/test_file_utils.py::TestPathTraversal::test_path_traversal_blocked`
**Fix**: Implement `_is_safe_path()` function in `mcp_second_brain/utils/fs.py` that:
- Resolves all paths to absolute paths
- Checks they are within the allowed project root
- Rejects any path that escapes the boundary

### 2. Automatic Secret Redaction in Logs
**Issue**: API keys and secrets could accidentally appear in logs
**Risk**: Sensitive credentials could be exposed in log files
**Test**: `tests/unit/test_logging.py::TestLoggingSecurity::test_automatic_secret_redaction`
**Fix**: Implement a logging filter that:
- Detects patterns like `sk-[alphanumeric]` (OpenAI keys)
- Redacts environment variable values ending in `_KEY` or `_SECRET`
- Replaces with `[REDACTED]` or similar
**Status**: Implemented as `SecretRedactionFilter` in `mcp_second_brain.utils.log_filter`

## Priority 2 - Important Enhancements

### 3. Gitignore Negation Patterns
**Issue**: Patterns like `!important.file` are not supported
**Risk**: Users may expect files to be included that are actually ignored
**Test**: `tests/unit/test_gitignore_edge_cases.py::test_negation_patterns`
**Fix**: Enhance `_is_ignored()` to properly handle negation patterns

## Implementation Notes

Before deploying to production or making the server publicly accessible:
1. Fix Priority 1 items
2. Add rate limiting to prevent DoS
3. Consider adding request size limits
4. Implement proper authentication if exposing over network

## Tracking

- [ ] Path traversal protection
- [x] Automatic log redaction
- [ ] Gitignore negation support
