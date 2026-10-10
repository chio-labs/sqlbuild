"""Inference-profile settings crossing into native analysis: rule ids and shape case."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import FunctionNullabilityRule
from sqlbuild.adapter.type_system.main._safe_cast_nullability import safe_cast_nullability
from sqlbuild.adapter.type_system.main.conditional_result_nullability import (
    conditional_result_nullability,
)
from sqlbuild.adapter.type_system.main.first_arg_nullability import first_arg_nullability
from sqlbuild.compiler.analysis_session.constants import (
    NULLABILITY_RULE_ADAPTER,
    NULLABILITY_RULE_CONDITIONAL_RESULT,
    NULLABILITY_RULE_FIRST_ARG,
    NULLABILITY_RULE_SAFE_CAST,
)
from sqlbuild.compiler.sql_analysis.constants import CASE_SENSITIVE_BINDING_DIALECTS

_NULLABILITY_RULE_IDS: dict[FunctionNullabilityRule, str] = {
    first_arg_nullability: NULLABILITY_RULE_FIRST_ARG,
    conditional_result_nullability: NULLABILITY_RULE_CONDITIONAL_RESULT,
    safe_cast_nullability: NULLABILITY_RULE_SAFE_CAST,
}


def nullability_rule_rows(profile: ExpressionInferenceProfile) -> list[tuple[str, str]]:
    """Adapter nullability rules as `(name, rule id)`; an adapter's own rule is `python`."""

    return [
        (name, _NULLABILITY_RULE_IDS.get(rule, NULLABILITY_RULE_ADAPTER))
        for name, rule in profile.function_nullability_rules.items()
    ]


def adapter_nullability_rules(
    profile: ExpressionInferenceProfile,
) -> dict[str, FunctionNullabilityRule]:
    """The adapter's own nullability rules, which the native session calls back into."""

    return {
        name: rule
        for name, rule in profile.function_nullability_rules.items()
        if rule not in _NULLABILITY_RULE_IDS
    }


def case_sensitive_shapes(*, profile: ExpressionInferenceProfile, dialect: str | None) -> bool:
    """Python's `inferred_binding_shape` test for keeping authored identifier quoting."""

    return not profile.quoted_identifiers_ignore_case and dialect in CASE_SENSITIVE_BINDING_DIALECTS
