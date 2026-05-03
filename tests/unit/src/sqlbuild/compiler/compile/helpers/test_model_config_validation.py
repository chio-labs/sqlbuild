"""Tests for compile-time model config validation."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.model_config_validation import (
    validate_custom_materialization_config,
    validate_incremental_config,
    validate_non_incremental_config,
    validate_placeholder_config,
)
from sqlbuild.compiler.compile.models import CompileModelConfig
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    CustomMaterializationConfigErrorTestCase,
    CustomMaterializationConfigValidTestCase,
    IncrementalConfigErrorTestCase,
    IncrementalConfigValidTestCase,
    NonIncrementalConfigErrorTestCase,
    NonIncrementalConfigValidTestCase,
    PlaceholderConfigErrorTestCase,
    PlaceholderConfigValidTestCase,
)

VALID_TEST_CASES: list[IncrementalConfigValidTestCase] = [
    IncrementalConfigValidTestCase(
        description="valid delete_insert with cursor",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "event_time",
            "cursor_type": "timestamp",
            "cursor_grain": "second",
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
            "cursor_grain": "hour",
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
            "cursor_grain": "second",
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
    cursor_inputs: object | None = test_case.config_values.get("cursor_inputs")
    known_input_names: frozenset[str] = (
        frozenset(str(name) for name in cursor_inputs)
        if isinstance(cursor_inputs, dict)
        else frozenset()
    )

    validate_incremental_config(
        config=config,
        model_name="test_model",
        ref_count=test_case.ref_count,
        known_input_names=known_input_names,
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
            "cursor_grain": "second",
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
            "cursor_grain": "second",
        },
        ref_count=2,
        expected_error_fragment="require explicit cursor_inputs",
    ),
    IncrementalConfigErrorTestCase(
        description="cursor_inputs with unknown input key raises",
        config_values={
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "event_time",
            "cursor_type": "timestamp",
            "cursor_grain": "second",
            "cursor_inputs": {"missing_relation": "event_time"},
        },
        ref_count=1,
        expected_error_fragment="cursor_inputs references unknown input 'missing_relation'",
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
            "cursor_grain": "second",
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
            known_input_names=frozenset({"orders", "shipments"}),
        )


NON_INCREMENTAL_VALID_TEST_CASES: list[NonIncrementalConfigValidTestCase] = [
    NonIncrementalConfigValidTestCase(
        description="table model without schema change keys passes",
        config_values={"materialized": "table"},
    ),
    NonIncrementalConfigValidTestCase(
        description="view model without schema change keys passes",
        config_values={"materialized": "view"},
    ),
    NonIncrementalConfigValidTestCase(
        description="incremental model with on_schema_change passes",
        config_values={"materialized": "incremental", "on_schema_change": "append_new_columns"},
    ),
    NonIncrementalConfigValidTestCase(
        description="incremental model with schema_change_backfill passes",
        config_values={
            "materialized": "incremental",
            "schema_change_backfill": {"add_column": "bounded-30d"},
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    NON_INCREMENTAL_VALID_TEST_CASES,
    ids=[case.description for case in NON_INCREMENTAL_VALID_TEST_CASES],
)
def test_given_valid_non_incremental_config_when_validating_then_passes(
    test_case: NonIncrementalConfigValidTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    validate_non_incremental_config(
        config=config,
        model_name="test_model",
    )

    assert test_case.expected_valid


NON_INCREMENTAL_ERROR_TEST_CASES: list[NonIncrementalConfigErrorTestCase] = [
    NonIncrementalConfigErrorTestCase(
        description="table model with on_schema_change raises",
        config_values={"materialized": "table", "on_schema_change": "append_new_columns"},
        expected_error_fragment="on_schema_change is only valid for incremental",
    ),
    NonIncrementalConfigErrorTestCase(
        description="view model with on_schema_change raises",
        config_values={"materialized": "view", "on_schema_change": "fail"},
        expected_error_fragment="on_schema_change is only valid for incremental",
    ),
    NonIncrementalConfigErrorTestCase(
        description="table model with schema_change_backfill raises",
        config_values={
            "materialized": "table",
            "schema_change_backfill": {"add_column": "full"},
        },
        expected_error_fragment="schema_change_backfill is only valid for incremental",
    ),
    NonIncrementalConfigErrorTestCase(
        description="view model with schema_change_backfill raises",
        config_values={
            "materialized": "view",
            "schema_change_backfill": {"type_change": "full"},
        },
        expected_error_fragment="schema_change_backfill is only valid for incremental",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    NON_INCREMENTAL_ERROR_TEST_CASES,
    ids=[case.description for case in NON_INCREMENTAL_ERROR_TEST_CASES],
)
def test_given_non_incremental_config_with_incremental_keys_when_validating_then_raises(
    test_case: NonIncrementalConfigErrorTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        validate_non_incremental_config(
            config=config,
            model_name="test_model",
        )


CUSTOM_MATERIALIZATION_VALID_TEST_CASES: list[CustomMaterializationConfigValidTestCase] = [
    CustomMaterializationConfigValidTestCase(
        description="valid custom materialization with config passthrough",
        config_values={"materialized": "partition_tracked", "config": {"tracking_schema": "meta"}},
        custom_materialization_names=frozenset({"partition_tracked"}),
    ),
    CustomMaterializationConfigValidTestCase(
        description="valid custom materialization with unique_key",
        config_values={"materialized": "atomic_swap", "unique_key": ["order_id"]},
        custom_materialization_names=frozenset({"atomic_swap"}),
    ),
    CustomMaterializationConfigValidTestCase(
        description="built-in table materialization skips custom validation",
        config_values={"materialized": "table"},
        custom_materialization_names=frozenset(),
    ),
    CustomMaterializationConfigValidTestCase(
        description="built-in incremental materialization skips custom validation",
        config_values={"materialized": "incremental", "incremental_strategy": "append"},
        custom_materialization_names=frozenset(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CUSTOM_MATERIALIZATION_VALID_TEST_CASES,
    ids=[case.description for case in CUSTOM_MATERIALIZATION_VALID_TEST_CASES],
)
def test_given_valid_custom_materialization_config_when_validating_then_passes(
    test_case: CustomMaterializationConfigValidTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    validate_custom_materialization_config(
        config=config,
        model_name="test_model",
        custom_materialization_names=test_case.custom_materialization_names,
    )

    assert test_case.expected_valid is True


CUSTOM_MATERIALIZATION_ERROR_TEST_CASES: list[CustomMaterializationConfigErrorTestCase] = [
    CustomMaterializationConfigErrorTestCase(
        description="unknown materialization name with no custom discovered",
        config_values={"materialized": "nonexistent"},
        custom_materialization_names=frozenset(),
        expected_error_fragment="unknown materialization 'nonexistent'",
    ),
    CustomMaterializationConfigErrorTestCase(
        description="unknown materialization name not in custom set",
        config_values={"materialized": "nonexistent"},
        custom_materialization_names=frozenset({"partition_tracked"}),
        expected_error_fragment="unknown materialization 'nonexistent'",
    ),
    CustomMaterializationConfigErrorTestCase(
        description="cursor disallowed on custom materialization",
        config_values={"materialized": "partition_tracked", "cursor": "event_time"},
        custom_materialization_names=frozenset({"partition_tracked"}),
        expected_error_fragment="cursor is not allowed on custom materializations",
    ),
    CustomMaterializationConfigErrorTestCase(
        description="incremental_strategy disallowed on custom materialization",
        config_values={"materialized": "partition_tracked", "incremental_strategy": "append"},
        custom_materialization_names=frozenset({"partition_tracked"}),
        expected_error_fragment="incremental_strategy is not allowed on custom materializations",
    ),
    CustomMaterializationConfigErrorTestCase(
        description="on_schema_change disallowed on custom materialization",
        config_values={"materialized": "partition_tracked", "on_schema_change": "fail"},
        custom_materialization_names=frozenset({"partition_tracked"}),
        expected_error_fragment="on_schema_change is not allowed on custom materializations",
    ),
    CustomMaterializationConfigErrorTestCase(
        description="batch_size disallowed on custom materialization",
        config_values={"materialized": "partition_tracked", "batch_size": "1h"},
        custom_materialization_names=frozenset({"partition_tracked"}),
        expected_error_fragment="batch_size is not allowed on custom materializations",
    ),
    CustomMaterializationConfigErrorTestCase(
        description="lookback disallowed on custom materialization",
        config_values={"materialized": "partition_tracked", "lookback": "1d"},
        custom_materialization_names=frozenset({"partition_tracked"}),
        expected_error_fragment="lookback is not allowed on custom materializations",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CUSTOM_MATERIALIZATION_ERROR_TEST_CASES,
    ids=[case.description for case in CUSTOM_MATERIALIZATION_ERROR_TEST_CASES],
)
def test_given_invalid_custom_materialization_config_when_validating_then_raises(
    test_case: CustomMaterializationConfigErrorTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        validate_custom_materialization_config(
            config=config,
            model_name="test_model",
            custom_materialization_names=test_case.custom_materialization_names,
        )


PLACEHOLDER_VALID_TEST_CASES: list[PlaceholderConfigValidTestCase] = [
    PlaceholderConfigValidTestCase(
        description="custom materialization with matching placeholders and defaults",
        config_values={
            "materialized": "partition_tracked",
            "placeholders": {"partition_start": "'2020-01-01'", "partition_end": "'2099-12-31'"},
        },
        query_sql="SELECT * FROM t WHERE d >= @@partition_start AND d < @@partition_end",
        custom_materialization_names=frozenset({"partition_tracked"}),
    ),
    PlaceholderConfigValidTestCase(
        description="custom materialization without placeholders",
        config_values={"materialized": "atomic_swap"},
        query_sql="SELECT * FROM t",
        custom_materialization_names=frozenset({"atomic_swap"}),
    ),
    PlaceholderConfigValidTestCase(
        description="built-in table materialization without placeholders",
        config_values={"materialized": "table"},
        query_sql="SELECT * FROM t",
        custom_materialization_names=frozenset(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLACEHOLDER_VALID_TEST_CASES,
    ids=[case.description for case in PLACEHOLDER_VALID_TEST_CASES],
)
def test_given_valid_placeholder_config_when_validating_then_passes(
    test_case: PlaceholderConfigValidTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    validate_placeholder_config(
        config=config,
        model_name="test_model",
        query_sql=test_case.query_sql,
        custom_materialization_names=test_case.custom_materialization_names,
    )

    assert test_case.expected_valid is True


PLACEHOLDER_ERROR_TEST_CASES: list[PlaceholderConfigErrorTestCase] = [
    PlaceholderConfigErrorTestCase(
        description="@@placeholder on built-in materialization",
        config_values={"materialized": "table"},
        query_sql="SELECT * FROM t WHERE d >= @@partition_start",
        custom_materialization_names=frozenset(),
        expected_error_fragment="@@placeholders are only allowed on custom materializations",
    ),
    PlaceholderConfigErrorTestCase(
        description="placeholders config on built-in materialization",
        config_values={"materialized": "table", "placeholders": {"x": "'1'"}},
        query_sql="SELECT * FROM t",
        custom_materialization_names=frozenset(),
        expected_error_fragment="placeholders config is only allowed on custom materializations",
    ),
    PlaceholderConfigErrorTestCase(
        description="@@placeholder without default in config",
        config_values={"materialized": "partition_tracked"},
        query_sql="SELECT * FROM t WHERE d >= @@partition_start",
        custom_materialization_names=frozenset({"partition_tracked"}),
        expected_error_fragment="@@placeholders without default values",
    ),
    PlaceholderConfigErrorTestCase(
        description="placeholder default not used in SQL",
        config_values={
            "materialized": "partition_tracked",
            "placeholders": {"partition_start": "'2020-01-01'", "unused_var": "'x'"},
        },
        query_sql="SELECT * FROM t WHERE d >= @@partition_start",
        custom_materialization_names=frozenset({"partition_tracked"}),
        expected_error_fragment="placeholders config entries not used in SQL",
    ),
    PlaceholderConfigErrorTestCase(
        description="partial mismatch between SQL placeholders and config",
        config_values={
            "materialized": "partition_tracked",
            "placeholders": {"partition_start": "'2020-01-01'"},
        },
        query_sql="SELECT * FROM t WHERE d >= @@partition_start AND d < @@partition_end",
        custom_materialization_names=frozenset({"partition_tracked"}),
        expected_error_fragment="@@placeholders without default values.*partition_end",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLACEHOLDER_ERROR_TEST_CASES,
    ids=[case.description for case in PLACEHOLDER_ERROR_TEST_CASES],
)
def test_given_invalid_placeholder_config_when_validating_then_raises(
    test_case: PlaceholderConfigErrorTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        validate_placeholder_config(
            config=config,
            model_name="test_model",
            query_sql=test_case.query_sql,
            custom_materialization_names=test_case.custom_materialization_names,
        )
