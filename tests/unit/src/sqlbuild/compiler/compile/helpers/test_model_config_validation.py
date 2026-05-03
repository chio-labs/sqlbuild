"""Tests for compile-time incremental model config validation."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.model_config_validation import (
    validate_incremental_config,
)
from sqlbuild.compiler.compile.models import CompileModelConfig
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    IncrementalConfigErrorTestCase,
    IncrementalConfigValidTestCase,
)

VALID_TEST_CASES: list[IncrementalConfigValidTestCase] = [
    IncrementalConfigValidTestCase(
        description="valid delete_insert with cursor",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "event_time",
            "cursor_type": "timestamp",
        },
        ref_count=1,
    ),
    IncrementalConfigValidTestCase(
        description="valid append without cursor",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "append",
        },
        ref_count=1,
    ),
    IncrementalConfigValidTestCase(
        description="valid merge with unique_key",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "merge",
            "unique_key": "order_id",
        },
        ref_count=1,
    ),
    IncrementalConfigValidTestCase(
        description="valid delete_insert without cursor with unique_key",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "unique_key": "order_id",
        },
        ref_count=1,
    ),
    IncrementalConfigValidTestCase(
        description="non-incremental model skips validation",
        config_values={"materialized": "table"},
        ref_count=1,
    ),
    IncrementalConfigValidTestCase(
        description="valid microbatch with batch_size",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "event_time",
            "cursor_type": "timestamp",
            "incremental_mode": "microbatch",
            "batch_size": "1h",
        },
        ref_count=1,
    ),
    IncrementalConfigValidTestCase(
        description="multi-input with cursor and cursor_inputs",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "event_time",
            "cursor_type": "timestamp",
            "cursor_inputs": {"orders": "event_time", "shipments": "event_time"},
        },
        ref_count=2,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    VALID_TEST_CASES,
    ids=[case.description for case in VALID_TEST_CASES],
)
def test_given_valid_config_when_validating_then_passes(
    test_case: IncrementalConfigValidTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    validate_incremental_config(
        config=config,
        model_name="test_model",
        ref_count=test_case.ref_count,
    )

    assert test_case.expected_valid


ERROR_TEST_CASES: list[IncrementalConfigErrorTestCase] = [
    IncrementalConfigErrorTestCase(
        description="incremental without strategy raises",
        config_values={"materialized": "incremental"},
        ref_count=1,
        expected_error_fragment="requires incremental_strategy",
    ),
    IncrementalConfigErrorTestCase(
        description="unknown strategy raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "upsert",
        },
        ref_count=1,
        expected_error_fragment="unknown incremental_strategy",
    ),
    IncrementalConfigErrorTestCase(
        description="cursor without cursor_type raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "event_time",
        },
        ref_count=1,
        expected_error_fragment="cursor requires cursor_type",
    ),
    IncrementalConfigErrorTestCase(
        description="cursor on append raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "append",
            "cursor": "event_time",
            "cursor_type": "timestamp",
        },
        ref_count=1,
        expected_error_fragment="not allowed with append",
    ),
    IncrementalConfigErrorTestCase(
        description="cursor_inputs without cursor raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "append",
            "cursor_inputs": {"orders": "event_time"},
        },
        ref_count=1,
        expected_error_fragment="cursor_inputs requires cursor",
    ),
    IncrementalConfigErrorTestCase(
        description="multi-input with cursor but no cursor_inputs raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "event_time",
            "cursor_type": "timestamp",
        },
        ref_count=2,
        expected_error_fragment="require explicit cursor_inputs",
    ),
    IncrementalConfigErrorTestCase(
        description="delete_insert without cursor or unique_key raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
        },
        ref_count=1,
        expected_error_fragment="requires unique_key",
    ),
    IncrementalConfigErrorTestCase(
        description="merge without unique_key raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "merge",
        },
        ref_count=1,
        expected_error_fragment="requires unique_key",
    ),
    IncrementalConfigErrorTestCase(
        description="lookback without cursor raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "append",
            "lookback": "1d",
        },
        ref_count=1,
        expected_error_fragment="lookback is only valid with cursor",
    ),
    IncrementalConfigErrorTestCase(
        description="batch_size without microbatch raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "event_time",
            "cursor_type": "timestamp",
            "batch_size": "1h",
        },
        ref_count=1,
        expected_error_fragment="batch_size is only valid with",
    ),
    IncrementalConfigErrorTestCase(
        description="unknown cursor_type raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "event_time",
            "cursor_type": "date",
        },
        ref_count=1,
        expected_error_fragment="unknown cursor_type",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_config_when_validating_then_raises(
    test_case: IncrementalConfigErrorTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        validate_incremental_config(
            config=config,
            model_name="test_model",
            ref_count=test_case.ref_count,
        )
