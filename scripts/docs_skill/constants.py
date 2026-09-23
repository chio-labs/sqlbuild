"""Stable constants for SQLBuild docs reference generation."""

import tempfile
from pathlib import Path

DEFAULT_REPO_URL: str = "https://github.com/chio-labs/sqlbuild-docs"
DEFAULT_CLONE_DIR: Path = Path(tempfile.gettempdir()) / "sqlbuild-docs-skill-source"
DEFAULT_OUTPUT_DIR: Path = Path("src/sqlbuild/.agents/skills/sqlbuild/references/docs")
DOCS_BASE_URL: str = "https://docs.sqlbuild.com"
GENERATED_MARKER: str = "<!-- generated-by: sqlbuild skills -->"
INDEX_FILENAME: str = "CONTENTS.md"
FRONTMATTER_DELIMITER: str = "---"
TABLE_OF_CONTENTS_MIN_LINES: int = 100
UNGROUPED_LABEL: str = "Other pages"
