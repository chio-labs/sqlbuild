"""Behavior tests for custom-rule code and typed subject resolution."""

from __future__ import annotations

import pytest

from sqlbuild.rule_engine._helpers.engine.definition import (
    resolve_rule_signature,
    rule_from_value,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import Rule
from sqlbuild.rules import Finding, Model, Project, RuleContext, rule
from tests.unit.src.sqlbuild.rule_engine._helpers.engine._test_types import (
    RuleCodeTestCase,
    RuleSignatureTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RuleCodeTestCase("familyless custom code", "XSQBR001", expected_family="XSQBR"),
        RuleCodeTestCase("named custom family", "XSQBRARCH013", expected_family="XSQBRARCH"),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_custom_code_when_defining_rule_then_family_is_derived(
    test_case: RuleCodeTestCase,
) -> None:
    @rule(code=test_case.code, message="Check the subject", remediation="Update the subject.")
    def check(*, model: Model, ctx: RuleContext) -> list[Finding]:
        del model, ctx
        return []

    decorated: Rule | None = rule_from_value(value=check)

    assert decorated is not None
    assert decorated.family == test_case.expected_family


@pytest.mark.parametrize(
    "test_case",
    [
        RuleCodeTestCase("too few digits", "XSQBRARCH1", expected_error_pattern="custom rule"),
        RuleCodeTestCase("lowercase family", "XSQBRarch001", expected_error_pattern="custom rule"),
        RuleCodeTestCase("built-in namespace", "SQBRARCH001", expected_error_pattern="custom rule"),
        RuleCodeTestCase("too many digits", "XSQBRARCH0001", expected_error_pattern="custom rule"),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_custom_code_when_defining_rule_then_it_is_rejected(
    test_case: RuleCodeTestCase,
) -> None:
    with pytest.raises(RulesError, match=test_case.expected_error_pattern):

        @rule(code=test_case.code, message="Check the subject", remediation="Update the subject.")
        def check(*, model: Model, ctx: RuleContext) -> list[Finding]:
            del model, ctx
            return []


@pytest.mark.parametrize(
    "test_case",
    [
        RuleSignatureTestCase(
            "project subject follows context", expected_subject_parameter="project"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_subject_after_context_when_resolving_then_position_is_not_semantic(
    test_case: RuleSignatureTestCase,
) -> None:
    @rule(
        code="XSQBRARCH021",
        message="Check the project",
        remediation="Update the project.",
    )
    def check(*, ctx: RuleContext, project: Project) -> list[Finding]:
        del project, ctx
        return []

    decorated: Rule | None = rule_from_value(value=check)
    assert decorated is not None

    resolved: Rule = resolve_rule_signature(rule=decorated)

    assert resolved.project_wide is True
    assert resolved.subject_parameter == test_case.expected_subject_parameter
    assert resolved.context_parameter == "ctx"


@pytest.mark.parametrize(
    "test_case",
    [RuleSignatureTestCase("union subject is ambiguous", expected_error_pattern="exactly one")],
    ids=lambda case: case.description,
)
def test_given_ambiguous_union_subject_when_resolving_then_it_is_rejected(
    test_case: RuleSignatureTestCase,
) -> None:
    @rule(
        code="XSQBRARCH022",
        message="Check the subject",
        remediation="Update the subject.",
    )
    def check(*, subject: Model | Project, ctx: RuleContext) -> list[Finding]:
        del subject, ctx
        return []

    decorated: Rule | None = rule_from_value(value=check)
    assert decorated is not None

    with pytest.raises(RulesError, match=test_case.expected_error_pattern):
        resolve_rule_signature(rule=decorated)
