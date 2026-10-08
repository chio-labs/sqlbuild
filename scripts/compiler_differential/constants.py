"""Stable constants for the compiler engine differential harness."""

import json
import re

from scripts.compiler_differential.models import DifferentialCommand, ExpectedOutcome

ENGINE_ENV_VAR: str = "SQLBUILD_COMPILER_ENGINE"
STAGE_CAPTURE_ENV_VAR: str = "SQLBUILD_COMPILER_STAGE_CAPTURE_DIR"
ANALYSIS_RECORD_ENV_VAR: str = "SQLBUILD_ANALYSIS_RECORD_DIR"
WHEEL_SITE_RECORD_PREFIX: str = "polyglot-sites-"
ANALYSIS_DEFERRAL_RECORD_PREFIX: str = "analysis-deferrals-"
RECORDS_DIRECTORY: str = "records"
ENGINE_NAMES: tuple[str, ...] = ("python", "native", "native-preview")
DEFAULT_ENGINES: tuple[str, str] = ("python", "native-preview")
SQB_ENTRY: str = "import sys; from sqlbuild.cli.entry.main.entry import main; sys.exit(main())"
EXCLUDED_ENVIRONMENT_KEYS: frozenset[str] = frozenset(
    {"VIRTUAL_ENV", ENGINE_ENV_VAR, STAGE_CAPTURE_ENV_VAR, ANALYSIS_RECORD_ENV_VAR}
)
EXCLUDED_ENVIRONMENT_PREFIX: str = "DBT_"
PROJECT_CONFIG_FILE: str = "sqlbuild_project.toml"
DUCKDB_ADAPTER: str = "duckdb"
PROJECT_DIRECTORY: str = "project"
CAPTURES_DIRECTORY: str = "captures"
LEFT_SIDE: str = "left"
RIGHT_SIDE: str = "right"
TARGET_DIRECTORY: str = "target"
COMPILED_DIRECTORY: str = "target/compiled"
MANIFEST_FILE: str = "target/manifest.json"
DAG_FILE: str = "target/sqlbuild_dag.json"
STRIPPED_REPORT_FIELDS: frozenset[str] = frozenset({"compile_timings", "compiler_engine"})
MANIFEST_VOLATILE_METADATA: frozenset[str] = frozenset({"generated_at", "invocation_id"})
ELAPSED_TIME_PATTERN: re.Pattern[str] = re.compile(r"\b\d+(?:\.\d+)?\s?m?s\b")
ELAPSED_TIME_MASK: str = "<elapsed>"
COMMAND_TIMEOUT_SECONDS: float = 900.0
VALUE_PREVIEW_CHARACTERS: int = 160
MISSING_VALUE: str = "<missing>"
DEFAULT_SEED_COUNT: int = 12
PLAN_LABEL: str = "plan"
ERROR_SEVERITY: str = "error"
WARNING_SEVERITY: str = "warning"
MODEL_RESOURCE_TYPE: str = "model"
DEFAULT_DENSE_MODELS: int = 3000
FIXTURE_ROOT: str = "tests/e2e/fixtures"
EXAMPLE_ROOT: str = "website/examples"
FIXTURE_PROJECT_SUBDIRECTORIES: dict[str, str] = {"dbt_interop": "sqlbuild_project"}
EXPECT_SUCCESS: ExpectedOutcome = ExpectedOutcome()
EXPECT_SUCCESS_VALUE: str = "success"
EXPECT_FAILURE_PREFIX: str = "failure:"
FIXTURE_EXPECTED_OUTCOMES: dict[str, ExpectedOutcome] = {
    "dbt_interop": ExpectedOutcome(error_code="C214")
}
CORPUS_FIXTURES: str = "fixtures"
CORPUS_EXAMPLES: str = "examples"
CORPUS_SEEDS: str = "seeds"
CORPUS_FAILURES: str = "failures"
CORPUS_DENSE: str = "dense"
CORPUS_NAMES: tuple[str, ...] = (
    CORPUS_FIXTURES,
    CORPUS_EXAMPLES,
    CORPUS_SEEDS,
    CORPUS_FAILURES,
    CORPUS_DENSE,
)
PER_PULL_REQUEST_CORPORA: tuple[str, ...] = (
    CORPUS_FIXTURES,
    CORPUS_EXAMPLES,
    CORPUS_SEEDS,
    CORPUS_FAILURES,
)
CUSTOM_RULE_FILE: str = "rules/order_names.py"
CUSTOM_RULE_SOURCE: str = """from sqlbuild.rules import Finding, Model, RuleContext, rule


@rule(
    code="XSQBRDIFF001",
    message="Model names stay below sixty characters",
    remediation="Rename the model.",
)
def short_model_names(*, model: Model, ctx: RuleContext) -> list[Finding]:
    if len(model.name) < 60:
        return []
    return [ctx.finding(subject=model)]
"""
CUSTOM_RULE_THRESHOLDS: str = "\n[rules.thresholds]\nmin_custom_rule_test_cases = 0\n"
COLD_COMPILE: DifferentialCommand = DifferentialCommand(
    label="compile", arguments=("compile", "--json", "--manifest", "--dag")
)
WARM_COMPILE: DifferentialCommand = DifferentialCommand(
    label="compile-warm", arguments=("compile", "--json")
)
STORE_WARM_COMPILE: DifferentialCommand = DifferentialCommand(
    label="compile-store-warm",
    arguments=("compile", "--json"),
    environment=(("SQLBUILD_DISABLE_COMPILE_REUSE", "1"),),
)
PLAN: DifferentialCommand = DifferentialCommand(label=PLAN_LABEL, arguments=("plan", "--json"))

GENERATOR_DOMAINS: tuple[str, ...] = ("sales", "inventory", "support", "fulfillment", "billing")
GENERATOR_LAYERS: tuple[str, ...] = ("staging", "marts")
GENERATOR_SOURCE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("id", "INTEGER"),
    ("amount", "DOUBLE"),
    ("status", "VARCHAR"),
    ("created_at", "TIMESTAMP"),
)
GENERATOR_STATUS_VALUES: tuple[tuple[str, str], ...] = (
    ("PLACED", "placed"),
    ("SHIPPED", "expédié"),
    ("CANCELLED", "取消"),
    ("RETURNED", "returned ✓"),
)
GENERATOR_NON_ASCII_LABELS: tuple[str, ...] = (
    "Zürich – depot",
    "東京 warehouse",
    "café ☕ counter",
    "naïve résumé",
    "Ελληνικά orders",
)
GENERATOR_FLOAT_VALUES: tuple[str, ...] = ("0.15", "1e-07", "12345.678", "0.1", "2.5e+20", "-3.75")
GENERATOR_REGION_ENV_VAR: str = "SQB_DIFFERENTIAL_REGION"
GENERATOR_INVALID_SHARE: float = 0.25
GENERATOR_INVALID_CODES: dict[str, str] = {
    "unknown_ref": "P001",
    "unknown_macro": "P001",
    "failing_macro": "P001",
    "unknown_enum_member": "P001",
    "unknown_constant": "P001",
    "missing_description": "P010",
    "duplicate_macro": "P001",
    "header_syntax": "D002",
    "over_broad_constant": "S024",
}
GENERATOR_HALF: float = 0.5
GENERATOR_CROSS_DOMAIN_SHARE: float = 0.4
GENERATOR_NON_ASCII_DESCRIPTION_SHARE: float = 0.3
GENERATOR_VARIABLE_SHARE: float = 0.3

FAILURE_BASE_CONFIG: str = (
    'name = "failure_corpus"\nadapter = "duckdb"\n\n[connection]\ndatabase = "failure.duckdb"\n'
)
FAILURE_BASE_SOURCES: str = """sources:
  - name: raw_orders
    description: Orders feed.
    expression: >-
      (SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,
      'placed' AS status)
    columns:
      - name: order_id
        type: INTEGER
      - name: customer_id
        type: INTEGER
      - name: amount
        type: DOUBLE
      - name: status
        type: VARCHAR
"""
FAILURE_BASE_STAGING: str = """MODEL (
  description "Staged orders",
);

SELECT order_id, customer_id, amount, status
FROM __source("raw_orders")
"""
FAILURE_BASE_MART: str = """MODEL (
  description "Order totals per customer",
);

SELECT customer_id, SUM(amount) AS total_amount
FROM __ref("stg_orders")
GROUP BY customer_id
"""
FAILURE_BASE_FILES: dict[str, str] = {
    "sqlbuild_project.toml": FAILURE_BASE_CONFIG,
    "sources/raw.yml": FAILURE_BASE_SOURCES,
    "models/staging/stg_orders.sql": FAILURE_BASE_STAGING,
    "models/marts/customer_totals.sql": FAILURE_BASE_MART,
}
FAILURE_STAGING_PATH: str = "models/staging/stg_orders.sql"
FAILURE_MART_PATH: str = "models/marts/customer_totals.sql"
FAILURE_CONFIG_PATH: str = "sqlbuild_project.toml"
FAILURE_SOURCES_PATH: str = "sources/raw.yml"
GENERATOR_ENUM_KIND: str = "enum"
GENERATOR_CONSTANT_KIND: str = "constant"
GENERATOR_MACRO_KIND: str = "macro"
GENERATOR_HOOK_KIND: str = "hook"
GENERATOR_ROLES: dict[str, str] = {
    GENERATOR_ENUM_KIND: "enums",
    GENERATOR_CONSTANT_KIND: "constants",
    GENERATOR_MACRO_KIND: "macros",
    GENERATOR_HOOK_KIND: "hooks",
}
GENERATOR_RENDER_BLOCKS: tuple[str, ...] = (
    "macro_context_reads",
    "typed_reference_macro",
    "macro_generated_reference",
    "table_function",
    "interpolation",
    "cursor_bounds",
    "macros_across_resources",
    "enum_column_contract",
    "resource_audits",
    "model_config",
)
GENERATOR_ANALYSIS_BLOCKS: tuple[str, ...] = (
    "column_shapes",
    "contract_chain",
    "udf_signatures",
    "dynamic_columns",
    "quoted_identifiers",
    "metadata_checks",
    "sql_test_mocks",
    "analysis_opt_out",
    "python_sql",
    "analysis_modes",
)
GENERATOR_FEATURE_BLOCKS: tuple[str, ...] = (
    "incremental_append",
    "incremental_delete_insert",
    "incremental_merge",
    "microbatch_watermark",
    "microbatch_rolling_window",
    "snapshot_timestamp",
    "snapshot_check",
    "python_hook",
    "managed_source_loader",
    "asset_and_check",
    "audit_factory",
    "provider",
    "lifecycle_sink",
    "command_output_sink",
    "custom_materialization",
    "project_adapter",
    "model_schema",
    "list_constant",
    "cross_file_macro_import",
    "macro_test_mode",
    "parameterized_test",
    "generic_audit",
    "functions",
    "local_config",
    "target_override",
    "dbt_ref",
    "line_endings",
    *GENERATOR_RENDER_BLOCKS,
    *GENERATOR_ANALYSIS_BLOCKS,
)
GENERATOR_FEATURE_STRIDE: int = 4
GENERATOR_OPTIONAL_FEATURE_SHARE: float = 0.2
GENERATOR_RARE_FEATURE_PERIOD: int = 12
GENERATOR_RARE_FEATURE_BLOCKS: dict[str, int] = {"dbt_ref": 1}
GENERATOR_DBT_REF_ERROR_CODE: str = "C214"
GENERATOR_FEATURE_FOLDER: str = "models/features"
GENERATOR_RENDER_FOLDER: str = "models/rendering"
GENERATOR_RENDER_TEST_FOLDER: str = "tests/unit/rendering"
GENERATOR_ANALYSIS_FOLDER: str = "models/analysis"
GENERATOR_ANALYSIS_TEST_FOLDER: str = "tests/unit/analysis"
GENERATOR_OPEN_SOURCE: str = "open_events"
GENERATOR_DIALECT_CONNECTIONS: dict[str, tuple[str, ...]] = {
    "postgres": ('host = "localhost"', 'database = "generated"'),
    "snowflake": ('account = "example"', 'user = "builder"', 'database = "GENERATED"'),
}
GENERATOR_DIALECT_TARGETS: dict[str, tuple[str, ...]] = {"snowflake": ('database = "GENERATED"',)}
GENERATOR_DIALECT_EXCLUDED_BLOCKS: frozenset[str] = frozenset(
    {"dynamic_columns", "quoted_identifiers", "analysis_modes"}
)
GENERATOR_DIALECT_BLOCKS: tuple[str, ...] = tuple(
    block for block in GENERATOR_ANALYSIS_BLOCKS if block not in GENERATOR_DIALECT_EXCLUDED_BLOCKS
)
GENERATOR_SELECTED_MODEL: str = "{model}"
GENERATOR_ANALYSIS_MODE_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("compile-select", ("compile", "--json", "--select", GENERATOR_SELECTED_MODEL)),
    ("compile-no-analysis", ("compile", "--json", "--no-sql-analysis")),
    ("compile-rich-lineage", ("compile", "--json", "--lineage-mode", "rich")),
)
GENERATOR_CHANNEL_ENV_VAR: str = "SQB_DIFFERENTIAL_CHANNEL"
GENERATOR_MISSING_ENV_VAR: str = "SQB_DIFFERENTIAL_UNSET"
GENERATOR_ENVIRONMENT: dict[str, str] = {GENERATOR_CHANNEL_ENV_VAR: "web-orders"}
GENERATOR_PROJECT_ADAPTER: str = "generated_duckdb"
GENERATOR_CRLF: str = "\r\n"
GENERATOR_BOM: str = "\ufeff"
GENERATOR_DBT_MODEL: str = "upstream_orders"
GENERATOR_DBT_MANIFEST: str = (
    json.dumps(
        {
            "metadata": {"dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json"},
            "nodes": {
                f"model.upstream.{GENERATOR_DBT_MODEL}": {
                    "resource_type": "model",
                    "package_name": "upstream",
                    "name": GENERATOR_DBT_MODEL,
                    "database": "generated",
                    "schema": "upstream",
                    "alias": GENERATOR_DBT_MODEL,
                    "fqn": ["upstream", GENERATOR_DBT_MODEL],
                    "checksum": {"name": "sha256", "checksum": "0" * 64},
                    "depends_on": {"nodes": []},
                    "config": {"materialized": "table"},
                    "columns": {
                        "order_id": {"name": "order_id", "data_type": "integer"},
                        "customer_id": {"name": "customer_id", "data_type": "integer"},
                    },
                    "compiled_code": "SELECT 1 AS order_id, 10 AS customer_id",
                }
            },
            "sources": {},
        },
        indent=2,
    )
    + "\n"
)
GENERATOR_SUFFIXES: dict[str, str] = {
    GENERATOR_ENUM_KIND: ".sql",
    GENERATOR_CONSTANT_KIND: ".sql",
    GENERATOR_MACRO_KIND: ".py",
}
DISCOVERY_STAGE_CAPTURE_SUFFIX: str = "-discovered_project_inputs.json"
DISCOVERY_NON_COLLECTION_FIELDS: frozenset[str] = frozenset(
    {"project_config", "local_config", "project_dir", "native_session"}
)
DISCOVERY_DECLARATION_FILE_COLLECTIONS: tuple[str, ...] = (
    "enum_files",
    "constant_files",
    "model_schema_files",
    "sql_hook_files",
    "audit_files",
    "macro_files",
    "hook_functions",
)
DISCOVERY_TEXT_FILE_COLLECTIONS: tuple[str, ...] = (
    "model_files",
    "enum_files",
    "constant_files",
    "model_schema_files",
    "sql_function_files",
    "sql_hook_files",
    "python_function_files",
    "schema_files",
    "source_files",
    "test_files",
    "scenario_files",
    "audit_files",
    "macro_files",
)
DISCOVERY_DETAIL_KINDS: tuple[str, ...] = (
    "incremental_append",
    "incremental_delete_insert",
    "incremental_merge",
    "microbatch_watermark",
    "microbatch_rolling_window",
    "snapshot_timestamp",
    "snapshot_check",
    "custom_materialized_model",
    "model_local_declaration",
    "dbt_ref_model",
    "dbt_target_path_config",
    "managed_source",
    "unmanaged_source",
    "scope_global",
    "scope_inherited",
    "scope_local",
    "constant_string",
    "constant_integer",
    "constant_boolean",
    "constant_float",
    "constant_decimal",
    "constant_list",
    "non_ascii_constant",
    "enum_string",
    "enum_integer",
    "cross_file_macro_import",
    "test_mode_model",
    "test_mode_macro",
    "test_mode_udf",
    "parameterized_test",
    "singular_audit",
    "generic_audit",
    "path_defaults",
    "local_config",
    "target_override",
    "project_adapter_config",
    "crlf",
    "tab",
    "bom",
    "non_ascii_comment",
    "non_ascii_string",
)
MICROBATCH_MODE: str = "microbatch"
STRATEGY_HEADER_KEYS: dict[str, str] = {
    "incremental": "incremental_strategy",
    "snapshot": "snapshot_strategy",
}
DBT_REF_CALL: str = "__dbt_ref("
SINGULAR_AUDIT_KIND: str = "singular_audit"
TAB: str = "\t"
CRLF_BYTES: bytes = b"\r\n"
TYPE_MARKER: str = "__type__"
CALLABLE_MARKER: str = "__callable__"
UNCANONICAL_CAPTURE_MARKERS: tuple[str, ...] = ("__opaque__", "__cycle__")
CALLABLE_CAPTURE_FIELDS: frozenset[str] = frozenset({"function", "provider_class"})
COLLECTION_CAPTURE_MARKERS: frozenset[str] = frozenset(
    {"__set__", "__mapping__", "__unordered_mapping__"}
)
PATH_MARKER: str = "__path__"
RELATIVE_PATH_FIELDS: frozenset[str] = frozenset({"relative_path"})
CONFIG_ONLY_KINDS: dict[str, str] = {
    "project_adapter_config": (
        "the config names a non-built-in adapter; adapters/ modules are resolved after "
        "discovery and are not in the capture"
    ),
    "dbt_target_path_config": (
        "the config sets [dbt] target_path; the manifest is read after discovery"
    ),
}
RENDER_STAGE_CAPTURE_SUFFIX: str = "-compile_project_inputs.json"
RENDER_NON_COLLECTION_FIELDS: frozenset[str] = frozenset(
    {
        "project_config",
        "local_config",
        "discovered_inputs",
        "sql_lexical_syntax",
        "run_id",
        "effective_target_name",
        "effective_target",
        "compile_cache_dir",
        "effective_connection",
        "effective_settings",
        "no_sql_validation",
        "effective_vars",
        "macro_context",
        "diagnostics",
        "external_sql_reference_resolver",
        "scope_index",
        "declaration_scope",
        "analysis_reuse",
    }
)
RENDER_CALLABLE_CAPTURE_FIELDS: frozenset[str] = CALLABLE_CAPTURE_FIELDS
TYPED_REFERENCE_ANNOTATION: str = "SqlResourceRef"
RENDER_HOOK_KEYS: tuple[str, ...] = ("pre_hooks", "post_hooks")
RENDER_MACRO_SOURCE_READS: dict[str, tuple[str, ...]] = {
    "macro_reads_vars": ("ctx.vars",),
    "macro_reads_constants": ("ctx.constants", "ctx.render_constant"),
    "macro_reads_enums": ("ctx.enums", "ctx.render_enum_member"),
    "macro_reads_target": ("ctx.target_name", "ctx.adapter_name"),
    "macro_reads_environment": ("os.environ",),
}
RENDER_DETAIL_KINDS: tuple[str, ...] = (
    "macro_in_model",
    "macro_in_test",
    "macro_in_scenario",
    "macro_in_audit",
    "macro_in_function",
    "macro_in_source_expression",
    "macro_in_hook",
    "nested_macro_call",
    "typed_reference_argument",
    "macro_generated_reference",
    "cross_file_macro_import",
    "tested_macro",
    *RENDER_MACRO_SOURCE_READS,
    "scope_global_use",
    "scope_inherited_use",
    "scope_local_use",
    "scope_private_use",
    "enum_member",
    "scalar_constant",
    "list_constant",
    "expected_model_grant",
    "enum_column_contract",
    "project_variable",
    "environment_variable",
    "runtime_placeholder",
    "cursor_intrinsic",
    "source_expression_rendered",
    "audit_arguments",
    "python_hook",
    "named_sql_hook",
    "inline_sql_hook",
    "hook_context_variable",
    "named_hook_arguments",
    "reference_ref",
    "reference_source",
    "reference_seed",
    "reference_udf",
    "reference_table_function",
    "reference_dbt_ref",
    "model_test",
    "macro_test",
    "udf_test",
    "parameterized_test_case",
    "singular_audit",
    "model_audit",
    "model_column_audit",
    "source_column_audit",
    "seed_column_audit",
    "path_default",
    "model_header_template",
    "target_namespace_template",
    "model_column_audit_options",
)
RENDER_INDIRECT_KINDS: dict[str, str] = {
    kind: "the used macro's own function source reads it; the capture does not record context reads"
    for kind in RENDER_MACRO_SOURCE_READS
}
RENDER_CONFIG_ONLY_KINDS: dict[str, str] = {}
DIAGNOSTIC_CODE_PATTERN: re.Pattern[str] = re.compile(r"[A-Z][0-9]{3}")
RENDER_RAISED_CODES: frozenset[str] = frozenset({"C214", "C216", "K012"})
RENDER_CODE_SCAN_EXCLUDED: dict[str, str] = {
    "_helpers/assembly": "semantic and metadata validation of the assembled CompiledProject (M4)",
    "_helpers/analysis": "SQL analysis of rendered SQL, after the CompileProjectInputs frontier",
}
_SCOPE_QUERY_ONLY: str = "reported only by sqb scope queries, never by compile"
_TOLERANT_SCOPE_ONLY: str = (
    "reported only by the tolerant index sqb scope builds; compile discovery fails first "
    "with a D-code"
)
_NEVER_EMITTED: str = "defined in ScopeDiagnosticCode but no compiler path reports it"
_FOLDED_INTO_P001: str = (
    "compile raises the strict scope index error, which reports it inside a P001 "
    "'Invalid declaration scope index' message"
)
DISCOVERY_UNREACHABLE_CODES: dict[str, str] = {
    "D017": ("the corpus runs a supported Python; an integration test forces an unsupported one"),
}
RENDER_UNREACHABLE_CODES: dict[str, str] = {
    "S001": _SCOPE_QUERY_ONLY,
    "S002": _SCOPE_QUERY_ONLY,
    "S003": _FOLDED_INTO_P001,
    "S004": "discovery rejects the identity first with D016",
    "S005": "discovery rejects the identity first with D016",
    "S011": _SCOPE_QUERY_ONLY,
    "S012": _NEVER_EMITTED,
    "S013": _SCOPE_QUERY_ONLY,
    "S014": _SCOPE_QUERY_ONLY,
    "S015": _NEVER_EMITTED,
    "S016": _NEVER_EMITTED,
    "S017": _NEVER_EMITTED,
    "S018": "discovery rejects the duplicate resource first with D007",
    "S019": _TOLERANT_SCOPE_ONLY,
    "S020": _TOLERANT_SCOPE_ONLY,
    "S021": _TOLERANT_SCOPE_ONLY,
    "S022": _TOLERANT_SCOPE_ONLY,
    "S023": _TOLERANT_SCOPE_ONLY,
}
ANALYSIS_STAGE_CAPTURE_SUFFIX: str = "-compiled_project.json"
COMPILED_PROJECT_CAPTURE_TYPE: str = "sqlbuild.compiler.compile.models:CompiledProject"
ANALYSIS_NON_COLLECTION_FIELDS: frozenset[str] = frozenset(
    {
        "run_id",
        "effective_target_name",
        "effective_connection",
        "effective_vars",
        "binding_catalog",
        "effective_target_database",
        "effective_target_schema",
        "sql_analysis_dialect",
        "sql_lexical_syntax",
        "compile_cache_dir",
        "settings",
        "scenario",
        "enforce_explicit_references",
        "diagnostics",
        "external_sql_reference_resolver",
        "scope_index",
        "native_session",
    }
)
ANALYSIS_CALLABLE_CAPTURE_FIELDS: frozenset[str] = CALLABLE_CAPTURE_FIELDS
ANALYSIS_OPAQUE_CAPTURE_VALUES: re.Pattern[str] = re.compile(
    r'\{"__opaque__":\s*"sqlbuild\._native:ProjectCatalog"\}'
)
ANALYSIS_EXPLICIT_WRITE_SCHEMA_DIALECTS: frozenset[str] = frozenset({"snowflake"})
ANALYSIS_DIALECT_VARIANTS: tuple[str, ...] = ("postgres", "snowflake")
ANALYSIS_UPSTREAM_CHAIN_HOPS: int = 3
ANALYSIS_DETAIL_KINDS: tuple[str, ...] = (
    "typed_column",
    "untyped_column",
    "star_over_complete_input",
    "star_over_published_shape",
    "star_unresolved",
    "set_operation",
    "cte",
    "cte_passthrough_type",
    "quoted_identifier_case",
    "dynamic_column_proof",
    "cursor_intrinsic",
    "runtime_placeholder",
    "batch_binding",
    "dataflow_binding",
    "select_limited_analysis",
    "sql_analysis_disabled",
    "upstream_chain",
    "sized_contract_shape",
    "contract_nullability_shape",
    "source_expression_shape",
    "seed_column_types",
    "scalar_udf",
    "table_function",
    "udf_argument_types",
    "sql_analysis_opt_out",
    "inline_sql_hook",
    "named_sql_hook",
    "hook_list",
    "explicit_promotion_mode",
    "python_sql_literal_relation",
    "managed_write_schema",
    "accepted_values_audit",
    "relationships_audit",
    "expression_audit",
    "metadata_column_reference",
    "sql_test_expected_columns",
    "sql_test_macro_mock",
    "dialect_duckdb",
    "dialect_postgresql",
    "dialect_snowflake",
)
ANALYSIS_INDIRECT_KINDS: dict[str, str] = {
    "managed_write_schema": (
        "every destination resolved an explicit schema under an adapter that requires one; "
        "the capture does not record the write-schema check itself"
    ),
}
ANALYSIS_CODE_SCAN_ROOTS: tuple[str, ...] = (
    "compile/_helpers/assembly",
    "compile/_helpers/analysis",
    "compile/_helpers/diagnostics",
    "contracts",
    "pipeline/_helpers/target_validation.py",
    "sql_analysis",
)
_NEVER_REPORTED_BY_POLYGLOT: str = (
    "polyglot defines the finding but never reports it, and no SQLBuild check maps to it"
)
ANALYSIS_UNREACHABLE_CODES: dict[str, str] = {
    "B000": (
        "the binding layer's internal unknown-relation code; compile drops it because an "
        "unknown relation is an open input"
    ),
    "B210": _NEVER_REPORTED_BY_POLYGLOT,
    "B214": (
        "polyglot reports assignment types only for INSERT statements; compiled models, tests "
        "and audits are queries"
    ),
    "B219": _NEVER_REPORTED_BY_POLYGLOT,
    "P003": (
        "the contract check raises it for a declared column without a type, which it skips "
        "first; compile reports P003 only as the built-in audit shadow warning"
    ),
}
