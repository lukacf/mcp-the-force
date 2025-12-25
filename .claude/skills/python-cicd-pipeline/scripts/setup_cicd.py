#!/usr/bin/env python3
"""
Setup script for Python CI/CD Pipeline

This script initializes a CI/CD pipeline for a Python project by:
1. Creating necessary directories (.github/workflows/)
2. Generating configuration files from templates
3. Setting up pre-commit hooks

Usage:
    python setup_cicd.py --source-dir myproject --python-version 3.13

The script reads templates from the references/ directory and customizes them
based on the provided arguments.
"""

import argparse
import sys
from pathlib import Path


def get_skill_dir() -> Path:
    """Get the skill directory (parent of scripts/)."""
    return Path(__file__).parent.parent


def read_template(name: str) -> str:
    """Read a template file from references/."""
    template_path = get_skill_dir() / "references" / name
    if not template_path.exists():
        print(f"Error: Template not found: {template_path}")
        sys.exit(1)
    return template_path.read_text()


def customize_template(content: str, replacements: dict) -> str:
    """Replace placeholders in template content."""
    for placeholder, value in replacements.items():
        content = content.replace(f"{{{{{placeholder}}}}}", value)
    return content


def write_file(path: Path, content: str, dry_run: bool = False):
    """Write content to file, creating directories as needed."""
    if dry_run:
        print(f"Would create: {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"Created: {path}")


def create_makefile(project_dir: Path, source_dir: str, dry_run: bool = False):
    """Create Makefile from template."""
    template = read_template("makefile-template.md")

    # Extract the makefile content from the markdown
    lines = template.split("```makefile")[1].split("```")[0].strip()

    # Customize
    content = lines.replace("{{SOURCE_DIR}}", source_dir)

    write_file(project_dir / "Makefile", content, dry_run)


def create_pre_commit_config(project_dir: Path, source_dir: str, dry_run: bool = False):
    """Create .pre-commit-config.yaml from template."""
    content = read_template("pre-commit-config.yaml")
    content = customize_template(content, {"SOURCE_DIR": source_dir})
    write_file(project_dir / ".pre-commit-config.yaml", content, dry_run)


def create_ci_workflow(project_dir: Path, python_version: str, dry_run: bool = False):
    """Create .github/workflows/ci.yml from template."""
    content = read_template("ci-workflow.yaml")
    content = content.replace('"3.13"', f'"{python_version}"')
    write_file(project_dir / ".github" / "workflows" / "ci.yml", content, dry_run)


def create_release_workflow(
    project_dir: Path, python_version: str, dry_run: bool = False
):
    """Create .github/workflows/release.yml from template."""
    content = read_template("release-workflow.yaml")
    content = content.replace("'3.13'", f"'{python_version}'")
    write_file(project_dir / ".github" / "workflows" / "release.yml", content, dry_run)


def create_changelog(project_dir: Path, dry_run: bool = False):
    """Create initial CHANGELOG.md."""
    content = """# Changelog

## [Unreleased]

### Added
- Initial project setup

"""
    write_file(project_dir / "CHANGELOG.md", content, dry_run)


def create_test_directories(project_dir: Path, dry_run: bool = False):
    """Create test directory structure."""
    dirs = [
        project_dir / "tests" / "unit",
        project_dir / "tests" / "integration",
    ]

    for d in dirs:
        if dry_run:
            print(f"Would create directory: {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"Created directory: {d}")

    # Create empty conftest.py if it doesn't exist
    conftest = project_dir / "tests" / "conftest.py"
    if not conftest.exists():
        content = '''"""Pytest configuration and shared fixtures."""

import pytest
'''
        write_file(conftest, content, dry_run)


def main():
    parser = argparse.ArgumentParser(
        description="Set up CI/CD pipeline for a Python project"
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        required=True,
        help="Source directory name (e.g., 'myproject', 'src/myproject')",
    )
    parser.add_argument(
        "--python-version",
        type=str,
        default="3.13",
        help="Python version for CI (default: 3.13)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without creating files",
    )
    parser.add_argument(
        "--skip-makefile",
        action="store_true",
        help="Skip Makefile creation (if you already have one)",
    )
    parser.add_argument(
        "--skip-changelog",
        action="store_true",
        help="Skip CHANGELOG.md creation (if you already have one)",
    )

    args = parser.parse_args()

    project_dir = args.project_dir.resolve()

    print(f"Setting up CI/CD pipeline in: {project_dir}")
    print(f"Source directory: {args.source_dir}")
    print(f"Python version: {args.python_version}")
    if args.dry_run:
        print("(Dry run - no files will be created)")
    print()

    # Check for pyproject.toml
    if not (project_dir / "pyproject.toml").exists():
        print("Warning: No pyproject.toml found. You'll need to create one.")
        print("See references/pyproject-example.toml for a template.")
        print()

    # Create files
    if not args.skip_makefile:
        create_makefile(project_dir, args.source_dir, args.dry_run)

    create_pre_commit_config(project_dir, args.source_dir, args.dry_run)
    create_ci_workflow(project_dir, args.python_version, args.dry_run)
    create_release_workflow(project_dir, args.python_version, args.dry_run)

    if not args.skip_changelog and not (project_dir / "CHANGELOG.md").exists():
        create_changelog(project_dir, args.dry_run)

    create_test_directories(project_dir, args.dry_run)

    print()
    print("Setup complete! Next steps:")
    print("1. Review and customize the generated files")
    print("2. Install pre-commit: pip install pre-commit")
    print("3. Install hooks: make install-hooks")
    print("4. Ensure uv.lock is tracked in git (not in .gitignore)")
    print("5. Add test and dev dependencies to pyproject.toml")


if __name__ == "__main__":
    main()
