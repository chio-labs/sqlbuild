"""Built-in audit, test, and custom-rule coverage rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel, CompileSqlReference
from sqlbuild.kata_engine.constants import (
    EVALUATE_RULE_CALL,
    KATA_THRESHOLD_DEFAULTS,
    MIN_AUDITS_PER_MODEL,
    MIN_CUSTOM_RULE_TEST_CASES,
    MIN_TESTS_PER_MODEL,
)
from sqlbuild.kata_engine.models import KataFault, KataRule
from sqlbuild.kata_engine.types import RuleContext


def _rule(
    *,
    code: str,
    slug: str,
    message: str,
    remediation: str,
    check: Any,
    project_wide: bool = False,
) -> KataRule:
    return KataRule(
        code=code,
        family="tests",
        slug=slug,
        message=message,
        remediation=remediation,
        check=check,
        project_wide=project_wide,
    )


def minimum_audits(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    if ctx.is_passthrough:
        return []
    minimum: int = ctx.kata_config.thresholds.get(
        MIN_AUDITS_PER_MODEL, KATA_THRESHOLD_DEFAULTS[MIN_AUDITS_PER_MODEL]
    )
    if ctx.declared_audit_count >= minimum:
        return []
    return [
        ctx.path_fault(
            message=(
                f"model {model.name!r} has {ctx.declared_audit_count} audits; {minimum} required"
            )
        )
    ]


def minimum_tests(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    if ctx.is_passthrough:
        return []
    minimum: int = ctx.kata_config.thresholds.get(
        MIN_TESTS_PER_MODEL, KATA_THRESHOLD_DEFAULTS[MIN_TESTS_PER_MODEL]
    )
    if ctx.targeting_test_count >= minimum:
        return []
    remediation: str = _test_remediation(model=model)
    return [
        ctx.path_fault(
            message=(
                f"model {model.name!r} has {ctx.targeting_test_count} tests; {minimum} required"
            ),
            remediation=remediation,
        )
    ]


def _test_remediation(*, model: CompiledModel) -> str:
    mock_name: str = "__ref__upstream_model"
    if model.references:
        reference: CompileSqlReference = model.references[0]
        mock_name = f"__{reference.ref_kind}__{reference.ref_name}"
    example: str = (
        "TEST();\n\n"
        "WITH\n"
        f"{mock_name} AS (\n"
        "  SELECT 1 AS input_id, 2 AS input_value\n"
        "),\n"
        f"__expected__{model.name} AS (\n"
        "  SELECT 1 AS output_id, 4 AS transformed_value\n"
        ")\n"
        "SELECT 1"
    )
    return (
        "Add a SQL unit test that mocks each real import and asserts concrete transformed rows, "
        f"for example:\n\n{example}\n\n"
        "Choose input rows that exercise this model's actual filter, join, aggregation, or "
        "mapping. Do not merely assert that inputs survive unchanged or re-derive expected "
        "values with the model's own logic. Prove the test is failable: temporarily perturb the "
        "model logic or expected value, confirm the test fails, then revert the mutation."
    )


def custom_rule_test_coverage(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    if not ctx.is_project_anchor:
        return []
    minimum: int = ctx.kata_config.thresholds.get(
        MIN_CUSTOM_RULE_TEST_CASES,
        KATA_THRESHOLD_DEFAULTS[MIN_CUSTOM_RULE_TEST_CASES],
    )
    if minimum == 0:
        return []
    test_files: tuple[Path, ...] = ctx.project_glob(pattern="tests/**/*.py")
    faults: list[KataFault] = []
    for rule in ctx.selected_rules:
        if not rule.custom:
            continue
        case_count: int = 0
        check_name: str = getattr(rule.check, "__name__", "")
        for path in test_files:
            source: str = ctx.project_read_text(path=path.relative_to(ctx.project_dir).as_posix())
            if check_name in source and EVALUATE_RULE_CALL in source:
                case_count += source.count("RuleCase(")
        if case_count >= minimum:
            continue
        source_path: Path = Path(rule.source) if rule.source is not None else Path("kata")
        if source_path.is_absolute() and source_path.is_relative_to(ctx.project_dir):
            source_path = source_path.relative_to(ctx.project_dir)
        faults.append(
            ctx.fault_for(
                path=source_path,
                message=(
                    f"custom rule {rule.code} has {case_count} harness cases; {minimum} required"
                ),
                remediation=(
                    "Add statically visible RuleCase(...) values passed through evaluate_rule in "
                    "tests/ for this custom rule source."
                ),
            )
        )
    return faults


def test_rules() -> tuple[KataRule, ...]:
    """Return built-in test and audit rules."""

    return (
        _rule(
            code="KTX001",
            slug="minimum-audits",
            message="non-passthrough models must declare the configured minimum audits",
            remediation=(
                "Attach concrete not_null, unique, or accepted_values audits to this model's "
                "contract; audits gate promotion when bad rows appear."
            ),
            check=minimum_audits,
        ),
        _rule(
            code="KTX002",
            slug="minimum-tests",
            message="non-passthrough models must have the configured minimum unit tests",
            remediation="Add a failable SQL unit test that targets this model's real logic.",
            check=minimum_tests,
        ),
        _rule(
            code="KTX201",
            slug="custom-rule-test-coverage",
            message="selected custom kata rules must have public-harness test cases",
            remediation="Add RuleCase values evaluated by evaluate_rule under tests/.",
            check=custom_rule_test_coverage,
            project_wide=True,
        ),
    )
