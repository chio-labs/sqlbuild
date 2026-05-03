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
    expected_seed_paths: tuple[str, ...]
    expected_test_paths: tuple[str, ...]
    expected_test_block_indexes: tuple[int, ...]
    expected_test_block_names: tuple[str | None, ...]
    expected_test_block_sql_bodies: tuple[str, ...]
    expected_audit_paths: tuple[str, ...]
    expected_audit_block_indexes: tuple[int, ...]
    expected_audit_block_names: tuple[str | None, ...]
    expected_audit_block_sql_bodies: tuple[str, ...]
    expected_macro_paths: tuple[str, ...]
    expected_manifest_path: str | None
    expected_adapter_path: str | None
