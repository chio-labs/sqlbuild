"""Constants for the lint and format layer."""

from __future__ import annotations

LINT_ENGINE_SQLBUILD: str = "sqlbuild"
LINT_ENGINE_SQRUFF: str = "sqruff"

VIOLATION_SEVERITY_FAULT: str = "fault"
VIOLATION_SEVERITY_WARNING: str = "warning"

HEADER_KIND_MODEL: str = "MODEL"
HEADER_KIND_SCENARIO: str = "SCENARIO"
HEADER_KIND_TEST: str = "TEST"
HEADER_KIND_AUDIT: str = "AUDIT"
HEADER_KIND_FUNCTION: str = "FUNCTION"
HEADER_KIND_ENUM: str = "ENUM"
HEADER_KIND_CONSTANT: str = "CONSTANT"

DSL_HEADER_KINDS: frozenset[str] = frozenset(
    {
        HEADER_KIND_MODEL,
        HEADER_KIND_SCENARIO,
        HEADER_KIND_TEST,
        HEADER_KIND_AUDIT,
        HEADER_KIND_FUNCTION,
        HEADER_KIND_ENUM,
        HEADER_KIND_CONSTANT,
    }
)

IDENTIFIER_SEPARATOR_CHARACTER: str = "_"

DESCRIPTION_HEADER_KINDS: frozenset[str] = frozenset({HEADER_KIND_MODEL, HEADER_KIND_SCENARIO})
DESCRIPTION_REQUIRED_HEADER_KINDS: frozenset[str] = frozenset({HEADER_KIND_MODEL})

DEFAULT_MAX_DESCRIPTION_LINES: int = 10
DEFAULT_SQRUFF_CONFIG_PATH: str = ".sqruff"

LINT_DIRECTORY_NAMES: tuple[str, ...] = (
    "models",
    "tests",
    "audits",
    "functions",
    "enums",
    "constants",
)

DEFAULT_SQRUFF_CONFIG_CONTENT: str = """\
[core]
dialect = "snowflake"
templater = "jinja"
"""

RULE_DESCRIPTION_PRESENT: str = "description-present"
RULE_DESCRIPTION_LENGTH: str = "description-length"
RULE_LEADING_COMMENT_DESCRIPTION: str = "leading-comment-description"
RULE_HEADER_WHITESPACE: str = "header-whitespace"
RULE_HEADER_PARSE: str = "header-parse"

PROJECT_CONFIG_FILENAME_KEY: str = "sqlbuild_project.toml"
LINT_SECTION_KEY: str = "lint"
SQRUFF_ENABLED_KEY: str = "sqruff"
SQRUFF_CONFIG_PATH_KEY: str = "sqruff_config"
MAX_DESCRIPTION_LINES_KEY: str = "max_description_lines"

ADAPTER_DIALECT_TRANSLATIONS: dict[str, str] = {
    "duckdb": "duckdb",
    "motherduck": "duckdb",
    "snowflake": "snowflake",
    "bigquery": "bigquery",
    "databricks": "databricks",
    "postgres": "postgres",
    "sqlserver": "tsql",
}
SQRUFF_CONFIG_SECTION: str = "core"
SQRUFF_CONFIG_DIALECT_KEY: str = "dialect"
ADAPTER_CONFIG_KEY: str = "adapter"
DEFAULT_SQRUFF_CONFIG_TEMPLATE: str = '[core]\ndialect = "{dialect}"\n'
