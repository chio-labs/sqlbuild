"""Seeded model configs, layers and targets compared between the native and Python paths."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import date
from itertools import compress
from operator import itemgetter
from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile._helpers.attachment.core import build_model_config
from sqlbuild.compiler.compile._helpers.attachment.model_config import (
    build_native_model_config,
    find_matching_path_default,
    native_model_config_session,
    native_model_validators_accept,
    native_path_default,
    run_python_model_validators,
)
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    CompileSqlReference,
    ModelConfigBuildRequest,
    ModelResourceNames,
    ModelValidationRequest,
    ModelValidatorContext,
    NativeModelConfigInputs,
    NativeModelConfigSession,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlModelFile,
    NamedSqlHookEntry,
    PythonHookEntry,
    SqlHookEntry,
)
from sqlbuild.spec.contracts.models import (
    AuthoredTimeTravelRetention,
    DefaultsConfig,
    MaterializationDefaultsConfig,
    MaterializationRetentionDefaults,
    ProjectConfig,
    ResolvedTableType,
    ResolvedTimeTravelRetention,
    SchemaColumn,
    SettingsConfig,
    TargetConfig,
)
from sqlbuild.spec.contracts.types import TableType, TableTypeSource

_ABSENT: object = object()
_RAISES: str = "Python raises"
_DEFERRED: str = "native defers"
_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_RUN_ID: str = "20261008T000000Z_orders"
BUILD_ENVIRONMENT: dict[str, str] = {"SQB_BUILD_DB": "ops", "SQB_BUILD_SCHEMA": "nightly"}
_NAMES: ModelResourceNames = ModelResourceNames(
    models={"orders", "customers"},
    seeds={"regions"},
    sources={"raw.orders"},
    functions={"cents", "order_lines"},
    table_functions={"order_lines"},
    custom_materializations=frozenset({"ledger"}),
)
_VALIDATOR_CONTEXT: ModelValidatorContext = ModelValidatorContext(
    names=_NAMES,
    settings=SettingsConfig(),
    external_sql_reference_resolver=None,
    native_config=None,
)


def _reference(kind: str, name: str) -> CompileSqlReference:
    return CompileSqlReference(ref_kind=kind, ref_name=name)


_ORDERS: CompileSqlReference = _reference("ref", "orders")
_REFERENCES: tuple[CompileSqlReference, ...] = (
    _ORDERS,
    _reference("ref", "customers"),
    _reference("ref", "invoices"),
    _reference("seed", "regions"),
    _reference("seed", "orders"),
    _reference("source", "raw.orders"),
    _reference("source", "raw.refunds"),
    _reference("udf", "cents"),
    _reference("udf", "order_lines"),
    _reference("table_fn", "order_lines"),
    _reference("table_fn", "cents"),
    _reference("dbt_ref", "orders"),
)
_WATERMARK_INPUTS: dict[str, object] = {
    "orders": {"column": "updated_at", "roles": ["filter", "watermark"]}
}
_INCREMENTAL: dict[str, object] = {
    "materialized": "incremental",
    "incremental_strategy": "append",
    "cursor": "updated_at",
    "cursor_type": "timestamp",
    "cursor_grain": "day",
}
_PROFILES: tuple[tuple[dict[str, object], tuple[CompileSqlReference, ...]], ...] = (
    ({"materialized": "table", "tags": ["core"]}, (_ORDERS,)),
    ({"materialized": "view", "contract": "none"}, ()),
    ({**_INCREMENTAL, "cursor_start": "2024-01-01", "cursor_end": "2024-03-01"}, (_ORDERS,)),
    (
        {
            **_INCREMENTAL,
            "incremental_strategy": "delete_insert",
            "incremental_mode": "microbatch",
            "microbatch_strategy": "watermark",
            "cursor_watermark_mode": "all",
            "batch_size": "1d",
            "lookback": "2d",
            "cursor_inputs": _WATERMARK_INPUTS,
            "microbatch_limit": {"max_batches": 6, "action": "cap_from_start"},
        },
        (_ORDERS,),
    ),
    (
        {
            **_INCREMENTAL,
            "incremental_mode": "microbatch",
            "microbatch_strategy": "rolling_window",
            "cursor_inputs": {"orders": "updated_at"},
        },
        (_ORDERS,),
    ),
    (
        {
            "materialized": "incremental",
            "incremental_strategy": "merge",
            "unique_key": ["order_id"],
            "merge_exclude_columns": ["loaded_at"],
            "on_schema_change": "append_new_columns",
            "replay_on_change": "bounded-14d",
        },
        (_ORDERS,),
    ),
    (
        {
            "materialized": "incremental",
            "incremental_strategy": "delete_insert",
            "cursor": "order_id",
            "cursor_type": "integer",
            "cursor_start": "10",
            "cursor_end": 20,
            "unique_key": "order_id",
        },
        (_ORDERS,),
    ),
    (
        {
            "materialized": "snapshot",
            "unique_key": "order_id",
            "snapshot_strategy": "timestamp",
            "updated_at": "updated_at",
            "observed_at": "loaded_at",
            "historical_input": "snapshot",
        },
        (_ORDERS,),
    ),
    (
        {
            "materialized": "snapshot",
            "unique_key": ["order_id"],
            "snapshot_strategy": "check",
            "check_columns": ["*"],
            "contract": "enforced",
            "columns": {"order_id": None, "status": None},
        },
        (_ORDERS,),
    ),
    ({"materialized": "ledger", "placeholders": {"region": "emea"}}, ()),
    (
        {"materialized": "table", "migrate_from": "legacy_orders", "old_name_view": "7d"},
        (_ORDERS,),
    ),
)
_VALIDATION_POOLS: dict[str, tuple[object, ...]] = {
    "materialized": ("table", "view", "incremental", "snapshot", "ledger", "archive", 5),
    "incremental_strategy": ("append", "delete_insert", "merge", "upsert", 3, _ABSENT),
    "cursor": ("updated_at", "order_id", 7, _ABSENT),
    "cursor_type": ("timestamp", "integer", "date", _ABSENT),
    "cursor_grain": ("day", "hour", "month", "week", _ABSENT),
    "cursor_start": (
        "2024-01-01",
        "2024-02-01T00:00:00",
        "2024-01-01 10:00:00+02:00",
        "2024-01-01T00:00:00.123Z",
        "2024-13-01",
        "20240101",
        "2024-W01-1",
        10,
        "15",
        "1e3",
        "abc",
        date(2024, 1, 1),
        True,
        _ABSENT,
    ),
    "cursor_end": ("2024-01-01", "2024-06-01 00:00", 5, 40, "30", "2025-01-01T00:00:00-05:00"),
    "unique_key": ("order_id", ["order_id", "customer_id"], [], (), 5, _ABSENT),
    "merge_exclude_columns": (["amount"], ["ORDER_ID"], ["a", "A"], [""], "amount", _ABSENT),
    "incremental_mode": ("full", "microbatch", "batch", _ABSENT),
    "microbatch_strategy": ("rolling_window", "watermark", "hourly", _ABSENT),
    "cursor_watermark_mode": ("all", "any", "none", _ABSENT),
    "batch_size": ("1d", "effective", "2h", "1mo", 5, _ABSENT),
    "batch_concurrency": (1, 2, 0, -1, True, "2", 2**70, _ABSENT),
    "unaccounted_partition_policy": ("synthesize", "recover_all", "skip", _ABSENT),
    "cursor_inputs": (
        {"orders": "updated_at"},
        _WATERMARK_INPUTS,
        {"customers": {"column": "c", "roles": ["watermark"]}},
        {"orders": {"column": "c", "roles": ["filter", "filter"]}},
        {},
        {"orders": ""},
        {"invoices": "updated_at"},
        ["orders"],
        _ABSENT,
    ),
    "max_microbatches": (1, 3, 10, 0, True, "3", _ABSENT),
    "microbatch_limit": (
        {"max_batches": 5, "action": "cap_from_start"},
        {"max_batches": 2, "action": "warn"},
        {"max_batches": 0, "action": "error"},
        {"max_batches": 5},
        _ABSENT,
    ),
    "lookback": ("3d", "1mo", "2h", "1mo2d", "soon", _ABSENT),
    "on_schema_change": ("fail", "ignore", "drop", 5, _ABSENT),
    "replay_on_change": ("forward", "full", "bounded-14d", "bounded- 1mo ", "bounded-x", _ABSENT),
    "append_cursor_inclusive": (True, False, "yes", _ABSENT),
    "full_refresh": (True, False, "no", _ABSENT),
    "cursor_start_max_ahead": ("disabled", "0d", "7d", "soon", _ABSENT),
    "cursor_start_max_action": ("cap", "error", "warn", _ABSENT),
    "cursor_future_max_distance": ("1d", "disabled", "later", _ABSENT),
    "cursor_future_action": ("cap", "error", ["cap"], _ABSENT),
    "contract": ("enforced", "none", "strict", 1, _ABSENT),
    "columns": ({"order_id": None, "updated_at": None}, _ABSENT),
    "snapshot_strategy": ("timestamp", "check", "hybrid", _ABSENT),
    "updated_at": ("updated_at", "status", 5, _ABSENT),
    "observed_at": ("loaded_at", _ABSENT),
    "historical_input": ("snapshot", "changes", "events", _ABSENT),
    "initial_valid_from": ("updated_at", "observed_at", "execution_time", "now", _ABSENT),
    "snapshot_full_refresh": ("deny", "allow", "always", _ABSENT),
    "snapshot_schema_change": ("deny", "append_new_columns", "drop", _ABSENT),
    "check_columns": (["*"], ["*", "status"], ["status"], [], ("*",), _ABSENT),
    "invalidate_hard_deletes": (True, False, "yes", _ABSENT),
    "valid_from_column": ("valid_from", "VALID_TO", _ABSENT),
    "valid_to_column": ("valid_to", _ABSENT),
    "migrate_from": ("legacy_orders", " ", "orders_daily", " ORDERS_DAILY ", 5, _ABSENT),
    "migrate_force": (True, False, "yes", _ABSENT),
    "old_name_view": ("7d", " 2d ", False, True, "soon", None, _ABSENT),
    "placeholders": ({"region": "emea"}, {"other": "x"}, ["region"], _ABSENT),
}
_RETENTIONS: tuple[ResolvedTimeTravelRetention, ...] = (
    ResolvedTimeTravelRetention(),
    ResolvedTimeTravelRetention(),
    ResolvedTimeTravelRetention(desired_days=7, unmanaged=False),
)
_TABLE_TYPES: tuple[ResolvedTableType, ...] = (
    ResolvedTableType(),
    ResolvedTableType(),
    ResolvedTableType(value=TableType.PERMANENT, source=TableTypeSource.MODEL, declared=True),
)
_DECLARED_COLUMNS: tuple[tuple[SchemaColumn, ...] | None, ...] = (
    None,
    None,
    (SchemaColumn(name="order_id"), SchemaColumn(name="updated_at")),
    (SchemaColumn(name="customer_id"),),
)
_QUERIES: tuple[str, ...] = (
    "SELECT 1",
    "SELECT 1",
    "SELECT '@@@region' AS marker, @@@region AS region",
    "SELECT @@@other",
    "SELECT '@@@' AS marker",
)


@dataclass(frozen=True)
class ModelValidationParity:
    """How native validation compared with the Python validators over one corpus."""

    mismatches: list[dict[str, object]]
    native_accepted: int
    python_accepted: int
    python_rejected: int


@dataclass(frozen=True)
class ConfigBuildCase:
    """One project's layers and target and one model file to build config for."""

    project_config: ProjectConfig
    target_config: TargetConfig | None
    effective_target_name: str | None
    model_file: DiscoveredSqlModelFile


@dataclass(frozen=True)
class ModelConfigBuildParity:
    """How native config builds compared with Python's over one corpus."""

    mismatches: list[tuple[object, object, object]]
    built: int
    deferred: int
    python_raised: int


def generated_validation_requests(
    *, rng: random.Random, count: int
) -> list[ModelValidationRequest]:
    """Return seeded effective configs mixing valid profiles with invalid and unusual values."""

    return [_validation_request(rng=rng) for _ in range(count)]


def model_validation_parity(*, requests: list[ModelValidationRequest]) -> ModelValidationParity:
    """Validate natively and in Python; native may reject valid configs but never accept invalid."""

    session: NativeModelConfigSession = _session(
        project_config=ProjectConfig(name="orders", adapter="duckdb"),
        target_config=None,
        effective_target_name=None,
    )
    native: list[bool] = [
        native_model_validators_accept(session=session, request=request) for request in requests
    ]
    python: list[bool] = [_python_accepts(request) for request in requests]
    wrongly_accepted: list[bool] = [
        accepted and not valid for accepted, valid in zip(native, python, strict=True)
    ]
    return ModelValidationParity(
        mismatches=[request.config.values for request in compress(requests, wrongly_accepted)],
        native_accepted=sum(native),
        python_accepted=sum(python),
        python_rejected=len(python) - sum(python),
    )


def _validation_request(*, rng: random.Random) -> ModelValidationRequest:
    profile, references = rng.choice(_PROFILES)
    values: dict[str, object] = dict(profile)
    mutated: list[str] = rng.sample(sorted(_VALIDATION_POOLS), k=rng.choice((0, 0, 1, 1, 2, 3)))
    values.update((key, rng.choice(_VALIDATION_POOLS[key])) for key in mutated)
    return ModelValidationRequest(
        model_file=_model_file(relative_path="marts/orders_daily.sql", header_values={}),
        config=CompileModelConfig(
            values=dict(
                compress(values.items(), [value is not _ABSENT for value in values.values()])
            ),
            time_travel_retention=rng.choice(_RETENTIONS),
            table_type=rng.choice(_TABLE_TYPES),
        ),
        references=rng.choice(
            (references, references, references, tuple(rng.sample(_REFERENCES, k=2)))
        ),
        declared_columns=rng.choice(_DECLARED_COLUMNS),
        query_sql=rng.choice(_QUERIES),
    )


def _python_accepts(request: ModelValidationRequest) -> bool:
    try:
        run_python_model_validators(context=_VALIDATOR_CONTEXT, request=request)
    except Exception:  # noqa: BLE001 - any Python failure means native must not accept
        return False
    return True


_DEFAULTS: tuple[DefaultsConfig, ...] = (
    DefaultsConfig(),
    DefaultsConfig(materialized="table", schema="analytics", tags=("core",)),
    DefaultsConfig(
        materialized="view",
        database="warehouse",
        schema="${region}_core",
        full_refresh=True,
        row_diff_exclude_columns=("loaded_at",),
        row_diff_tolerances={"by_type": {"DOUBLE": 0.1}, "sample": 3},
    ),
    DefaultsConfig(pre_hooks=[SqlHookEntry(statement="SELECT 1")], tags=("core", "daily")),
    DefaultsConfig(incremental_strategy="append", cursor_start="2024-01-01", contract="none"),
)
_PATH_DEFAULTS: tuple[dict[str, dict[str, object]], ...] = (
    {},
    {"staging": {"materialized": "view", "tags": ["staging", "core"]}},
    {
        "staging/*": {"schema": "${CTX:model.name}_stg", "row_diff_exclude_columns": ["x"]},
        "marts": {
            "materialized": "table",
            "row_diff_tolerances": {"by_column": {"amount": 0.5}, "by_type": "loose"},
            "post_hooks": [NamedSqlHookEntry(name="audit_refresh", kwargs={})],
        },
    },
    {
        "**/finance": {"database": "${ENV:SQB_BUILD_DB}", "tags": "finance"},
        "marts/**": {"tags": [1, 2], "schema": "${CTX:run.target}"},
    },
    {"*/orders.sql": {"materialized": "table"}, "staging/*": {"materialized": "view"}},
)
_HEADER_POOLS: dict[str, tuple[object, ...]] = {
    "materialized": ("table", "incremental", "view", "snapshot", 5),
    "schema": (
        "orders",
        "${region}_${CTX:model.name}",
        "${CTX:run.target}",
        "${ENV:SQB_BUILD_SCHEMA}",
        "${missing}",
        "${CTX:destination.table}",
        "${coalesce(ENV:SQB_UNSET_SCHEMA, 'fallback')}",
    ),
    "database": ("warehouse", "${ENV:SQB_BUILD_DB}", None),
    "alias": ("orders_v2", "${CTX:model.schema}_x", "@cents(amount)"),
    "tags": (["daily"], ["core", "daily"], "daily", [1]),
    "full_refresh": (True, False),
    "time_travel_retention": ("7d", "inherit", "disabled", "0d", "6h", 7),
    "table_type": ("permanent", "transient", "inherit", "temporary"),
    "row_diff_exclude_columns": (["updated_at"], ("x", "y")),
    "row_diff_tolerances": ({"by_type": {"INTEGER": 1}}, {"by_column": {"a": 2}, "x": 1}, "loose"),
    "description": ("Orders.", "Totals for @cents(1)"),
    "unique_key": (["order_id"],),
    "pre_hooks": ([SqlHookEntry(statement="SELECT 1")], ["SELECT 1"], None),
    "post_hooks": ([PythonHookEntry(name="notify", kwargs={})],),
}
_TARGETS: tuple[TargetConfig | None, ...] = (
    None,
    TargetConfig(),
    TargetConfig(database="dev_db", schema="${CTX:model.schema}_dev"),
    TargetConfig(schema="preserve"),
    TargetConfig(database="preserve", schema="analytics"),
    TargetConfig(
        schema="${ENV:SQB_BUILD_SCHEMA}",
        default_table_type=TableType.PERMANENT,
        time_travel_retention=AuthoredTimeTravelRetention(desired_days=3),
        time_travel_retention_by_materialization={
            "incremental": AuthoredTimeTravelRetention(unmanaged=True)
        },
    ),
)
_MATERIALIZATION_DEFAULTS: tuple[MaterializationDefaultsConfig, ...] = (
    MaterializationDefaultsConfig(),
    MaterializationDefaultsConfig(
        table=MaterializationRetentionDefaults(
            time_travel_retention=AuthoredTimeTravelRetention(desired_days=1),
            table_type=TableType.PERMANENT,
        )
    ),
)
_MODEL_PATHS: tuple[str, ...] = (
    "staging/orders.sql",
    "marts/finance/revenue.sql",
    "orders.sql",
)


def generated_config_builds(*, rng: random.Random, count: int) -> list[ConfigBuildCase]:
    """Return seeded project layers, targets and MODEL headers, valid and invalid."""

    return [_config_build_case(rng=rng) for _ in range(count)]


def model_config_build_parity(*, cases: list[ConfigBuildCase]) -> ModelConfigBuildParity:
    """Build natively and in Python; native may defer but never differ or hide an error."""

    outcomes: list[tuple[object, object, object]] = [
        (case.model_file.header_values, _python_build(case), _native_build(case)) for case in cases
    ]
    return ModelConfigBuildParity(
        mismatches=list(
            compress(
                outcomes,
                [native not in (_DEFERRED, python) for _, python, native in outcomes],
            )
        ),
        built=sum(native not in (_DEFERRED, _RAISES) for _, _, native in outcomes),
        deferred=sum(native == _DEFERRED for _, _, native in outcomes),
        python_raised=sum(python == _RAISES for _, python, _ in outcomes),
    )


def _config_build_case(*, rng: random.Random) -> ConfigBuildCase:
    keys: list[str] = rng.sample(sorted(_HEADER_POOLS), k=rng.choice((0, 1, 2, 3, 4)))
    return ConfigBuildCase(
        project_config=ProjectConfig(
            name="orders",
            adapter="duckdb",
            defaults=rng.choice(_DEFAULTS),
            path_defaults=rng.choice(_PATH_DEFAULTS),
            materialization_defaults=rng.choice(_MATERIALIZATION_DEFAULTS),
        ),
        target_config=rng.choice(_TARGETS),
        effective_target_name=rng.choice(("dev", None)),
        model_file=_model_file(
            relative_path=rng.choice(_MODEL_PATHS),
            header_values={key: rng.choice(_HEADER_POOLS[key]) for key in keys},
        ),
    )


def _python_build(case: ConfigBuildCase) -> object:
    with COMPILE_INPUT_READS.recording() as reads:
        try:
            matched: str | None = find_matching_path_default(
                model_file=case.model_file, path_defaults=case.project_config.path_defaults
            )
            config: CompileModelConfig = build_model_config(
                request=ModelConfigBuildRequest(
                    defaults=case.project_config.defaults,
                    path_defaults=case.project_config.path_defaults,
                    matched_path_default=matched,
                    model_header_values=case.model_file.header_values,
                    effective_vars={"region": "emea"},
                    target_config=case.target_config,
                    model_name=case.model_file.file_path.stem,
                    effective_target_name=case.effective_target_name,
                    run_id=_RUN_ID,
                    materialization_defaults=case.project_config.materialization_defaults,
                )
            )
        except Exception:  # noqa: BLE001 - every Python failure must stop the native build too
            return _RAISES
    return (_config_shape(config), reads.environment_names, reads.read_run_id)


def _native_build(case: ConfigBuildCase) -> object:
    session: NativeModelConfigSession = _session(
        project_config=case.project_config,
        target_config=case.target_config,
        effective_target_name=case.effective_target_name,
    )
    with COMPILE_INPUT_READS.recording() as reads:
        try:
            matched: str | None = native_path_default(session=session, model_file=case.model_file)
        except Exception:  # noqa: BLE001 - path conflicts are reported by Python
            return _RAISES
        config: CompileModelConfig | None = build_native_model_config(
            session=session, model_file=case.model_file, matched_path_default=matched
        )
    shapes: list[object] = [
        (_config_shape(built), reads.environment_names, reads.read_run_id)
        for built in cast(list[CompileModelConfig], list(compress([config], [config is not None])))
    ]
    return (*shapes, _DEFERRED)[0]


def _config_shape(config: CompileModelConfig) -> tuple[object, ...]:
    items: list[tuple[str, object]] = list(config.values.items())
    hooks: list[bool] = [key in _HOOK_KEYS for key, _ in items]
    return (
        list(compress(items, [not hook for hook in hooks])),
        sorted(compress(items, hooks), key=itemgetter(0)),
        replace(config, values={}),
    )


def _session(
    *,
    project_config: ProjectConfig,
    target_config: TargetConfig | None,
    effective_target_name: str | None,
) -> NativeModelConfigSession:
    return native_model_config_session(
        inputs=NativeModelConfigInputs(
            project_config=project_config,
            target_config=target_config,
            effective_vars={"region": "emea"},
            effective_target_name=effective_target_name,
            run_id=_RUN_ID,
            microbatch_concurrency=False,
        ),
        names=_NAMES,
    )


def _model_file(*, relative_path: str, header_values: dict[str, object]) -> DiscoveredSqlModelFile:
    return DiscoveredSqlModelFile(
        file_path=Path("/project/models") / relative_path,
        relative_path=Path("models") / relative_path,
        contents="",
        header_values=header_values,
        header_column_locations={},
        output_column_locations={},
        query_sql="SELECT 1",
    )
