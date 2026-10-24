"""Planning binds models to listed Snowflake source columns with Snowflake's identifier case rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import CompilePipelineResult
from tests.integration.src.sqlbuild.executor.build.snowflake_metadata._test_types import (
    SourceBindingCaseTestCase,
)
from tests.integration.src.sqlbuild.executor.build.snowflake_metadata.helpers import (
    bundles_warehouse,
    plan_offline_snowflake_project,
    write_bundles_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceBindingCaseTestCase(
            "unquoted", "bundle_sku, quantity", expected_models=("bundle_report",)
        ),
        SourceBindingCaseTestCase("uppercase", "BUNDLE_SKU", expected_models=("bundle_report",)),
        SourceBindingCaseTestCase(
            "quoted uppercase", '"BUNDLE_SKU"', expected_models=("bundle_report",)
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_source_without_quoted_case_setting_when_planning_then_names_bind(
    test_case: SourceBindingCaseTestCase, tmp_path: Path
) -> None:
    write_bundles_project(project_dir=tmp_path, select=test_case.select)
    planned: CompilePipelineResult = plan_offline_snowflake_project(
        project_dir=tmp_path, warehouse=bundles_warehouse()
    )
    assert (
        tuple(entry.name for entry in planned.plan_output.model_entries)
        == test_case.expected_models
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SourceBindingCaseTestCase("quoted lowercase", '"bundle_sku"', "B002"),
        SourceBindingCaseTestCase("unknown", "missing_sku", "B002"),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_source_without_quoted_case_setting_when_planning_then_rejects_unknown(
    test_case: SourceBindingCaseTestCase, tmp_path: Path
) -> None:
    write_bundles_project(project_dir=tmp_path, select=test_case.select)
    with pytest.raises(Exception, match=test_case.expected_error):
        _ = plan_offline_snowflake_project(project_dir=tmp_path, warehouse=bundles_warehouse())


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
