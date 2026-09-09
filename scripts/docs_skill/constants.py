"""Stable constants for SQLBuild docs skill generation."""

import tempfile
from pathlib import Path

DEFAULT_REPO_URL: str = "https://github.com/chio-labs/sqlbuild-docs"
DEFAULT_CLONE_DIR: Path = Path(tempfile.gettempdir()) / "sqlbuild-docs-skill-source"
DEFAULT_OUTPUT_PATH: Path = Path("src/sqlbuild/.agents/skills/sqlbuild/SKILL.md")
GENERATED_MARKER: str = "<!-- generated-by: sqlbuild skills -->"
SKILL_DESCRIPTION: str = (
    "ALWAYS load this skill when doing ANY SQLBuild work. This includes models, tests, audits, "
    "scenarios, configuration, CLI behavior, adapters, dependencies, documentation, and related "
    "code."
)
SKILL_FRONTMATTER: str = f"""---
name: sqlbuild
description: {SKILL_DESCRIPTION}
---"""
INTRODUCTION_PAGE_NAME: str = "index"
FRONTMATTER_DELIMITER: str = "---"
