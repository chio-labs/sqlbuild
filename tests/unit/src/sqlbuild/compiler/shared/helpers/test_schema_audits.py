from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.shared.helpers.schema_audits import parse_audit_instance
from sqlbuild.spec.models.schema import SchemaAuditInstance
from tests.unit.src.sqlbuild.compiler.shared.helpers._test_types import (
    ParseAuditInstanceErrorTestCase,
    ParseAuditInstanceTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParseAuditInstanceTestCase(
            description="parses always_run as reserved audit option",
            raw_audit={
                "not_null": {
                    "always_run": True,
                    "severity": "error",
                    "column": "order_id",
                }
            },
            expected_definition_name="not_null",
            expected_always_run=True,
            expected_argument_keys=("column",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_audit_mapping_when_parsing_then_always_run_is_reserved_option(
    test_case: ParseAuditInstanceTestCase,
) -> None:
    result: SchemaAuditInstance = parse_audit_instance(
        raw_audit=test_case.raw_audit,
        file_path=Path("models/orders.sql"),
        label="model orders",
        error_class=ValueError,
    )

    assert result.definition_name == test_case.expected_definition_name
    assert result.always_run is test_case.expected_always_run
    assert tuple(sorted(result.arguments)) == test_case.expected_argument_keys


@pytest.mark.parametrize(
    "test_case",
    [
        ParseAuditInstanceErrorTestCase(
            description="rejects non-boolean always_run",
            raw_audit={"not_null": {"always_run": "true"}},
            expected_error_fragment="'always_run' must be a boolean",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_non_boolean_always_run_when_parsing_then_raises_clear_error(
    test_case: ParseAuditInstanceErrorTestCase,
) -> None:
    with pytest.raises(ValueError) as error_info:
        parse_audit_instance(
            raw_audit=test_case.raw_audit,
            file_path=Path("models/orders.sql"),
            label="model orders",
            error_class=ValueError,
        )

    assert test_case.expected_error_fragment in str(error_info.value)
