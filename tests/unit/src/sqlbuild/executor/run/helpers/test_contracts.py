from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.run.helpers.contracts import validate_runtime_contract
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    RuntimeContractValidationTestCase,
)
from tests.unit.src.sqlbuild.executor.run.helpers.helpers import build_contract_model_plan_entry

VALID_TEST_CASES: list[RuntimeContractValidationTestCase] = [
    RuntimeContractValidationTestCase(
        description="skips non-enforced contract",
        contract_enforced=False,
        contract_columns=(ColumnInfo(name="id", type="INTEGER"),),
        actual_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="extra_column", type="VARCHAR"),
        ),
        expected_valid=True,
    ),
    RuntimeContractValidationTestCase(
        description="allows exact enforced contract with compatible types",
        contract_enforced=True,
        contract_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="status", type="VARCHAR"),
        ),
        actual_columns=(
            ColumnInfo(name="id", type="INT"),
            ColumnInfo(name="status", type="VARCHAR"),
        ),
        expected_valid=True,
    ),
    RuntimeContractValidationTestCase(
        description="allows untyped declared contract column",
        contract_enforced=True,
        contract_columns=(ColumnInfo(name="id", type=""),),
        actual_columns=(ColumnInfo(name="id", type="INTEGER"),),
        expected_valid=True,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    VALID_TEST_CASES,
    ids=[case.description for case in VALID_TEST_CASES],
)
def test_given_valid_runtime_contract_when_validating_then_passes(
    test_case: RuntimeContractValidationTestCase,
) -> None:
    entry: ModelPlanEntry = build_contract_model_plan_entry(
        contract_enforced=test_case.contract_enforced,
        contract_columns=test_case.contract_columns,
    )

    validate_runtime_contract(entry=entry, actual_columns=test_case.actual_columns)

    assert test_case.expected_valid is True


ERROR_TEST_CASES: list[RuntimeContractValidationTestCase] = [
    RuntimeContractValidationTestCase(
        description="rejects enforced contract with no declared columns",
        contract_enforced=True,
        contract_columns=(),
        actual_columns=(ColumnInfo(name="id", type="INTEGER"),),
        expected_valid=False,
        expected_error_fragment="declares no columns",
        expected_error_code="K007",
    ),
    RuntimeContractValidationTestCase(
        description="rejects missing runtime column",
        contract_enforced=True,
        contract_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="status", type="VARCHAR"),
        ),
        actual_columns=(ColumnInfo(name="id", type="INTEGER"),),
        expected_valid=False,
        expected_error_fragment="missing columns: status",
        expected_error_code="K008",
    ),
    RuntimeContractValidationTestCase(
        description="rejects extra runtime column",
        contract_enforced=True,
        contract_columns=(ColumnInfo(name="id", type="INTEGER"),),
        actual_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="extra_column", type="VARCHAR"),
        ),
        expected_valid=False,
        expected_error_fragment="extra columns: extra_column",
        expected_error_code="K009",
    ),
    RuntimeContractValidationTestCase(
        description="rejects incompatible runtime type",
        contract_enforced=True,
        contract_columns=(ColumnInfo(name="id", type="INTEGER"),),
        actual_columns=(ColumnInfo(name="id", type="VARCHAR"),),
        expected_valid=False,
        expected_error_fragment="has type VARCHAR but contract declares INTEGER",
        expected_error_code="K010",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_runtime_contract_when_validating_then_raises(
    test_case: RuntimeContractValidationTestCase,
) -> None:
    entry: ModelPlanEntry = build_contract_model_plan_entry(
        contract_enforced=test_case.contract_enforced,
        contract_columns=test_case.contract_columns,
    )
    assert test_case.expected_error_fragment is not None

    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment) as exc_info:
        validate_runtime_contract(entry=entry, actual_columns=test_case.actual_columns)

    assert test_case.expected_valid is False
    assert exc_info.value.code == test_case.expected_error_code
