"""Stable constants for SQLBuild docs reference generation."""

from pathlib import Path

DEFAULT_DOCS_ROOT: Path = Path(__file__).resolve().parents[2] / "website/src/content/docs/docs"
DEFAULT_OUTPUT_DIR: Path = Path("src/sqlbuild/.agents/skills/sqlbuild/references/docs")
SITE_BASE_URL: str = "https://sqlbuild.com"
DOCS_BASE_URL: str = f"{SITE_BASE_URL}/docs"
DOCS_SLUG: str = "docs"
DOCS_URL_PATH: str = f"/{DOCS_SLUG}"
INDEX_PAGE: str = "index"
COMPONENT_TAG_END: str = ">"
GENERATED_MARKER: str = "<!-- generated-by: sqlbuild skills -->"
INDEX_FILENAME: str = "CONTENTS.md"
FRONTMATTER_DELIMITER: str = "---"
TABLE_OF_CONTENTS_MIN_LINES: int = 100
UNGROUPED_LABEL: str = "Other pages"
