from __future__ import annotations

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    ResolveAdapterErrorTestCase,
    ResolveAdapterTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveAdapterTestCase(
            description="resolves duckdb adapter lazily",
            adapter_name="duckdb",
            expected_adapter_class_name="DuckDbAdapter",
        )
    ],
    ids=["resolves duckdb adapter lazily"],
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
            expected_error_fragment="Unknown adapter 'unknown'",
        )
    ],
    ids=["raises for unknown adapter"],
)
def test_given_unknown_adapter_when_resolving_adapter_then_raises_value_error(
    test_case: ResolveAdapterErrorTestCase,
) -> None:
    with pytest.raises(ValueError) as error_info:
        resolve_adapter(test_case.adapter_name)

    assert test_case.expected_error_fragment in str(error_info.value)
