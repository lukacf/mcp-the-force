# Release Process

This document describes the complete release workflow from development to published release.

## Overview

```
Development → Update Changelog → Bump Version → Tag → Push → Automated Release
```

## Step-by-Step Process

### 1. Update CHANGELOG.md

Before releasing, update the changelog with all changes since the last release:

```markdown
## [1.2.0] - 2024-12-10
### Added
- New feature description

### Fixed
- Bug fix description
```

### 2. Bump Version in pyproject.toml

Update the version field to match your planned release:

```toml
[project]
version = "1.2.0"
```

### 3. Commit Version Bump

```bash
git add CHANGELOG.md pyproject.toml
git commit -m "chore: bump version to 1.2.0 and update changelog"
```

### 4. Create and Push Tag

```bash
git tag -a v1.2.0 -m "Release v1.2.0 - Brief description"
git push origin main
git push origin v1.2.0
```

### 5. Automated Release (GitHub Actions)

The release workflow automatically:
1. Verifies version consistency (tag matches pyproject.toml)
2. Extracts changelog section for this version
3. Creates GitHub Release with notes
4. Builds wheel and source distribution
5. Uploads artifacts to the release

## Version Numbering (SemVer)

- **MAJOR** (1.x.x): Breaking changes
- **MINOR** (x.1.x): New features, backwards compatible
- **PATCH** (x.x.1): Bug fixes, backwards compatible

## Troubleshooting

### Version Mismatch Error
```
Version mismatch: pyproject.toml has X but tag is Y
```
**Fix**: Ensure pyproject.toml version matches your tag (without 'v' prefix).

### Missing Changelog Section
The release will fall back to "Release {version}" if no matching changelog section found.

### Failed Release, Need to Retry

If the release workflow fails after creating a tag:

```bash
# Delete the tag locally and remotely
git tag -d v1.2.0
git push origin :refs/tags/v1.2.0

# Fix the issue, then re-create
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin v1.2.0
```

## Pre-Release Checklist

- [ ] All tests passing locally (`make ci`)
- [ ] CHANGELOG.md updated with all changes
- [ ] Version bumped in pyproject.toml
- [ ] No uncommitted changes (`git status`)
- [ ] On main branch with latest changes (`git pull`)
