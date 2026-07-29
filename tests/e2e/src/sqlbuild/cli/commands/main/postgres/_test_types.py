from dataclasses import dataclass, field


@dataclass(frozen=True)
class PostgresDependencyBaselineE2ETestCase:
    description: str
    schema_prefix: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_stdout_fragments: tuple[str, ...]
    expected_upstream_rows: tuple[tuple[object, ...], ...]
    expected_downstream_rows: tuple[tuple[object, ...], ...]
    expected_fingerprint_rows: tuple[tuple[object, ...], ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresBuildE2ETestCase:
    description: str
    expected_row_count: int
    expected_table_name: str = "fact_orders"
    command: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresNodeResultE2ETestCase:
    description: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresSourceLoaderStrategiesE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_countries: tuple[tuple[object, ...], ...]
    expected_webhook_event_counts: tuple[tuple[object, ...], ...]
    expected_order_events: tuple[tuple[object, ...], ...]
    expected_customers: tuple[tuple[object, ...], ...]
    expected_loader_status: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresSourceLoaderDagE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresDltE2ETestCase:
    description: str
    expected_loaded_rows: tuple[tuple[object, ...], ...]
    expected_model_rows: tuple[tuple[object, ...], ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresIntermediateDagStrategyE2ETestCase:
    description: str
    loader_py: str
    expected_intermediate_rows: tuple[tuple[object, ...], ...]
    expected_terminal_rows: tuple[tuple[object, ...], ...]
    command: tuple[str, ...] = ("--no-color", "load", "--select", "+raw_events")
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresLoaderWaffleShopE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_event_count: int
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresDiffE2ETestCase:
    description: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresSnapshotE2ETestCase:
    description: str
    expected_current_rows_after_initial_build: tuple[tuple[object, ...], ...]
    expected_current_rows_after_recovery: tuple[tuple[object, ...], ...]
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...]
    expected_historical_check_rows: tuple[tuple[object, ...], ...]
    expected_failure_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PostgresSnapshotApplyE2ETestCase:
    description: str
    expected_current_check_rows: tuple[tuple[object, ...], ...]
    expected_current_delete_rows: tuple[tuple[object, ...], ...]
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...]
    expected_historical_check_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresScenarioLocalReplayE2ETestCase:
    description: str
    model_sql: str
    scenario_sql: str
    expected_stdout_fragments: tuple[str, ...]
    expected_return_code: int = 0
    scenario_name: str = "transpilable_event_rollup"
    expected_local_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    local_rows_sql: str = ""
    corrupt_capture_dialect: bool = False


@dataclass(frozen=True)
class PostgresSourceDeferralE2ETestCase:
    description: str
    expected_model_rows: tuple[tuple[object, ...], ...]
    expected_loader_rows: tuple[tuple[object, ...], ...]
    command: tuple[str, ...] = ("--no-color", "build", "--select", "stg_orders")
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresPartialSourceTypeEnforcementE2ETestCase:
    description: str
    expected_rows: tuple[tuple[object, ...], ...]
    command: tuple[str, ...] = ("--no-color", "build", "--select", "stg_orders")
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresDbtProfileE2ETestCase:
    description: str
    expected_toml_fragments: tuple[str, ...]
    unexpected_toml_fragments: tuple[str, ...]
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]
    expected_noop_fragments: tuple[str, ...]
    expected_plain_selector_block_fragments: tuple[str, ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresStateLifecycleE2ETestCase:
    description: str
    expected_exit_code: int
    expected_schema_version: int
    expected_init_fragment: str = "Virtual State Initialized"
    expected_migrate_fragment: str = "Virtual State Migrated"
    expected_rollback_fragment: str = "Virtual State Rolled Back"
    expected_reset_fragment: str = "Virtual State Reset"


@dataclass(frozen=True)
class PostgresStateAdoptDetachE2ETestCase:
    description: str
    expected_exit_code: int
    expected_rows_after_adopt: tuple[tuple[object, ...], ...]
    expected_rows_after_detach: tuple[tuple[object, ...], ...]
    expected_detached_status: str


@dataclass(frozen=True)
class PostgresStateAdoptDetachErrorE2ETestCase:
    description: str
    expected_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class PostgresReconcileE2ETestCase:
    description: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_exit_code: int = 0
    input_text: str = ""


@dataclass(frozen=True)
class PostgresVirtualSeedE2ETestCase:
    description: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_seed_strategy: str
    incremental_strategy: str = "delete_insert"
    expected_exit_code: int = 0


@dataclass(frozen=True)
class PostgresVirtualRollbackE2ETestCase:
    description: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_checkpoint_count: int
    expected_exit_code: int = 0


@dataclass(frozen=True)
class PostgresVirtualParityE2ETestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_exit_code: int = 0


@dataclass(frozen=True)
class PostgresJanitorDetachedVdeE2ETestCase:
    description: str
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_virtual_environment_count_after: int
    expected_ref_count_after: int


@dataclass(frozen=True)
class PostgresStateLifecycleErrorE2ETestCase:
    description: str
    allow_reset: bool
    command: tuple[str, ...]
    expected_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class PostgresStateExplicitRollbackE2ETestCase:
    description: str
    expected_exit_code: int
    expected_schema_version: int
    expected_rollback_fragment: str = "Virtual State Rolled Back"


@dataclass(frozen=True)
class PostgresStateLocalOverrideE2ETestCase:
    description: str
    expected_exit_code: int
    expected_schema_version: int


@dataclass(frozen=True)
class PostgresStateConnectionErrorE2ETestCase:
    description: str
    expected_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class PostgresStateResetInvalidE2ETestCase:
    description: str
    expected_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class PostgresStateSchemaCorruptionE2ETestCase:
    description: str
    mutation_sql_template: str
    expected_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class PostgresDbtSeedChangeE2ETestCase:
    description: str
    expected_initial_total: int
    expected_changed_total: int
    expected_changed_fragments: tuple[str, ...]
    expected_rerun_fragments: tuple[str, ...]
