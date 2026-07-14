"""Stable constants for SQLBuild docs skill generation."""

import tempfile
from pathlib import Path

DEFAULT_REPO_URL: str = "https://github.com/chio-labs/sqlbuild-docs"
DEFAULT_CLONE_DIR: Path = Path(tempfile.gettempdir()) / "sqlbuild-docs-skill-source"
DEFAULT_OUTPUT_PATH: Path = Path("src/sqlbuild/.agents/skills/sqlbuild/SKILL.md")
GENERATED_MARKER: str = "<!-- generated-by: sqlbuild skills update -->"
SKILL_DESCRIPTION: str = (
    "Use when working with SQLBuild syntax, project structure, configuration, testing, "
    "adapters, CLI behavior, SQLBuild docs, or SQLBuild-related code."
)
SKILL_FRONTMATTER: str = f"""---
name: sqlbuild
description: {SKILL_DESCRIPTION}
---"""
INTRODUCTION_PAGE_NAME: str = "index"
FRONTMATTER_DELIMITER: str = "---"
