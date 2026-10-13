"""Constants for the lint and format layer."""

from __future__ import annotations

from sqlbuild.lint.types import LintSeverity

LINT_ENGINE_SQLBUILD: str = "sqlbuild"
LINT_ENGINE_NATIVE: str = "native"

VIOLATION_SEVERITY_FAULT: LintSeverity = LintSeverity.FAULT
VIOLATION_SEVERITY_WARNING: LintSeverity = LintSeverity.WARNING

HEADER_KIND_SCENARIO: str = "SCENARIO"
HEADER_KIND_TEST: str = "TEST"

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

TEMPLATE_INTERPOLATION_START: str = "${"
RELATION_IDENTITY_TEMPLATE: str = "{kind}:{name}"
RELATION_KIND_SOURCE: str = "source"
RELATION_KIND_SEED: str = "seed"

FIX_COLUMNS_UNKNOWN: str = "Output columns could not be inferred, so the fix cannot be verified"
FIX_COLUMNS_CHANGED: str = "The fix would change output columns, types or nullability"
FIX_DEPENDENCIES_CHANGED: str = "The fix would change model dependencies"
FIX_LINEAGE_CHANGED: str = "The fix would change column lineage"
FIX_NEW_DIAGNOSTICS: str = "The fix would add compile diagnostics: "
