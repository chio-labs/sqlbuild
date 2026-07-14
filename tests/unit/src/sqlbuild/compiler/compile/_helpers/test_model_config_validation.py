"""Tests for compile-time model config validation."""

from __future__ import annotations

from typing import cast

import pytest

from sqlbuild.compiler.compile._helpers.config.model_validation import (
    validate_contract_config,
    validate_custom_materialization_config,
    validate_incremental_config,
    validate_non_incremental_config,
    validate_placeholder_config,
    validate_snapshot_config,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models.core import CompileModelConfig
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ContractConfigErrorTestCase,
    ContractConfigValidTestCase,
    CustomMaterializationConfigErrorTestCase,
    CustomMaterializationConfigValidTestCase,
    IncrementalConfigErrorTestCase,
    IncrementalConfigValidTestCase,
    NonIncrementalConfigErrorTestCase,
    NonIncrementalConfigValidTestCase,
    PlaceholderConfigErrorTestCase,
    PlaceholderConfigValidTestCase,
    SnapshotConfigErrorTestCase,
    SnapshotConfigValidTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ContractConfigValidTestCase(
            description="allows enforced contract config",
            config_values={"materialized": "table", "contract": "enforced"},
        ),
        ContractConfigValidTestCase(
            description="allows none contract config",
            config_values={"materialized": "table", "contract": "none"},
        ),
        ContractConfigValidTestCase(
            description="allows omitted contract config",
            config_values={"materialized": "table"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_contract_config_when_validating_then_passes(
    test_case: ContractConfigValidTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    validate_contract_config(config=config, model_name="test_model")

    assert test_case.expected_valid is True


@pytest.mark.parametrize(
    "test_case",
    [
        ContractConfigErrorTestCase(
            description="rejects unknown contract config",
            config_values={"materialized": "table", "contract": "strict"},
            expected_error_fragment="unknown contract 'strict'",
        ),
        ContractConfigErrorTestCase(
            description="rejects non-string contract config",
            config_values={"materialized": "table", "contract": True},
            expected_error_fragment="contract must be a string",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_contract_config_when_validating_then_raises(
    test_case: ContractConfigErrorTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    with pytest.raises(CompileInputError) as exc_info:
        validate_contract_config(config=config, model_name="test_model")

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
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
            description="valid append with cursor and explicit inclusive flag",
            config_values={
                "materialized": "incremental",
                "incremental_strategy": "append",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
                "append_cursor_inclusive": False,
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
        IncrementalConfigValidTestCase(
            description="enforced contract allows declared cursor and unique key",
            config_values={
                "materialized": "incremental",
                "contract": "enforced",
                "columns": {
                    "id": {},
                    "event_time": {},
                },
                "incremental_strategy": "delete_insert",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
                "unique_key": ["id"],
            },
            ref_count=1,
        ),
        IncrementalConfigValidTestCase(
            description="non-enforced contract ignores omitted cursor declaration",
            config_values={
                "materialized": "incremental",
                "contract": "none",
                "columns": {"id": {}},
                "incremental_strategy": "delete_insert",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
            },
            ref_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_config_when_validating_then_passes(
    test_case: IncrementalConfigValidTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)
    cursor_inputs: object | None = test_case.config_values.get("cursor_inputs")
    cursor_input_dict: dict[object, object] = cast(
        dict[object, object], ({}, cursor_inputs)[isinstance(cursor_inputs, dict)]
    )
    known_input_names: frozenset[str] = frozenset(str(name) for name in cursor_input_dict)

    validate_incremental_config(
        config=config,
        model_name="test_model",
        ref_count=test_case.ref_count,
        known_input_names=known_input_names,
    )

    assert test_case.expected_valid


@pytest.mark.parametrize(
    "test_case",
    [
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
            description="mapping replay_on_change raises",
            config_values={
                "materialized": "incremental",
                "incremental_strategy": "append",
                "replay_on_change": {"add_column": "bounded-30d"},
            },
            ref_count=1,
            expected_error_fragment="replay_on_change must be a string",
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
            description="append_cursor_inclusive on merge raises",
            config_values={
                "materialized": "incremental",
                "incremental_strategy": "merge",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
                "append_cursor_inclusive": True,
            },
            ref_count=1,
            expected_error_fragment="only valid with append strategy",
        ),
        IncrementalConfigErrorTestCase(
            description="append_cursor_inclusive without cursor raises",
            config_values={
                "materialized": "incremental",
                "incremental_strategy": "append",
                "append_cursor_inclusive": True,
            },
            ref_count=1,
            expected_error_fragment="append_cursor_inclusive requires cursor",
        ),
        IncrementalConfigErrorTestCase(
            description="append_cursor_inclusive non bool raises",
            config_values={
                "materialized": "incremental",
                "incremental_strategy": "append",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
                "append_cursor_inclusive": "yes",
            },
            ref_count=1,
            expected_error_fragment="append_cursor_inclusive must be a boolean",
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
        IncrementalConfigErrorTestCase(
            description="enforced contract rejects undeclared cursor",
            config_values={
                "materialized": "incremental",
                "contract": "enforced",
                "columns": {"id": {}},
                "incremental_strategy": "delete_insert",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
            },
            ref_count=1,
            expected_error_fragment="cursor references column 'event_time' not declared",
        ),
        IncrementalConfigErrorTestCase(
            description="enforced contract rejects undeclared incremental unique key",
            config_values={
                "materialized": "incremental",
                "contract": "enforced",
                "columns": {"event_time": {}},
                "incremental_strategy": "merge",
                "unique_key": ["id"],
            },
            ref_count=1,
            expected_error_fragment="unique_key references column 'id' not declared",
        ),
    ],
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
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
            description="incremental model with replay_on_change passes",
            config_values={
                "materialized": "incremental",
                "replay_on_change": "bounded-30d",
            },
        ),
        NonIncrementalConfigValidTestCase(
            description="incremental model with append_cursor_inclusive passes",
            config_values={
                "materialized": "incremental",
                "incremental_strategy": "append",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
                "append_cursor_inclusive": True,
            },
        ),
    ],
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
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
            description="table model with replay_on_change raises",
            config_values={
                "materialized": "table",
                "replay_on_change": "full",
            },
            expected_error_fragment="replay_on_change is only valid for incremental",
        ),
        NonIncrementalConfigErrorTestCase(
            description="view model with replay_on_change raises",
            config_values={
                "materialized": "view",
                "replay_on_change": "full",
            },
            expected_error_fragment="replay_on_change is only valid for incremental",
        ),
        NonIncrementalConfigErrorTestCase(
            description="table model with append_cursor_inclusive raises",
            config_values={"materialized": "table", "append_cursor_inclusive": True},
            expected_error_fragment="append_cursor_inclusive is only valid for incremental",
        ),
    ],
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotConfigValidTestCase(
            description="valid current-state timestamp snapshot",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
            },
        ),
        SnapshotConfigValidTestCase(
            description="valid current-state check snapshot",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "check",
                "check_columns": ["plan", "status"],
            },
        ),
        SnapshotConfigValidTestCase(
            description="valid current-state check snapshot with wildcard check columns",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "check",
                "check_columns": ["*"],
            },
        ),
        SnapshotConfigValidTestCase(
            description="valid historical check snapshot defaults to snapshot input",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "check",
                "check_columns": ["plan"],
                "observed_at": "snapshot_date",
            },
        ),
        SnapshotConfigValidTestCase(
            description="valid historical timestamp snapshot input",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "observed_at": "snapshot_date",
                "historical_input": "snapshot",
                "invalidate_hard_deletes": True,
            },
        ),
        SnapshotConfigValidTestCase(
            description="valid historical timestamp changes input",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "observed_at": "loaded_at",
                "historical_input": "changes",
            },
        ),
        SnapshotConfigValidTestCase(
            description="valid snapshot with custom validity names and policy",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "valid_from_column": "effective_from",
                "valid_to_column": "effective_to",
                "initial_valid_from": "updated_at",
                "snapshot_full_refresh": "require_confirmation",
                "snapshot_schema_change": "append_new_columns",
            },
        ),
        SnapshotConfigValidTestCase(
            description="enforced contract allows declared snapshot config columns",
            config_values={
                "materialized": "snapshot",
                "contract": "enforced",
                "columns": {
                    "id": {},
                    "updated_at": {},
                    "snapshot_date": {},
                },
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "observed_at": "snapshot_date",
                "historical_input": "snapshot",
            },
        ),
        SnapshotConfigValidTestCase(
            description="non-enforced contract ignores omitted snapshot declaration",
            config_values={
                "materialized": "snapshot",
                "contract": "none",
                "columns": {"id": {}},
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
            },
        ),
        SnapshotConfigValidTestCase(
            description="enforced contract allows wildcard check columns",
            config_values={
                "materialized": "snapshot",
                "contract": "enforced",
                "columns": {
                    "id": {},
                    "plan": {},
                    "status": {},
                },
                "unique_key": ["id"],
                "snapshot_strategy": "check",
                "check_columns": ["*"],
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_snapshot_config_when_validating_then_passes(
    test_case: SnapshotConfigValidTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    validate_snapshot_config(config=config, model_name="test_model")

    assert test_case.expected_valid is True


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotConfigErrorTestCase(
            description="unknown snapshot schema change policy raises",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "snapshot_schema_change": "sync_all_columns",
            },
            expected_error_fragment="unknown snapshot_schema_change",
        ),
        SnapshotConfigErrorTestCase(
            description="enforced contract rejects append new columns snapshot policy",
            config_values={
                "materialized": "snapshot",
                "contract": "enforced",
                "columns": {
                    "id": {},
                    "updated_at": {},
                },
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "snapshot_schema_change": "append_new_columns",
            },
            expected_error_fragment="snapshot_schema_change=append_new_columns is not valid",
            expected_error_code="K012",
        ),
        SnapshotConfigErrorTestCase(
            description="snapshot without unique key raises",
            config_values={"materialized": "snapshot", "snapshot_strategy": "timestamp"},
            expected_error_fragment="requires unique_key",
        ),
        SnapshotConfigErrorTestCase(
            description="snapshot without strategy raises",
            config_values={"materialized": "snapshot", "unique_key": ["id"]},
            expected_error_fragment="requires snapshot_strategy",
        ),
        SnapshotConfigErrorTestCase(
            description="unknown snapshot strategy raises",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "event_time",
            },
            expected_error_fragment="unknown snapshot_strategy",
        ),
        SnapshotConfigErrorTestCase(
            description="timestamp snapshot without updated_at raises",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
            },
            expected_error_fragment="requires updated_at",
        ),
        SnapshotConfigErrorTestCase(
            description="check snapshot without check columns raises",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "check",
            },
            expected_error_fragment="requires check_columns",
        ),
        SnapshotConfigErrorTestCase(
            description="check snapshot rejects mixed wildcard and explicit check columns",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "check",
                "check_columns": ["*", "plan"],
            },
            expected_error_fragment="cannot be combined with explicit columns",
        ),
        SnapshotConfigErrorTestCase(
            description="historical_input without observed_at raises",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "historical_input": "snapshot",
            },
            expected_error_fragment="historical_input requires observed_at",
        ),
        SnapshotConfigErrorTestCase(
            description="timestamp observed snapshot without historical input raises",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "observed_at": "snapshot_date",
            },
            expected_error_fragment="require historical_input snapshot or changes",
        ),
        SnapshotConfigErrorTestCase(
            description="check snapshot rejects changes input",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "check",
                "check_columns": ["plan"],
                "observed_at": "snapshot_date",
                "historical_input": "changes",
            },
            expected_error_fragment="historical_input=changes is not valid",
        ),
        SnapshotConfigErrorTestCase(
            description="hard deletes reject changes input",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "observed_at": "loaded_at",
                "historical_input": "changes",
                "invalidate_hard_deletes": True,
            },
            expected_error_fragment="invalidate_hard_deletes is not valid",
        ),
        SnapshotConfigErrorTestCase(
            description="incremental key on snapshot raises",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "cursor": "updated_at",
            },
            expected_error_fragment="cursor is not allowed on snapshot models",
        ),
        SnapshotConfigErrorTestCase(
            description="matching validity column names raise",
            config_values={
                "materialized": "snapshot",
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "valid_from_column": "valid_at",
                "valid_to_column": "VALID_AT",
            },
            expected_error_fragment="valid_from_column and valid_to_column must differ",
        ),
        SnapshotConfigErrorTestCase(
            description="enforced contract rejects undeclared snapshot unique key",
            config_values={
                "materialized": "snapshot",
                "contract": "enforced",
                "columns": {"updated_at": {}},
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
            },
            expected_error_fragment="unique_key references column 'id' not declared",
        ),
        SnapshotConfigErrorTestCase(
            description="enforced contract rejects undeclared updated_at",
            config_values={
                "materialized": "snapshot",
                "contract": "enforced",
                "columns": {"id": {}},
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
            },
            expected_error_fragment="updated_at references column 'updated_at' not declared",
        ),
        SnapshotConfigErrorTestCase(
            description="enforced contract rejects undeclared observed_at",
            config_values={
                "materialized": "snapshot",
                "contract": "enforced",
                "columns": {
                    "id": {},
                    "updated_at": {},
                },
                "unique_key": ["id"],
                "snapshot_strategy": "timestamp",
                "updated_at": "updated_at",
                "observed_at": "snapshot_date",
                "historical_input": "snapshot",
            },
            expected_error_fragment="observed_at references column 'snapshot_date' not declared",
        ),
        SnapshotConfigErrorTestCase(
            description="enforced contract rejects undeclared check column",
            config_values={
                "materialized": "snapshot",
                "contract": "enforced",
                "columns": {
                    "id": {},
                    "plan": {},
                },
                "unique_key": ["id"],
                "snapshot_strategy": "check",
                "check_columns": ["plan", "status"],
            },
            expected_error_fragment="check_columns references column 'status' not declared",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_snapshot_config_when_validating_then_raises(
    test_case: SnapshotConfigErrorTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(values=test_case.config_values)

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment) as exc_info:
        validate_snapshot_config(config=config, model_name="test_model")

    assert exc_info.value.code == test_case.expected_error_code


@pytest.mark.parametrize(
    "test_case",
    [
        CustomMaterializationConfigValidTestCase(
            description="valid custom materialization with config passthrough",
            config_values={
                "materialized": "partition_tracked",
                "config": {"tracking_schema": "meta"},
            },
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
        CustomMaterializationConfigValidTestCase(
            description="built-in snapshot materialization skips custom validation",
            config_values={
                "materialized": "snapshot",
                "snapshot_strategy": "timestamp",
                "unique_key": ["id"],
                "updated_at": "updated_at",
            },
            custom_materialization_names=frozenset(),
        ),
    ],
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
        PlaceholderConfigValidTestCase(
            description="custom materialization with matching placeholders and defaults",
            config_values={
                "materialized": "partition_tracked",
                "placeholders": {
                    "partition_start": "'2020-01-01'",
                    "partition_end": "'2099-12-31'",
                },
            },
            query_sql="SELECT * FROM t WHERE d >= @@@partition_start AND d < @@@partition_end",
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
        PlaceholderConfigValidTestCase(
            description="built-in table materialization ignores compile-time interpolation tokens",
            config_values={"materialized": "table"},
            query_sql="SELECT * FROM @@schema_name.t",
            custom_materialization_names=frozenset(),
        ),
    ],
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
        PlaceholderConfigErrorTestCase(
            description="@@@placeholder on built-in materialization",
            config_values={"materialized": "table"},
            query_sql="SELECT * FROM t WHERE d >= @@@partition_start",
            custom_materialization_names=frozenset(),
            expected_error_fragment="@@@placeholders are only allowed on custom materializations",
        ),
        PlaceholderConfigErrorTestCase(
            description="placeholders config on built-in materialization",
            config_values={"materialized": "table", "placeholders": {"x": "'1'"}},
            query_sql="SELECT * FROM t",
            custom_materialization_names=frozenset(),
            expected_error_fragment="placeholders config is only allowed on custom materializations",
        ),
        PlaceholderConfigErrorTestCase(
            description="@@@placeholder without default in config",
            config_values={"materialized": "partition_tracked"},
            query_sql="SELECT * FROM t WHERE d >= @@@partition_start",
            custom_materialization_names=frozenset({"partition_tracked"}),
            expected_error_fragment="@@@placeholders without default values",
        ),
        PlaceholderConfigErrorTestCase(
            description="placeholder default not used in SQL",
            config_values={
                "materialized": "partition_tracked",
                "placeholders": {"partition_start": "'2020-01-01'", "unused_var": "'x'"},
            },
            query_sql="SELECT * FROM t WHERE d >= @@@partition_start",
            custom_materialization_names=frozenset({"partition_tracked"}),
            expected_error_fragment="placeholders config entries not used in SQL",
        ),
        PlaceholderConfigErrorTestCase(
            description="partial mismatch between SQL placeholders and config",
            config_values={
                "materialized": "partition_tracked",
                "placeholders": {"partition_start": "'2020-01-01'"},
            },
            query_sql="SELECT * FROM t WHERE d >= @@@partition_start AND d < @@@partition_end",
            custom_materialization_names=frozenset({"partition_tracked"}),
            expected_error_fragment="@@@placeholders without default values.*partition_end",
        ),
    ],
    ids=lambda case: case.description,
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
