"""Tests for source loader discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.exceptions import LoaderDiscoveryError
from sqlbuild.compiler.discovery.helpers.filesystem.core import discover_loader_functions
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    DiscoverLoaderFunctionsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverLoaderFunctionsTestCase(
            description="discovers decorated source loaders from loaders directory",
            files={
                "loaders/github.py": """
from sqlbuild.loaders import loader

@loader
def github_events(ctx):
    return []
""",
                "loaders/stripe.py": """
from sqlbuild.loaders import loader

@loader(destination="raw.customers")
def stripe_customers(ctx):
    return []
""",
            },
            expected_names=("github_events", "stripe_customers"),
            expected_targets=(None, "raw.customers"),
            expected_dependency_counts=(0, 0),
            expected_write_strategies=(None, None),
            expected_cursor_columns=(None, None),
            expected_unique_keys=((), ()),
            expected_column_names=((), ()),
            expected_contracts=(None, None),
        ),
        DiscoverLoaderFunctionsTestCase(
            description="discovers intermediate loader write and schema metadata",
            files={
                "loaders/events.py": """
from sqlbuild.loaders import loader

@loader(
    destination="staging.events",
    write_strategy="merge",
    cursor_column="updated_at",
    unique_key=["event_id", "updated_at"],
    columns=[
        {"name": "event_id", "type": "BIGINT"},
        {"name": "updated_at", "type": "TIMESTAMP"},
    ],
    contract="enforced",
)
def events(ctx):
    return []
""",
            },
            expected_names=("events",),
            expected_targets=("staging.events",),
            expected_dependency_counts=(0,),
            expected_write_strategies=("merge",),
            expected_cursor_columns=("updated_at",),
            expected_unique_keys=(("event_id", "updated_at"),),
            expected_column_names=(("event_id", "updated_at"),),
            expected_contracts=("enforced",),
        ),
        DiscoverLoaderFunctionsTestCase(
            description="discovers loader dependencies from decorator metadata",
            files={
                "loaders/events.py": """
from sqlbuild.loaders import loader

@loader
def fetch_events(ctx):
    return []

@loader(depends_on=[fetch_events])
def enriched_events(ctx):
    return []
""",
            },
            expected_names=("enriched_events", "fetch_events"),
            expected_targets=(None, None),
            expected_dependency_counts=(1, 0),
            expected_write_strategies=(None, None),
            expected_cursor_columns=(None, None),
            expected_unique_keys=((), ()),
            expected_column_names=((), ()),
            expected_contracts=(None, None),
        ),
        DiscoverLoaderFunctionsTestCase(
            description="discovers explicit loader names and dependencies",
            files={
                "loaders/events.py": """
from sqlbuild.loaders import loader

@loader(name="fetch_events")
def make_fetch(ctx):
    return []

@loader(name="enriched_events", depends_on=[make_fetch])
def make_enriched(ctx):
    return []
""",
            },
            expected_names=("enriched_events", "fetch_events"),
            expected_targets=(None, None),
            expected_dependency_counts=(1, 0),
            expected_write_strategies=(None, None),
            expected_cursor_columns=(None, None),
            expected_unique_keys=((), ()),
            expected_column_names=((), ()),
            expected_contracts=(None, None),
        ),
        DiscoverLoaderFunctionsTestCase(
            description="returns empty tuple when loaders directory does not exist",
            files={},
            expected_names=(),
            expected_targets=(),
            expected_dependency_counts=(),
            expected_write_strategies=(),
            expected_cursor_columns=(),
            expected_unique_keys=(),
            expected_column_names=(),
            expected_contracts=(),
        ),
        DiscoverLoaderFunctionsTestCase(
            description="ignores undecorated functions and init files",
            files={
                "loaders/__init__.py": "",
                "loaders/helpers.py": "def helper(): return None\n",
                "loaders/orders.py": """
from sqlbuild.loaders import loader

@loader
def orders(ctx):
    return []
""",
            },
            expected_names=("orders",),
            expected_targets=(None,),
            expected_dependency_counts=(0,),
            expected_write_strategies=(None,),
            expected_cursor_columns=(None,),
            expected_unique_keys=((),),
            expected_column_names=((),),
            expected_contracts=(None,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_dir_when_discovering_loaders_then_returns_expected(
    test_case: DiscoverLoaderFunctionsTestCase,
    tmp_path: Path,
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in test_case.files.items():
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")

    result: tuple[DiscoveredLoaderFunction, ...] = discover_loader_functions(project_dir=tmp_path)

    assert tuple(loader.name for loader in result) == test_case.expected_names
    assert tuple(loader.destination for loader in result) == test_case.expected_targets
    assert (
        tuple(len(loader.depends_on) for loader in result) == test_case.expected_dependency_counts
    )
    assert (
        tuple(
            None if loader.write_strategy is None else loader.write_strategy.value
            for loader in result
        )
        == test_case.expected_write_strategies
    )
    assert tuple(loader.cursor_column for loader in result) == test_case.expected_cursor_columns
    assert tuple(loader.unique_key for loader in result) == test_case.expected_unique_keys
    assert tuple(tuple(column.name for column in loader.columns) for loader in result) == (
        test_case.expected_column_names
    )
    assert tuple(loader.contract for loader in result) == test_case.expected_contracts


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverLoaderFunctionsTestCase(
            description="raises clear error when loader file import fails",
            files={"loaders/broken.py": "import missing_loader_dependency\n"},
            expected_names=(),
            expected_targets=(),
            expected_dependency_counts=(),
            expected_write_strategies=(),
            expected_cursor_columns=(),
            expected_unique_keys=(),
            expected_column_names=(),
            expected_contracts=(),
            expected_error_fragment="Failed to import source loader file",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_loader_import_error_when_discovering_loaders_then_raises_clear_error(
    test_case: DiscoverLoaderFunctionsTestCase,
    tmp_path: Path,
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in test_case.files.items():
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")

    with pytest.raises(LoaderDiscoveryError, match=test_case.expected_error_fragment):
        discover_loader_functions(project_dir=tmp_path)
