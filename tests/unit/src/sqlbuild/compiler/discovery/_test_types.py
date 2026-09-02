from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoverProjectInputsTestCase:
    description: str
    repo_files: dict[str, str]
    expected_model_paths: tuple[str, ...]
    expected_model_header_values: tuple[dict[str, object], ...]
    expected_model_query_sql: tuple[str, ...]
    expected_schema_paths: tuple[str, ...]
    expected_schema_model_names: tuple[tuple[str, ...], ...]
    expected_schema_seed_names: tuple[tuple[str, ...], ...]
    expected_source_paths: tuple[str, ...]
    expected_source_entry_names: tuple[tuple[str, ...], ...]
    expected_seed_paths: tuple[str, ...]
    expected_test_paths: tuple[str, ...]
    expected_test_block_indexes: tuple[int, ...]
    expected_test_block_names: tuple[str | None, ...]
    expected_test_block_sql_bodies: tuple[str, ...]
    expected_scenario_paths: tuple[str, ...]
    expected_scenario_names: tuple[str, ...]
    expected_scenario_header_values: tuple[dict[str, object], ...]
    expected_scenario_sql_bodies: tuple[str, ...]
    expected_audit_paths: tuple[str, ...]
    expected_audit_block_indexes: tuple[int, ...]
    expected_audit_block_names: tuple[str | None, ...]
    expected_audit_block_sql_bodies: tuple[str, ...]
    expected_macro_paths: tuple[str, ...]
    expected_loader_names: tuple[str, ...]
    expected_adapter_path: str | None
    expected_task_names: tuple[str, ...] = ()
    expected_asset_names: tuple[str, ...] = ()
    expected_check_names: tuple[str, ...] = ()
    expected_hook_names: tuple[str, ...] = ()
    expected_provider_names: tuple[str, ...] = ()
    expected_provider_paths: tuple[str, ...] = ()
    expected_provider_class_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoverProjectInputsErrorTestCase:
    description: str
    repo_files: dict[str, str]
    expected_error_fragment: str


@dataclass(frozen=True)
class DiscoverFactoryValidationTestCase:
    description: str
    repo_files: dict[str, str]
    expected_loader_names: tuple[str, ...] = ()
    expected_task_names: tuple[str, ...] = ()
    expected_asset_names: tuple[str, ...] = ()
    expected_check_names: tuple[str, ...] = ()
    expected_error_fragment: str = ""


@dataclass(frozen=True)
class DiscoveryLifecycleTestCase:
    description: str
    expected_event_types: tuple[str, ...]
    expected_operation_names: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveryRelevantCountTestCase:
    description: str
    expected_item_count: int
    unexpected_root_pattern: str
