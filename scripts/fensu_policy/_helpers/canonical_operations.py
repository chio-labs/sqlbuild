"""Canonical-operation predicates for SQLBuild custom rules."""

from fensu import ComparisonFact, NamedCallFact

from scripts.fensu_policy.constants import (
    ATTRIBUTE_REFERENCE_KIND,
    DBT_REF_ATTRIBUTE_NAME,
    SELECTOR_MARKER,
    SELECTOR_STRING_METHOD_NAMES,
    SQL_REFERENCE_KIND_CLASS_NAME,
    STRING_LITERAL_KIND,
)


def comparison_uses_dbt_ref(*, comparison: ComparisonFact) -> bool:
    """Return whether a comparison directly references the dbt ref kind."""

    return any(
        reference is not None
        and reference.base_name == DBT_REF_ATTRIBUTE_NAME
        and reference.receiver_base_name == SQL_REFERENCE_KIND_CLASS_NAME
        for reference in comparison.operand_references
    )


def call_parses_selector_marker(*, call: NamedCallFact) -> bool:
    """Return whether an attribute call parses a literal selector marker."""

    if (
        call.reference is None
        or call.reference.kind != ATTRIBUTE_REFERENCE_KIND
        or call.reference.base_name not in SELECTOR_STRING_METHOD_NAMES
    ):
        return False
    return any(
        argument.position == 0
        and argument.kind == STRING_LITERAL_KIND
        and argument.value == SELECTOR_MARKER
        for argument in call.literal_arguments
    )
