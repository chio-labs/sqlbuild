from __future__ import annotations

import inspect
from typing import Any, cast

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from tests.unit.src.sqlbuild.adapter.strict._test_types import (
    FirstClassAdapterImplementationContractTestCase,
    StrictAdapterContractTestCase,
    TableFreshnessMetadataUnsupportedTestCase,
)
from tests.unit.src.sqlbuild.adapter.strict.helpers import (
    first_class_adapter_contract_violations,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StrictAdapterContractTestCase(
            description="strict adapter covers every public base adapter method",
            expected_missing_methods=frozenset(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_base_adapter_public_methods_when_checking_strict_contract_then_all_are_abstract(
    test_case: StrictAdapterContractTestCase,
) -> None:
    base_public_methods: frozenset[str] = frozenset(
        name
        for name, value in BaseAdapter.__dict__.items()
        if not name.startswith("_") and inspect.isfunction(value)
    )

    abstract_methods: frozenset[str] = cast(Any, StrictAdapter).__abstractmethods__
    missing_methods: frozenset[str] = base_public_methods.difference(abstract_methods)

    assert missing_methods == test_case.expected_missing_methods


@pytest.mark.parametrize(
    "test_case",
    [
        FirstClassAdapterImplementationContractTestCase(
            description="first-class adapters implement strict contract below base adapter",
            expected_violations=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_first_class_adapters_when_checking_contract_then_no_method_comes_from_base(
    test_case: FirstClassAdapterImplementationContractTestCase,
) -> None:
    violations: tuple[str, ...] = first_class_adapter_contract_violations()

    assert violations == test_case.expected_violations


@pytest.mark.parametrize(
    "test_case",
    [
        TableFreshnessMetadataUnsupportedTestCase(
            description="duckdb table freshness metadata is unsupported by default",
            expected_supports_metadata=False,
            expected_error_fragment="does not support table freshness metadata",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_adapter_when_getting_table_freshness_metadata_then_raises_clear_error(
    test_case: TableFreshnessMetadataUnsupportedTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()

    assert adapter.supports_table_freshness_metadata() is test_case.expected_supports_metadata
    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        adapter.get_table_freshness_metadata(
            connection=None,
            database=None,
            schema="main",
            name="raw_orders",
        )
