"""Stable constants for structure convention checks."""

BANNED_GENERIC_FILENAMES: frozenset[str] = frozenset(
    {"base.py", "common.py", "helpers.py", "misc.py"}
)
DEV_TOOLING_SEGMENTS: frozenset[str] = frozenset({"checks", "tooling"})
DEV_TOOLING_FILE_PREFIXES: tuple[str, ...] = ("check_", "format_", "lint_", "test_")
TYPE_CLASS_BASE_NAMES: frozenset[str] = frozenset(
    {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "NamedTuple", "Protocol", "TypedDict"}
)
MODEL_CLASS_BASE_NAMES: frozenset[str] = frozenset({"BaseModel"})
RAW_BUILTIN_RAISE_NAMES: frozenset[str] = frozenset(
    {
        "AssertionError",
        "Exception",
        "KeyError",
        "NotImplementedError",
        "RuntimeError",
        "TypeError",
        "ValueError",
    }
)
ADAPTER_DOMAIN_NAME: str = "adapter"
ADAPTER_ENTRY_BOUNDARY_NAMES: frozenset[str] = frozenset(
    {
        "_helpers",
        "classes",
        "models",
        "types",
        "constants",
        "exceptions",
        "shared",
    }
)
ADAPTER_ENTRY_BYPASS_MODULE_NAMES: frozenset[str] = frozenset(
    {"main.py", "models.py", "types.py", "constants.py", "exceptions.py", "helpers.py"}
)
ADAPTER_ROOT_PARTS: tuple[str, ...] = ("src", "sqlbuild", "adapter")
ADAPTERS_ROOT_PARTS: tuple[str, ...] = ("src", "sqlbuild", "adapters")
ADAPTERS_PATH_MARKER: str = "/adapters/"
ALL_EXPORT_NAME: str = "__all__"
ANNOTATIONS_FUTURE_FEATURE_NAME: str = "annotations"
BARE_EXCEPTION_CLASS_NAME: str = "Exception"
CLASSES_MODULE_NAME: str = "classes.py"
CLASSES_PACKAGE_NAME: str = "classes"
CLASSES_PATH_MARKER: str = "/classes/"
CLIENT_MODULE_NAME: str = "client.py"
INTEGRATIONS_ROOT_PARTS: tuple[str, ...] = ("src", "sqlbuild", "integrations")
CLIENT_STYLE_ROOT_PARTS: frozenset[tuple[str, ...]] = frozenset(
    {ADAPTERS_ROOT_PARTS, INTEGRATIONS_ROOT_PARTS}
)
COMPILER_EXECUTOR_DOMAIN_NAMES: frozenset[str] = frozenset({"compiler", "executor"})
CONSTANTS_MODULE_NAME: str = "constants.py"
CONSTANTS_PACKAGE_NAME: str = "constants"
CROSS_PACKAGE_PUBLIC_MODULE_NAMES: frozenset[str] = frozenset(
    {"classes", "models", "types", "constants", "exceptions", "__init__", "main"}
)
CROSS_PACKAGE_SOURCE_EXEMPT_DOMAIN_NAMES: frozenset[str] = frozenset({"spec"})
CROSS_PACKAGE_TARGET_EXEMPT_DOMAIN_NAMES: frozenset[str] = frozenset({"spec", "shared"})
DBT_INTEGRATION_PATH_MARKER: str = "src/sqlbuild/integrations/dbt/"
DBT_REF_ATTRIBUTE_NAME: str = "DBT_REF"
DEEP_INTERNAL_PACKAGE_NAMES: frozenset[str] = frozenset({"shared", "_helpers"})
DIRECT_TOP_LEVEL_ROLE_MODULE_NAMES: frozenset[str] = frozenset(
    {"models.py", "types.py", CONSTANTS_MODULE_NAME, "helpers.py", CLASSES_MODULE_NAME}
)
ENTRY_MODULE_EXCLUDED_NAMES: frozenset[str] = frozenset({"__init__.py", "main.py"})
ENTRY_PACKAGE_NAME: str = "entry"
EXCEPTIONS_MODULE_NAME: str = "exceptions.py"
EXCEPTIONS_PACKAGE_NAME: str = "exceptions"
FROZEN_DATACLASS_KEYWORD_NAME: str = "frozen"
FUTURE_MODULE_NAME: str = "__future__"
GRAPH_KEY_CLASS_NAMES: frozenset[str] = frozenset({"GraphNodeKey", "SelectionStalenessNodeKey"})
HELPERS_MODULE_NAME: str = "helpers.py"
HELPERS_PACKAGE_NAME: str = "_helpers"
INIT_MODULE_NAME: str = "__init__.py"
INSERT_SQL_PREFIX: str = "INSERT INTO"
LOAD_PROJECT_MACROS_NAME: str = "load_project_macros"
LEGACY_DUCKDB_ADAPTER_PARTS: tuple[str, ...] = ("shared", "classes", "duckdb.py")
MAIN_MODULE_NAME: str = "main.py"
MAIN_PACKAGE_NAME: str = "main"
MAIN_SUPPORT_IMPORT_PACKAGE_NAMES: frozenset[str] = frozenset({"_helpers", "shared"})
MODELS_MODULE_NAME: str = "models.py"
MODELS_PACKAGE_NAME: str = "models"
NESTED_ALLOWED_CHILD_PACKAGE_NAMES: frozenset[str] = frozenset(
    {
        HELPERS_PACKAGE_NAME,
        "shared",
        CLASSES_PACKAGE_NAME,
        MODELS_PACKAGE_NAME,
        "types",
        CONSTANTS_PACKAGE_NAME,
        EXCEPTIONS_PACKAGE_NAME,
        MAIN_PACKAGE_NAME,
    }
)
NESTED_RUNTIME_ROLE_MODULE_NAMES: frozenset[str] = frozenset(
    {
        INIT_MODULE_NAME,
        MODELS_MODULE_NAME,
        "types.py",
        CONSTANTS_MODULE_NAME,
        EXCEPTIONS_MODULE_NAME,
        HELPERS_MODULE_NAME,
    }
)
NEWTYPE_CALL_NAME: str = "NewType"
NEWLINE_CHARACTER: str = "\n"
ORCHESTRATION_INTEGRATION_NAMES: frozenset[str] = frozenset({"dagster", "rivers"})
ORCHESTRATION_PUBLIC_MODULE_NAMES: frozenset[str] = frozenset(
    {"assets.py", "translator.py", "project.py", "resource.py"}
)
PROVIDER_CLASS_NAME: str = "Provider"
PROVIDER_MODULE_PARTS: tuple[str, ...] = ("src", "sqlbuild", "providers.py")
PLANNER_PATH_MARKER: str = "src/sqlbuild/compiler/planner/"
PUBLIC_SURFACE_ROLE_NAMES: frozenset[str] = frozenset(
    {
        CLASSES_PACKAGE_NAME,
        MODELS_PACKAGE_NAME,
        "types",
        CONSTANTS_PACKAGE_NAME,
        EXCEPTIONS_PACKAGE_NAME,
    }
)
PYTHON_BYTECODE_CACHE_PACKAGE_NAME: str = "__pycache__"
PYTHON_FILE_SUFFIX: str = ".py"
RAW_COLOR_CAPABILITY_MODULE_NAME: str = "sqlbuild.presentation._helpers.terminal_capabilities"
ROLE_BOUNDARY_NAMES: frozenset[str] = frozenset(
    {
        HELPERS_PACKAGE_NAME,
        CLASSES_PACKAGE_NAME,
        MODELS_PACKAGE_NAME,
        "types",
        CONSTANTS_PACKAGE_NAME,
        EXCEPTIONS_PACKAGE_NAME,
    }
)
RULES_PACKAGE_NAME: str = "rules"
STRATA_POLICY_PATH_MARKER: str = "scripts/strata_policy/"
TOOLING_RULE_HELPER_MIN_IMPORT_PARTS: int = 3
RUNTIME_ROOT_PARTS: tuple[str, ...] = ("src", "sqlbuild")
SC010_CODE: str = "SC010"
SELECTOR_MARKER: str = "+"
SELECTOR_STRING_METHOD_NAMES: frozenset[str] = frozenset(
    {"startswith", "endswith", "lstrip", "rstrip"}
)
SHARED_PACKAGE_NAME: str = "shared"
SIBLING_HELPER_IMPORTER_PACKAGE_NAMES: frozenset[str] = frozenset(
    {"classes", "main", "models", "types", "constants", "exceptions"}
)
SOURCE_FRESHNESS_TEXT_MARKERS: tuple[str, ...] = ("SOURCE_FRESHNESS", "source_freshness")
SOURCE_ROOT_NAME: str = "src"
SQLBUILD_PACKAGE_NAME: str = "sqlbuild"
SQLBUILD_SOURCE_PATH_MARKER: str = "src/sqlbuild/"
SQL_REFERENCE_KIND_CLASS_NAME: str = "SqlReferenceKind"
SUPPORTED_TOP_LEVEL_DIRECT_MODULE_NAMES: frozenset[str] = frozenset(
    {
        INIT_MODULE_NAME,
        MODELS_MODULE_NAME,
        "types.py",
        CONSTANTS_MODULE_NAME,
        EXCEPTIONS_MODULE_NAME,
        HELPERS_MODULE_NAME,
        "providers.py",
    }
)
SUPPORT_PACKAGE_NAMES: frozenset[str] = frozenset({HELPERS_PACKAGE_NAME, CLASSES_PACKAGE_NAME})
TOP_LEVEL_EXEMPT_DOMAIN_NAMES: frozenset[str] = frozenset({"presentation", SHARED_PACKAGE_NAME})
TOOLING_ROOT_NAME: str = "scripts"
TYPE_CHECKING_NAME: str = "TYPE_CHECKING"
TYPES_MODULE_NAME: str = "types.py"
TYPES_PACKAGE_NAME: str = "types"
