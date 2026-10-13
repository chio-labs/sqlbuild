"""Constants for the lint and format layer."""

from __future__ import annotations

from sqlbuild.lint.types import LintSeverity

LINT_ENGINE_SQLBUILD: str = "sqlbuild"
LINT_ENGINE_NATIVE: str = "native"

VIOLATION_SEVERITY_FAULT: LintSeverity = LintSeverity.FAULT
VIOLATION_SEVERITY_WARNING: LintSeverity = LintSeverity.WARNING

HEADER_KIND_MODEL: str = "MODEL"
HEADER_KIND_SCENARIO: str = "SCENARIO"
HEADER_KIND_TEST: str = "TEST"
HEADER_KIND_FUNCTION: str = "FUNCTION"
HEADER_KIND_HOOK: str = "HOOK"

DESCRIPTION_HEADER_KINDS: frozenset[str] = frozenset({HEADER_KIND_MODEL, HEADER_KIND_SCENARIO})
DESCRIPTION_REQUIRED_HEADER_KINDS: frozenset[str] = frozenset(
    {HEADER_KIND_MODEL, HEADER_KIND_SCENARIO, HEADER_KIND_FUNCTION, HEADER_KIND_HOOK}
)

DEFAULT_MAX_LITERAL_LENGTH: int = 100
DEFAULT_MAX_RANKING_ORDER_BY: int = 5
MAX_LITERAL_LENGTH_THRESHOLD: str = "max_literal_length"
MAX_RANKING_ORDER_BY_THRESHOLD: str = "max_ranking_order_by"
SAFE_RULE_FIX_CODES: frozenset[str] = frozenset(
    {
        "SQBRSQL002",
        "SQBRSQL003",
        "SQBRSQL005",
        "SQBRSQL006",
        "SQBRSQL008",
        "SQBRSQL017",
        "SQBRSQL025",
        "SQBRSQL042",
    }
)

LINT_DIRECTORY_NAMES: tuple[str, ...] = (
    "models",
    "tests",
    "audits",
    "functions",
    "enums",
    "constants",
    "hooks",
    "schemas",
)

RULE_DESCRIPTION_PRESENT: str = "description-present"
RULE_DESCRIPTION_LENGTH: str = "description-length"
RULE_LEADING_COMMENT_DESCRIPTION: str = "leading-comment-description"
RULE_HEADER_WHITESPACE: str = "header-whitespace"
RULE_HEADER_PARSE: str = "header-parse"

TEMPLATE_INTERPOLATION_START: str = "${"
RELATION_IDENTITY_TEMPLATE: str = "{kind}:{name}"
RELATION_KIND_SOURCE: str = "source"
RELATION_KIND_SEED: str = "seed"

FIX_COLUMNS_UNKNOWN: str = "Output columns could not be inferred, so the fix cannot be verified"
FIX_COLUMNS_CHANGED: str = "The fix would change output columns, types or nullability"
FIX_DEPENDENCIES_CHANGED: str = "The fix would change model dependencies"
FIX_LINEAGE_CHANGED: str = "The fix would change column lineage"
FIX_NEW_DIAGNOSTICS: str = "The fix would add compile diagnostics: "
