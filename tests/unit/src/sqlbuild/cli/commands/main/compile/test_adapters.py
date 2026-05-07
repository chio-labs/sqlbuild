from __future__ import annotations

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, resolve_effective_adapter_name
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    ResolveAdapterErrorTestCase,
    ResolveAdapterTestCase,
    ResolveEffectiveAdapterNameTestCase,
)

EFFECTIVE_ADAPTER_TEST_CASES: list[ResolveEffectiveAdapterNameTestCase] = [
    ResolveEffectiveAdapterNameTestCase(
        description="local adapter overrides project adapter",
        project_adapter="duckdb",
        local_adapter="snowflake",
        expected_adapter_name="snowflake",
    ),
    ResolveEffectiveAdapterNameTestCase(
        description="project adapter is used when local override is absent",
        project_adapter="duckdb",
        local_adapter=None,
        expected_adapter_name="duckdb",
    ),
]

RESOLVE_ADAPTER_TEST_CASES: list[ResolveAdapterTestCase] = [
    ResolveAdapterTestCase(
        description="resolves duckdb adapter lazily",
        adapter_name="duckdb",
        expected_adapter_class_name="DuckDbAdapter",
    ),
    ResolveAdapterTestCase(
        description="resolves bigquery adapter lazily",
        adapter_name="bigquery",
        expected_adapter_class_name="BigQueryAdapter",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RESOLVE_ADAPTER_TEST_CASES,
    ids=[case.description for case in RESOLVE_ADAPTER_TEST_CASES],
)
def test_given_adapter_name_when_resolving_adapter_then_returns_expected_adapter(
    test_case: ResolveAdapterTestCase,
) -> None:
    adapter: BaseAdapter = resolve_adapter(test_case.adapter_name)

    assert adapter.__class__.__name__ == test_case.expected_adapter_class_name


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveAdapterErrorTestCase(
            description="raises for unknown adapter",
            adapter_name="unknown",
            expected_error_fragment="unknown adapter 'unknown'",
        )
    ],
    ids=["raises for unknown adapter"],
)
def test_given_unknown_adapter_when_resolving_adapter_then_raises_cli_user_error(
    test_case: ResolveAdapterErrorTestCase,
) -> None:
    with pytest.raises(CliUserError) as error_info:
        resolve_adapter(test_case.adapter_name)

    assert error_info.value.code == "C601"
    assert test_case.expected_error_fragment in str(error_info.value)


@pytest.mark.parametrize(
    "test_case",
    EFFECTIVE_ADAPTER_TEST_CASES,
    ids=[case.description for case in EFFECTIVE_ADAPTER_TEST_CASES],
)
def test_given_project_and_local_adapter_when_resolving_effective_name_then_it_returns_expected(
    test_case: ResolveEffectiveAdapterNameTestCase,
) -> None:
    adapter_name: str = resolve_effective_adapter_name(
        project_config=ProjectConfig(name="demo", adapter=test_case.project_adapter),
        local_config=LocalConfig(adapter=test_case.local_adapter),
    )

    assert adapter_name == test_case.expected_adapter_name
