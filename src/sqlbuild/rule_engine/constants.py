"""Rules engine constants."""

RULES_SKILL_PATHS: tuple[str, ...] = (
    ".agents/skills/sqlbuild-rules/SKILL.md",
    ".claude/skills/sqlbuild-rules/SKILL.md",
    ".opencode/skills/sqlbuild-rules/SKILL.md",
)

RULES_NATIVE_API_VERSION: int = 1
CUSTOM_HOST_PROTOCOL_VERSION: int = 1
CUSTOM_HOST_RUNTIME_VERSION: str = "sqlbuild-rules-custom-v1"
CUSTOM_HOST_INPUT_TUPLE_SIZE: int = 2
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

BOOLEAN_TYPE: str = "BOOLEAN"
DATE_TYPE: str = "DATE"
TIMESTAMP_TYPE: str = "TIMESTAMP"


NAMED_CTE_TUPLE_SIZE: int = 2
TARGET_DIRECTORY_NAME: str = "target"
RULE_DECORATOR_TOKEN: str = "@rule"
INIT_MODULE_NAME: str = "__init__"
RULE_CONTEXT_PROJECT_FACT: str = "project"
RULE_CONTEXT_GRAPH_FACT: str = "graph"
RULE_CONTEXT_TESTS_FACT: str = "tests"
RULE_CONTEXT_AUDITS_FACT: str = "audits"
RULE_CONTEXT_DECLARATIONS_FACT: str = "declarations"
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
