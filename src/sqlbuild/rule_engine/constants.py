"""Rules engine constants."""

CUSTOM_HOST_MAX_TRACKED_READS: int = 100_000
CUSTOM_HOST_INPUT_POLL_SECONDS: float = 0.002
CUSTOM_HOST_INPUT_WAIT_SECONDS: float = 120.0
CUSTOM_HOST_MODULE: str = "sqlbuild.rule_engine._helpers.host.custom_host"
CUSTOM_HOST_CANCELLED_EXIT_CODE: int = 75
CUSTOM_HOST_CANCELLED_MESSAGE: str = "custom host cancelled after another host failed"
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
RULE_DECORATOR_TOKEN: str = "@rule"
RULES_DIRECTORY_NAME: str = "rules"
RULES_COPY_IGNORED_PATTERNS: tuple[str, ...] = (".*", "__pycache__", "*.pyc")

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
FACT_COLUMNS_ENUM_TYPES: str = "columns.enum_types"
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
