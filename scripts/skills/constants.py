"""Stable constants for skill generation tooling."""

from pathlib import Path

VIOLATION_CLASS_NAME: str = "Violation"
GENERATED_MARKER: str = "<!-- generated-by: make skills -->"
ELSE_BRANCH_KEY: str = "__else__"
SKILL_NAME: str = "sqlbuild-structure"
SKILL_DESCRIPTION: str = (
    "Use when modifying SQLBuild Python package structure, imports, boundaries, main/ "
    "entry modules, _helpers/, shared/, classes/, models.py, types.py, constants.py, "
    "exceptions.py, adapter/integration modules, or fixing make check structure convention "
    "violations SC001-SC068."
)
DEFAULT_STRUCTURE_RULES_PATH: Path = Path("scripts/structure/_helpers")
DEFAULT_STRUCTURE_SKILL_OUTPUT_PATH: Path = (
    Path.home() / ".config/opencode/skills/sqlbuild-structure/SKILL.md"
)
