# Changelog Format Guide

The changelog follows [Keep a Changelog](https://keepachangelog.com/) conventions with some simplifications for practical use.

## Structure

```markdown
# Changelog

## [Unreleased]
- Work in progress items go here during development

## [1.2.0] - 2024-12-10
### Added
- New feature X with description
- Another new capability

### Changed
- Modified behavior of Y
- Updated dependency versions

### Fixed
- Bug fix for issue Z
- Performance improvement for W

### Removed
- Deprecated feature Q

## [1.1.0] - 2024-11-15
...
```

## Section Types

| Section | Use When |
|---------|----------|
| **Added** | New features, capabilities, or files |
| **Changed** | Changes to existing functionality |
| **Deprecated** | Features marked for future removal |
| **Removed** | Features or files removed |
| **Fixed** | Bug fixes |
| **Security** | Security-related fixes |

## Simplified Format (Alternative)

For smaller projects, a simpler format without subsections:

```markdown
# Changelog

## 1.2.0
- Added new feature X with description
- Fixed bug in authentication flow
- Updated dependency Y to v2.0

## 1.1.0
- Initial feature implementation
```

## Best Practices

1. **Write for humans**: Describe what changed and why, not just what files
2. **Link to PRs/issues**: Reference `#123` for context
3. **Group related changes**: Keep similar changes together
4. **Be specific**: "Fixed null pointer in auth" > "Fixed bug"
5. **Update before release**: Add to changelog as you work, not at release time

## Release Workflow Integration

The release workflow extracts the section matching the tag version:
- Tag `v1.2.0` extracts `## [1.2.0]` or `## 1.2.0` section
- Content becomes the GitHub Release notes
- If no section found, falls back to "Release {version}"
