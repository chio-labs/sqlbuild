from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.compiler.compile.models import CompiledProject, CompiledRelationTarget
from sqlbuild.compiler.pipeline.helpers.target_validation import validate_project_targets
from tests.unit.src.sqlbuild.compiler.pipeline.helpers.target_validation._test_types import (
    ValidateProjectTargetsTestCase,
)
from tests.unit.src.sqlbuild.compiler.pipeline.helpers.target_validation.helpers import (
    build_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ValidateProjectTargetsTestCase(
            description="snowflake requires explicit database and schema",
            adapter_name=BuiltinAdapter.SNOWFLAKE,
            target=CompiledRelationTarget(
                database=None, schema=None, name="stg_customers", qualified_name=None
            ),
            expected_error_fragment="snowflake execution requires explicit target database, schema",
        )
    ],
    ids=["snowflake requires explicit database and schema"],
)
def test_given_adapter_with_missing_target_namespace_when_validating_then_raises_clear_error(
    test_case: ValidateProjectTargetsTestCase,
) -> None:
    project: CompiledProject = build_project(target=test_case.target)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        validate_project_targets(adapter_name=test_case.adapter_name, project=project)


@pytest.mark.parametrize(
    "test_case",
    [
        ValidateProjectTargetsTestCase(
            description="duckdb allows missing database and schema",
            adapter_name=BuiltinAdapter.DUCKDB,
            target=CompiledRelationTarget(
                database=None,
                schema=None,
                name="stg_customers",
                qualified_name=None,
            ),
            expected_error_fragment="",
        )
    ],
    ids=["duckdb allows missing database and schema"],
)
def test_given_duckdb_with_missing_target_namespace_when_validating_then_it_passes(
    test_case: ValidateProjectTargetsTestCase,
) -> None:
    project: CompiledProject = build_project(target=test_case.target)

    validate_project_targets(adapter_name=test_case.adapter_name, project=project)
    assert test_case.expected_error_fragment == ""
