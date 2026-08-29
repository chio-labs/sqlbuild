"""Tests for preserve target logical namespace validation."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.attachment.namespace_validation import (
    validate_preserved_logical_namespace,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.spec.contracts.models import TargetConfig
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    PreservedLogicalNamespaceTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        PreservedLogicalNamespaceTestCase(
            description="preserved schema without logical schema fails closed",
            logical_database="analytics",
            logical_schema=None,
            target_database=None,
            target_schema="preserve",
            expected_error_fragment="Model 'orders' has no logical schema",
        ),
        PreservedLogicalNamespaceTestCase(
            description="preserved database without logical database fails closed",
            logical_database=None,
            logical_schema="marts",
            target_database="preserve",
            target_schema=None,
            expected_error_fragment="Model 'orders' has no logical database",
        ),
        PreservedLogicalNamespaceTestCase(
            description="both preserved dimensions report one structured error",
            logical_database=None,
            logical_schema=None,
            target_database="preserve",
            target_schema="preserve",
            expected_error_fragment="no logical database and schema",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_missing_logical_namespace_when_validating_preserve_then_structured_error_is_raised(
    test_case: PreservedLogicalNamespaceTestCase,
) -> None:
    target: TargetConfig = TargetConfig(
        database=test_case.target_database,
        schema=test_case.target_schema,
    )
    with pytest.raises(CompileInputError, match=str(test_case.expected_error_fragment)) as error:
        validate_preserved_logical_namespace(
            resource_label="Model 'orders'",
            logical_database=test_case.logical_database,
            logical_schema=test_case.logical_schema,
            target_config=target,
        )
    assert error.value.help is not None
    assert "defaults" in error.value.help


@pytest.mark.parametrize(
    "test_case",
    (
        PreservedLogicalNamespaceTestCase(
            description="literal target supplies namespace without logical values",
            logical_database=None,
            logical_schema=None,
            target_database="physical_db",
            target_schema="physical_schema",
            expected_error_fragment=None,
        ),
        PreservedLogicalNamespaceTestCase(
            description="missing target fields retain adapter fallback",
            logical_database=None,
            logical_schema=None,
            target_database=None,
            target_schema=None,
            expected_error_fragment=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_non_preserved_target_when_validating_namespace_then_adapter_fallback_remains_allowed(
    test_case: PreservedLogicalNamespaceTestCase,
) -> None:
    validate_preserved_logical_namespace(
        resource_label="Model 'orders'",
        logical_database=test_case.logical_database,
        logical_schema=test_case.logical_schema,
        target_config=TargetConfig(
            database=test_case.target_database,
            schema=test_case.target_schema,
        ),
    )
    assert test_case.expected_error_fragment is None
