from __future__ import annotations

import pytest

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.exceptions import CliUserError
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig
from sqlbuild.spec.resolution.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    ResolveAdapterErrorTestCase,
    ResolveAdapterTestCase,
    ResolveEffectiveAdapterNameTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
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
        ResolveAdapterTestCase(
            description="resolves motherduck adapter lazily",
            adapter_name="motherduck",
            expected_adapter_class_name="MotherDuckAdapter",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_name_when_resolving_adapter_then_returns_expected_adapter(
    test_case: ResolveAdapterTestCase,
) -> None:
    adapter: BaseAdapter = resolve_adapter(adapter_name=test_case.adapter_name)

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
    ids=lambda case: case.description,
)
def test_given_unknown_adapter_when_resolving_adapter_then_raises_cli_user_error(
    test_case: ResolveAdapterErrorTestCase,
) -> None:
    with pytest.raises(CliUserError) as error_info:
        resolve_adapter(adapter_name=test_case.adapter_name)

    assert error_info.value.code == "C601"
    assert test_case.expected_error_fragment in str(error_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
)
def test_given_project_and_local_adapter_when_resolving_effective_name_then_it_returns_expected(
    test_case: ResolveEffectiveAdapterNameTestCase,
) -> None:
    adapter_name: str = resolve_effective_adapter_name(
        project_config=ProjectConfig(name="demo", adapter=test_case.project_adapter),
        local_config=LocalConfig(adapter=test_case.local_adapter),
    )

    assert adapter_name == test_case.expected_adapter_name
