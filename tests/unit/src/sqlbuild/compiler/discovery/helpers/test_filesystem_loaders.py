"""Tests for source loader discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.exceptions import LoaderDiscoveryError
from sqlbuild.compiler.discovery.helpers.filesystem import discover_loader_functions
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    DiscoverLoaderFunctionsTestCase,
)

TEST_CASES: list[DiscoverLoaderFunctionsTestCase] = [
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

@loader(target="raw.customers")
def stripe_customers(ctx):
    return []
""",
        },
        expected_names=("github_events", "stripe_customers"),
        expected_targets=(None, "raw.customers"),
        expected_dependency_counts=(0, 0),
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
    ),
    DiscoverLoaderFunctionsTestCase(
        description="returns empty tuple when loaders directory does not exist",
        files={},
        expected_names=(),
        expected_targets=(),
        expected_dependency_counts=(),
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
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
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
    assert tuple(loader.target for loader in result) == test_case.expected_targets
    assert (
        tuple(len(loader.depends_on) for loader in result) == test_case.expected_dependency_counts
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverLoaderFunctionsTestCase(
            description="raises clear error when loader file import fails",
            files={"loaders/broken.py": "import missing_loader_dependency\n"},
            expected_names=(),
            expected_targets=(),
            expected_dependency_counts=(),
            expected_error_fragment="Failed to import source loader file",
        )
    ],
    ids=["raises clear error when loader file import fails"],
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
