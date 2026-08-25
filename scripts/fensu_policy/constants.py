"""Stable constants for SQLBuild custom Fensu rules."""

ADAPTER_CLASS_BOUNDARIES: frozenset[str] = frozenset(
    {"_helpers", "classes", "models", "types", "constants", "exceptions", "shared"}
)
ADAPTER_CLASS_BYPASS_MODULES: frozenset[str] = frozenset(
    {"main.py", "models.py", "types.py", "constants.py", "exceptions.py", "helpers.py"}
)
ALLOWED_COMMENT_PREFIXES: tuple[str, ...] = (
    "#!",
    "# -*-",
    "# coding:",
    "# noqa",
    "# type: ignore",
    "# pyright:",
    "# pylint:",
    "# pragma:",
    "# sc: allow-param-mutation",
)
ALLOWED_MACRO_LOAD_PATHS: frozenset[str] = frozenset(
    {
        "src/sqlbuild/compiler/compile/main/_build_compile_inputs.py",
        "src/sqlbuild/compiler/compile/main/load_macros.py",
        "src/sqlbuild/compiler/compile/_helpers/render/macros.py",
    }
)
ALLOWED_PARAMETER_MUTATION_COMMENT: str = "# sc: allow-param-mutation"
ALLOWED_SOURCE_FRESHNESS_INSERT_PREFIXES: tuple[str, ...] = (
    "scripts/fensu_policy/",
    "src/sqlbuild/adapter/",
    "src/sqlbuild/adapters/",
    "src/sqlbuild/virtual/state/classes/",
)
ALLOWED_DBT_REF_SCAN_PATHS: frozenset[str] = frozenset(
    {
        "src/sqlbuild/integrations/dbt/_helpers/manifest/sqlbuild_refs.py",
        "src/sqlbuild/integrations/dbt/_helpers/manifest/compile_refs.py",
    }
)
ALLOWED_METADATA_LOOP_PATHS: frozenset[str] = frozenset(
    {
        "src/sqlbuild/adapter/relations/main/relation_lookup.py",
        "src/sqlbuild/compiler/planner/_helpers/output/plan_entry.py",
        "src/sqlbuild/executor/janitor/_helpers/plan.py",
        "src/sqlbuild/executor/pipeline/_helpers/testing.py",
        "src/sqlbuild/executor/run/_helpers/materializations/microbatch.py",
        "src/sqlbuild/integrations/dbt/_helpers/lineage/columns.py",
        "src/sqlbuild/integrations/dbt/_helpers/planning/model_planning.py",
        "src/sqlbuild/virtual/executor/_helpers/clone.py",
    }
)
ALLOWED_SELECTOR_PARSE_PATH: str = (
    "src/sqlbuild/compiler/planner/main/selection/selector_expansion.py"
)
CLIENT_STYLE_PREFIXES: frozenset[tuple[str, ...]] = frozenset(
    {("src", "sqlbuild", "adapters"), ("src", "sqlbuild", "integrations")}
)
DEV_TOOLING_FILE_PREFIXES: tuple[str, ...] = ("check_", "format_", "lint_", "test_")
DEV_TOOLING_SEGMENTS: frozenset[str] = frozenset({"checks", "tooling"})
DISCARDED_CALL_ALLOWED_NAMES: frozenset[str] = frozenset({"print"})
DISCARDED_CALL_ALLOWED_PREFIXES: tuple[str, ...] = (
    "check_",
    "enforce_",
    "validate_",
    "on_",
    "report_",
    "log",
    "write_",
)
FORBIDDEN_GENERIC_FILENAMES: frozenset[str] = frozenset(
    {"base.py", "common.py", "helpers.py", "misc.py"}
)
GLOBAL_REUSE_FORBIDDEN_TERMS: tuple[str, ...] = (
    "source_fingerprint",
    "source_target_name",
    "source_connection",
    "target_cursor",
    "REUSE_RELATION",
    "reuse_relation",
)
GRAPH_KEY_CLASS_NAMES: frozenset[str] = frozenset({"GraphNodeKey", "SelectionStalenessNodeKey"})
MAIN_SUPPORT_PACKAGE_NAMES: frozenset[str] = frozenset({"_helpers", "classes", "shared"})
REUSE_FORBIDDEN_TERMS: tuple[str, ...] = (
    "source_relation",
    "source relation",
    "source/target",
    "source_cursor",
    "target_relation",
    "target relation",
    "target_cursor",
)
REUSE_PATH_MARKERS: tuple[str, ...] = (
    "direct_reuse",
    "reuse_candidates.py",
    "reuse_execute.py",
    "reuse_plan.py",
    "reuse.py",
)
REUSE_TERM_ALLOWED_PATHS: dict[str, frozenset[str]] = {
    "source_target_name": frozenset(
        {"src/sqlbuild/compiler/planner/_helpers/warehouse/source_deferral.py"}
    ),
    "source_connection": frozenset(
        {
            "src/sqlbuild/virtual/executor/_helpers/build.py",
            "src/sqlbuild/virtual/planner/main/plan.py",
        }
    ),
}
SELECTOR_STRING_METHOD_NAMES: frozenset[str] = frozenset(
    {"startswith", "endswith", "lstrip", "rstrip"}
)
SOURCE_FRESHNESS_MARKERS: tuple[str, ...] = ("SOURCE_FRESHNESS", "source_freshness")
SOURCE_FRESHNESS_SINGULAR_WRITER: str = "write_source_freshness_record"
WAREHOUSE_METADATA_METHODS: frozenset[str] = frozenset(
    {
        "list_relations",
        "relation_exists",
        "get_columns",
        "get_all_columns",
        "describe_relation",
        "schema_exists",
        "get_table_freshness_metadata",
        "get_tables_freshness_metadata",
        "query_column_names",
        "list_functions",
    }
)

ABSTRACT_METHOD_DECORATOR_NAME: str = "abstractmethod"
ABC_MODULE_NAME: str = "abc"
ADAPTER_CLASS_MODULE_MIN_PARTS: int = 6
ADAPTER_CONTRACT_CLASSES_PATH: str = "src/sqlbuild/adapter/contract/classes"
ADAPTER_BUILTINS_PATH: str = "src/sqlbuild/adapter/discovery/main/builtins.py"
ADAPTER_IMPLEMENTATION_PATH_MARKERS: tuple[str, str] = ("/adapters/", "/classes/")
ADAPTER_ROOT_PARTS: tuple[str, ...] = ("src", "sqlbuild", "adapter")
ADAPTERS_ROOT_PARTS: tuple[str, ...] = ("src", "sqlbuild", "adapters")
ADAPTER_PACKAGE_IMPORT_PREFIX: str = "sqlbuild.adapters."
BASE_ADAPTER_CLASS_NAME: str = "BaseAdapter"
BASE_ADAPTER_REFERENCE_PART_COUNT: int = 2
CLIENT_MODULE_MIN_PARTS: int = 5
CLIENT_MODULE_NAME: str = "client.py"
CLASSES_PACKAGE_NAME: str = "classes"
COMPILER_EXECUTOR_DOMAIN_NAMES: frozenset[str] = frozenset({"compiler", "executor"})
DBT_INTEGRATION_PATH_PREFIX: str = "src/sqlbuild/integrations/dbt/"
DBT_REF_ATTRIBUTE_NAME: str = "DBT_REF"
HELPERS_PACKAGE_NAME: str = "_helpers"
INIT_MODULE_NAME: str = "__init__.py"
INSERT_SQL_PREFIX: str = "INSERT INTO"
LEGACY_DUCKDB_ADAPTER_SUFFIX: tuple[str, ...] = ("shared", "classes", "duckdb.py")
DUCKDB_BACKED_ADAPTER_PATH: str = "src/sqlbuild/adapter/contract/classes/duckdb_backed_adapter.py"
LOAD_PROJECT_MACROS_NAME: str = "load_project_macros"
NAME_REFERENCE_KIND: str = "name"
MAIN_MODULE_NAME: str = "main.py"
MAIN_PACKAGE_NAME: str = "main"
NESTED_HELPER_MODULE_MIN_PARTS: int = 5
PLANNER_PATH_PREFIX: str = "src/sqlbuild/compiler/planner/"
POLICY_EVALUATION_SCOPES: frozenset[str] = frozenset({"root", "tooling"})
POLICY_IMPLEMENTATION_PATH_PREFIX: str = "scripts/fensu_policy/"
PROVIDER_CLASS_NAME: str = "Provider"
PROVIDER_MODULE_PARTS: tuple[str, ...] = ("src", "sqlbuild", "providers.py")
PUBLIC_COLOR_ENTRY_PARTS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("src", "sqlbuild", "presentation", "main", "supports_color.py"),
        ("src", "sqlbuild", "presentation", "main", "terminal_columns.py"),
    }
)
ROOT_SCOPE_NAME: str = "root"
RUNTIME_ROOT_PARTS: tuple[str, ...] = ("src", "sqlbuild")
SELECTOR_MARKER: str = "+"
STRING_LITERAL_KIND: str = "string"
SQL_REFERENCE_KIND_CLASS_NAME: str = "SqlReferenceKind"
STRICT_ADAPTER_CLASS_NAME: str = "StrictAdapter"
ATTRIBUTE_REFERENCE_KIND: str = "attribute"
