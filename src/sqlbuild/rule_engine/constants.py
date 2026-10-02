"""Rules engine constants."""

RULES_SKILL_PATHS: tuple[str, ...] = (
    ".agents/skills/sqlbuild-rules/SKILL.md",
    ".claude/skills/sqlbuild-rules/SKILL.md",
    ".opencode/skills/sqlbuild-rules/SKILL.md",
)

RULES_NATIVE_API_VERSION: int = 1
CUSTOM_HOST_PROTOCOL_VERSION: int = 1
CUSTOM_HOST_RUNTIME_VERSION: str = "sqlbuild-rules-custom-v2"
CUSTOM_HOST_MAX_TRACKED_READS: int = 100_000
CUSTOM_RULES_CACHE_VERSION: str = "custom-rules-reads-v1"
CUSTOM_RULES_CACHE_FILE: str = "target/rules-cache/bulk/custom-rules.json"
NATIVE_RULES_MEMO_VERSION: str = "native-rules-response-v1"
NATIVE_RULES_MEMO_FILE: str = "target/rules-cache/bulk/native-response.json"
CUSTOM_HOST_INPUT_TUPLE_SIZE: int = 2
CUSTOM_HOST_MODULE: str = "sqlbuild.rule_engine._helpers.host.custom_host"
CUSTOM_HOST_LAUNCH_MODULE: str = "sqlbuild.rule_engine._helpers.host.custom_host_launch"
CUSTOM_HOST_HASH_SEED: str = "0"
CUSTOM_HOST_EXEC_OS_NAME: str = "posix"
CUSTOM_HOST_STARTUP_ENVIRONMENT: tuple[str, ...] = (
    "APPDATA",
    "HOME",
    "PYTHONHOME",
    "PYTHONNOUSERSITE",
    "PYTHONPATH",
    "PYTHONUSERBASE",
    "SYSTEMROOT",
)
CUSTOM_RULE_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "__future__",
        "abc",
        "bisect",
        "collections",
        "copy",
        "dataclasses",
        "decimal",
        "difflib",
        "enum",
        "fnmatch",
        "fractions",
        "functools",
        "graphlib",
        "hashlib",
        "heapq",
        "itertools",
        "json",
        "math",
        "operator",
        "pathlib",
        "re",
        "rules",
        "sqlbuild.rules",
        "statistics",
        "string",
        "textwrap",
        "types",
        "typing",
        "unicodedata",
    }
)
SKILL_FRESH: str = "fresh"
SKILL_MISSING: str = "missing"
SKILL_STALE: str = "stale"
REPLACEABLE_SKILL_STATES: frozenset[str] = frozenset({SKILL_FRESH, SKILL_MISSING, SKILL_STALE})

AST_SELECT_KIND: str = "select"
AST_CTE_KIND: str = "cte"
CONTRACT_ENFORCED: str = "enforced"
CONTRACT_BOOLEAN_NAME_CODE: str = "SQBRCONTRACT102"
CONTRACT_TIMESTAMP_NAME_CODE: str = "SQBRCONTRACT103"
CONTRACT_DATE_NAME_CODE: str = "SQBRCONTRACT104"
EMPTY_INPUT_TEST_CODE: str = "SQBRTEST203"
TYPE_PROOF_RULE_CODES: frozenset[str] = frozenset({"SQBRCONTRACT105"})

BOOLEAN_TYPE: str = "BOOLEAN"
DATE_TYPE: str = "DATE"
TIMESTAMP_TYPE: str = "TIMESTAMP"


NAMED_CTE_TUPLE_SIZE: int = 2
TARGET_DIRECTORY_NAME: str = "target"
RULE_DECORATOR_TOKEN: str = "@rule"
INIT_MODULE_NAME: str = "__init__"
PARENT_DIRECTORY_TOKEN: str = ".."

MIN_AUDITS_PER_MODEL: str = "min_audits_per_model"
MIN_TESTS_PER_MODEL: str = "min_tests_per_model"
MIN_CUSTOM_RULE_TEST_CASES: str = "min_custom_rule_test_cases"
CUSTOM_RULE_COVERAGE_CODE: str = "SQBRTEST301"
RULES_THRESHOLD_RULE_CODES: frozenset[str] = frozenset({"SQBRTEST201", "SQBRTEST202"})
RULES_LAYOUT_RULE_PREFIXES: tuple[str, str] = ("SQBRPROJECT2", "SQBRDECLARATION3")
RULES_LAYOUT_THRESHOLD_RULE_CODES: frozenset[str] = frozenset(
    {
        "SQBRPROJECT203",
        "SQBRPROJECT204",
        "SQBRDECLARATION303",
        "SQBRDECLARATION304",
        "SQBRDECLARATION306",
    }
)
MAX_SUBDOMAIN_DEPTH: str = "max_subdomain_depth"
MIN_SHARED_OWNER_PREFIX_DIRECTORIES: str = "min_shared_owner_prefix_directories"
MAX_ROLE_CONTAINER_DEPTH: str = "max_role_container_depth"
MAX_MACRO_CONTAINER_FILES: str = "max_macro_container_files"
MAX_CONSTANT_CONTAINER_FILES: str = "max_constant_container_files"
MAX_ENUM_CONTAINER_FILES: str = "max_enum_container_files"
MIN_SHARED_CONTAINER_PREFIX_FILES: str = "min_shared_container_prefix_files"
RULES_THRESHOLD_DEFAULTS: dict[str, int] = {
    MIN_AUDITS_PER_MODEL: 1,
    MIN_TESTS_PER_MODEL: 1,
    MIN_CUSTOM_RULE_TEST_CASES: 1,
    MAX_SUBDOMAIN_DEPTH: 1,
    MIN_SHARED_OWNER_PREFIX_DIRECTORIES: 2,
    MAX_ROLE_CONTAINER_DEPTH: 1,
    MAX_MACRO_CONTAINER_FILES: 10,
    MAX_CONSTANT_CONTAINER_FILES: 10,
    MAX_ENUM_CONTAINER_FILES: 10,
    MIN_SHARED_CONTAINER_PREFIX_FILES: 2,
}
RULE_FIX_AVAILABLE_NOTE: str = (
    "Fix available: `sqb format --fix` applies it after compiler verification"
)
FACT_PROJECT_MODELS: str = "project.models"
FACT_PROJECT_SOURCES: str = "project.sources"
FACT_PROJECT_SEEDS: str = "project.seeds"
FACT_PROJECT_FUNCTIONS: str = "project.functions"
FACT_PROJECT_TESTS: str = "project.tests"
FACT_PROJECT_AUDITS: str = "project.audits"
FACT_TREE_PATHS: str = "tree.paths"
FACT_TREE_CHILDREN: str = "tree.children"
FACT_TREE_DESCENDANTS: str = "tree.descendants"
FACT_TREE_GLOB: str = "tree.glob"
FACT_TREE_RELATIVE_PARTS: str = "tree.relative_parts"
FACT_TREE_RESOURCES_UNDER: str = "tree.resources_under"
FACT_TREE_READ_TEXT: str = "tree.read_text"
FACT_SQL_FOR_MODEL: str = "sql.for_model"
FACT_GRAPH_DEPENDENCIES: str = "graph.dependencies"
FACT_GRAPH_DEPENDENTS: str = "graph.dependents"
FACT_COLUMNS_DECLARED: str = "columns.declared"
FACT_COLUMNS_INFERRED: str = "columns.inferred"
FACT_COLUMNS_NAMES: str = "columns.names"
FACT_CONTRACTS_ENFORCED: str = "contracts.enforced"
FACT_CONTRACTS_GRAIN: str = "contracts.grain"
FACT_TESTS_ALL: str = "tests.all"
FACT_TESTS_FOR_MODEL: str = "tests.for_model"
FACT_AUDITS_ALL: str = "audits.all"
FACT_AUDITS_FOR_MODEL: str = "audits.for_model"
FACT_DECLARATIONS_PUBLIC_ENUMS: str = "declarations.public_enums"
FACT_DECLARATIONS_PUBLIC_CONSTANTS: str = "declarations.public_constants"
FACT_DECLARATIONS_ENUMS: str = "declarations.enums"
FACT_DECLARATIONS_CONSTANTS: str = "declarations.constants"
