from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapter.shared.types import TypeDialect
from sqlbuild.compiler.contracts.main.validate import validate_model_contracts
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.spec.models.schema import SourceLocation
from tests.unit.src.sqlbuild.compiler.contracts._test_types import (
    ContractLocationTestCase,
    ContractValidationTestCase,
)
from tests.unit.src.sqlbuild.compiler.contracts.helpers import make_contract_project

TEST_CASES: tuple[ContractValidationTestCase, ...] = (
    ContractValidationTestCase(
        description="declared untyped column exists",
        declared_columns=(("order_id", None),),
        inferred_columns=(("order_id", None),),
        type_enforcement=None,
        expected_codes=(),
        expected_severities=(),
        expected_messages=(),
    ),
    ContractValidationTestCase(
        description="declared untyped column is missing",
        declared_columns=(("customer_id", None),),
        inferred_columns=(("order_id", None),),
        type_enforcement=None,
        expected_codes=("K001",),
        expected_severities=("error",),
        expected_messages=("required column 'customer_id' missing from model output",),
    ),
    ContractValidationTestCase(
        description="declared typed column matches inferred type",
        declared_columns=(("order_id", "INTEGER"),),
        inferred_columns=(("order_id", "INT"),),
        type_enforcement=True,
        expected_codes=(),
        expected_severities=(),
        expected_messages=(),
    ),
    ContractValidationTestCase(
        description="typed mismatch with enforcement is error",
        declared_columns=(("amount_cents", "INTEGER"),),
        inferred_columns=(("amount_cents", "VARCHAR"),),
        type_enforcement=True,
        expected_codes=("K002",),
        expected_severities=("error",),
        expected_messages=(
            "column 'amount_cents' inferred as VARCHAR but contract declares INTEGER",
        ),
    ),
    ContractValidationTestCase(
        description="typed mismatch without enforcement is warning",
        declared_columns=(("amount_cents", "INTEGER"),),
        inferred_columns=(("amount_cents", "VARCHAR"),),
        type_enforcement=False,
        expected_codes=("K002",),
        expected_severities=("warning",),
        expected_messages=(
            "column 'amount_cents' inferred as VARCHAR but contract declares INTEGER",
        ),
    ),
    ContractValidationTestCase(
        description="unknown inferred type with enforcement is warning",
        declared_columns=(("amount_cents", "INTEGER"),),
        inferred_columns=(("amount_cents", None),),
        type_enforcement=True,
        expected_codes=("K003",),
        expected_severities=("warning",),
        expected_messages=(
            "column 'amount_cents' type could not be proven against declared INTEGER",
        ),
    ),
    ContractValidationTestCase(
        description="unknown inferred type without enforcement is ignored",
        declared_columns=(("amount_cents", "INTEGER"),),
        inferred_columns=(("amount_cents", None),),
        type_enforcement=False,
        expected_codes=(),
        expected_severities=(),
        expected_messages=(),
    ),
    ContractValidationTestCase(
        description="extra inferred columns are allowed",
        declared_columns=(("order_id", None),),
        inferred_columns=(("order_id", None), ("extra_column", None)),
        type_enforcement=None,
        expected_codes=(),
        expected_severities=(),
        expected_messages=(),
    ),
)


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_compiled_project_when_validating_contracts_then_returns_expected_diagnostics(
    test_case: ContractValidationTestCase,
) -> None:
    result: ContractValidationResult = validate_model_contracts(
        make_contract_project(
            declared_columns=test_case.declared_columns,
            inferred_columns=test_case.inferred_columns,
            type_enforcement=test_case.type_enforcement,
        ),
        dialect=TypeDialect.DUCKDB,
    )

    assert tuple(diagnostic.code for diagnostic in result.diagnostics) == test_case.expected_codes
    assert (
        tuple(str(diagnostic.severity) for diagnostic in result.diagnostics)
        == test_case.expected_severities
    )
    assert (
        tuple(diagnostic.message for diagnostic in result.diagnostics)
        == test_case.expected_messages
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ContractLocationTestCase(
            description="uses declared column location",
            column_name="customer_id",
            path=Path("models/orders.sql"),
            line=4,
            column=5,
            expected_path=Path("models/orders.sql"),
            expected_line=4,
            expected_column=5,
        )
    ],
    ids=["uses declared column location"],
)
def test_given_column_location_when_validating_contracts_then_diagnostic_uses_location(
    test_case: ContractLocationTestCase,
) -> None:
    location: SourceLocation = SourceLocation(
        path=test_case.path,
        line=test_case.line,
        column=test_case.column,
    )
    result: ContractValidationResult = validate_model_contracts(
        make_contract_project(
            declared_columns=((test_case.column_name, None),),
            inferred_columns=(("order_id", None),),
            type_enforcement=None,
            column_locations={test_case.column_name: location},
        ),
        dialect=TypeDialect.DUCKDB,
    )

    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].location == location
    assert result.diagnostics[0].path == test_case.expected_path
    assert result.diagnostics[0].line == test_case.expected_line
    assert result.diagnostics[0].column == test_case.expected_column
