"""Tests for task and asset discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_asset_functions,
    discover_check_functions,
    discover_task_functions,
)
from sqlbuild.compiler.discovery.exceptions import PythonNodeDiscoveryError
from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredTaskFunction,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    DiscoverCheckFunctionsTestCase,
    DiscoverTaskAssetFunctionsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverTaskAssetFunctionsTestCase(
            description="discovers decorated tasks and assets from explicit folders",
            files={
                "tasks/windows.py": """
from sqlbuild.tasks import task

@task(tags=("api",), group="ingestion")
def fetch_window(ctx):
    '''Fetch an API window.'''
    return {"window": "today"}

def helper():
    return None
""",
                "assets/exports.py": """
from sqlbuild.assets import asset
from tasks.windows import fetch_window

@asset(
    depends_on=fetch_window,
    columns=[{"name": "customer_id", "type": "string"}],
    column_lineage={"customer_id": [{"node": "dim_customers", "column": "customer_id"}]},
)
def export_customers(ctx):
    return {"uri": "s3://exports/customers.parquet"}
""",
                "assets/__init__.py": """
from sqlbuild.assets import asset

@asset
def ignored_init_asset(ctx):
    return None
""",
            },
            expected_task_names=("fetch_window",),
            expected_task_dependency_counts=(0,),
            expected_task_tags=(("api",),),
            expected_asset_names=("export_customers",),
            expected_asset_dependency_counts=(1,),
            expected_asset_column_names=(("customer_id",),),
            expected_asset_lineage_columns=(("customer_id",),),
        ),
        DiscoverTaskAssetFunctionsTestCase(
            description="returns empty tuples when task and asset folders do not exist",
            files={},
            expected_task_names=(),
            expected_task_dependency_counts=(),
            expected_task_tags=(),
            expected_asset_names=(),
            expected_asset_dependency_counts=(),
            expected_asset_column_names=(),
            expected_asset_lineage_columns=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_dir_when_discovering_python_nodes_then_returns_expected(
    test_case: DiscoverTaskAssetFunctionsTestCase,
    tmp_path: Path,
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in test_case.files.items():
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")

    tasks: tuple[DiscoveredTaskFunction, ...] = discover_task_functions(project_dir=tmp_path)
    assets: tuple[DiscoveredAssetFunction, ...] = discover_asset_functions(project_dir=tmp_path)

    assert tuple(task.name for task in tasks) == test_case.expected_task_names
    assert (
        tuple(len(task.depends_on) for task in tasks) == test_case.expected_task_dependency_counts
    )
    assert tuple(task.tags for task in tasks) == test_case.expected_task_tags
    assert tuple(asset.name for asset in assets) == test_case.expected_asset_names
    assert tuple(len(asset.depends_on) for asset in assets) == (
        test_case.expected_asset_dependency_counts
    )
    actual_asset_column_names: list[tuple[str, ...]] = []
    for asset in assets:
        column_names: list[str] = []
        for column in asset.columns:
            column_names.append(column.name)
        actual_asset_column_names.append(tuple(column_names))
    assert tuple(actual_asset_column_names) == test_case.expected_asset_column_names
    assert (
        tuple(tuple((asset.column_lineage or {}).keys()) for asset in assets)
        == test_case.expected_asset_lineage_columns
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverTaskAssetFunctionsTestCase(
            description="raises clear error when task import fails",
            files={"tasks/broken.py": "import missing_task_dependency\n"},
            expected_task_names=(),
            expected_task_dependency_counts=(),
            expected_task_tags=(),
            expected_asset_names=(),
            expected_asset_dependency_counts=(),
            expected_asset_column_names=(),
            expected_asset_lineage_columns=(),
            expected_error_fragment="Failed to import Python node file",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_python_node_import_error_when_discovering_then_raises_clear_error(
    test_case: DiscoverTaskAssetFunctionsTestCase,
    tmp_path: Path,
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in test_case.files.items():
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")

    with pytest.raises(PythonNodeDiscoveryError, match=test_case.expected_error_fragment):
        discover_task_functions(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverCheckFunctionsTestCase(
            description="discovers decorated checks from explicit folder",
            files={
                "assets/exports.py": """
from sqlbuild.assets import asset

@asset
def export_customers(ctx):
    return {"uri": "s3://exports/customers.parquet"}
""",
                "checks/exports.py": """
from sqlbuild.checks import check
from assets.exports import export_customers

@check(depends_on=export_customers, severity="warn", tags=("exports",))
def export_customers_exists(ctx):
    return True

def helper():
    return None
""",
                "checks/__init__.py": """
from sqlbuild.checks import check
from assets.exports import export_customers

@check(depends_on=export_customers)
def ignored_init_check(ctx):
    return True
""",
            },
            expected_check_names=("export_customers_exists",),
            expected_check_dependency_counts=(1,),
            expected_check_severities=("warn",),
            expected_check_tags=(("exports",),),
        ),
        DiscoverCheckFunctionsTestCase(
            description="returns empty tuple when check folder does not exist",
            files={},
            expected_check_names=(),
            expected_check_dependency_counts=(),
            expected_check_severities=(),
            expected_check_tags=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_dir_when_discovering_checks_then_returns_expected(
    test_case: DiscoverCheckFunctionsTestCase,
    tmp_path: Path,
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in test_case.files.items():
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")

    checks: tuple[DiscoveredCheckFunction, ...] = discover_check_functions(project_dir=tmp_path)

    assert tuple(check.name for check in checks) == test_case.expected_check_names
    assert tuple(len(check.depends_on) for check in checks) == (
        test_case.expected_check_dependency_counts
    )
    assert tuple(check.severity.value for check in checks) == test_case.expected_check_severities
    assert tuple(check.tags for check in checks) == test_case.expected_check_tags
