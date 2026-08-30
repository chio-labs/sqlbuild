"""CLI command decision constants."""

from sqlbuild.cli.commands.types import CompileLineageMode, PlaygroundTemplate
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.planner.types import SelectorKind

COMPILE_LINEAGE_MODE_VALUES: tuple[str, ...] = tuple(mode.value for mode in CompileLineageMode)
RICH_LINEAGE_STATUS_MODEL_THRESHOLD: int = 100
EMPTY_DAG_PATH: str = ""
TARGET_DIRECTORY_NAME: str = "target"
SQLBUILD_CONCURRENCY_ENV_VAR: str = "SQLBUILD_CONCURRENCY"
EMPTY_ENV_VALUE: str = ""
NO_COLOR_OPTION: str = "--no-color"
DEBUG_OPTION: str = "--debug"
DBT_INIT_COMMAND: str = "init"
SCENARIO_TEST_COMMAND: str = "test"
SCENARIO_CAPTURE_COMMAND: str = "capture"
COLUMN_LINEAGE_MODE_VALUES: tuple[str, ...] = tuple(mode.value for mode in ColumnLineageMode)
UNLIMITED_DEPTH_VALUE: str = "all"
UPSTREAM_DIRECTION: str = "upstream"
DOWNSTREAM_DIRECTION: str = "downstream"
BOTH_DIRECTIONS: str = "both"
JSON_OUTPUT_FORMAT: str = "json"
LIST_OUTPUT_FORMAT: str = "list"
SQL_FILE_SUFFIX: str = ".sql"
SELECTOR_INTERSECTION_MARKER: str = ","
PATH_BETWEEN_MARKER: str = "~"
SELECTOR_KIND_SEPARATOR: str = ":"
PATH_SEPARATOR: str = "/"
SELECTOR_EXPANSION_MARKER: str = "+"
COLUMN_TARGET_SEPARATOR: str = "."
SUPPORTED_TYPED_SELECTOR_KINDS: frozenset[str] = frozenset(
    {
        SelectorKind.SEED,
        SelectorKind.SOURCE,
        SelectorKind.TAG,
        SelectorKind.PATH,
    }
)
PLAYGROUND_TEMPLATE_VALUES: tuple[str, ...] = tuple(
    template.value for template in PlaygroundTemplate
)
SUCCESS_STATUS: str = "success"
FAILED_STATUS: str = "failed"
DEFAULT_MAX_SNAPSHOT_ROWS_PER_RELATION: int = 10_000
DEFAULT_MAX_SNAPSHOT_TOTAL_ROWS: int = 50_000
DEFAULT_MAX_SNAPSHOT_BYTES_PER_RELATION: int = 5_000_000
DEFAULT_MAX_SNAPSHOT_TOTAL_BYTES: int = 25_000_000
SCENARIO_CLI_MISSING_SUBCOMMAND: str = "C450"
SCENARIO_CLI_NONE_DISCOVERED: str = "C451"
SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED: str = "C452"
SCENARIO_CLI_UNKNOWN_SELECTOR: str = "C453"
SCENARIO_CLI_LOCAL_SNAPSHOT_FLAG_REQUIRED: str = "C454"
SCENARIO_CLI_SQL_VALIDATION_REQUIRED: str = "C455"
SCENARIO_CLI_CAPTURE_DIALECT_REQUIRED: str = "C456"
SCENARIO_CLI_UNSUPPORTED_GRAPH_SELECTOR: str = "C457"
SQL_ANALYSIS_CONFIG_KEY: str = "sql_analysis"
SQL_VALIDATION_CONFIG_KEY: str = "sql_validation"
GRAPH_SELECTOR_EXPANSION_MARKER: str = "+"
GRAPH_SELECTOR_PATH_MARKER: str = "~"
DBT_JSON_OUTPUT_OPTION: str = "--json"
DBT_PASSTHROUGH_SEPARATOR: str = "--"
DBT_VERBOSE_OPTIONS: frozenset[str] = frozenset({"--verbose", "-v"})
DBT_CLI_OUTPUT_OPTIONS: frozenset[str] = frozenset({DBT_JSON_OUTPUT_OPTION, *DBT_VERBOSE_OPTIONS})
DBT_NO_CONNECTION_OPTION: str = "--no-connection"
RECONCILE_ATTACH_COMMAND: str = "attach"
STATE_CHECKPOINTS_COMMAND: str = "checkpoints"
KATA_SKILLS_COMMAND: str = "skills"
COST_HISTORY_SELECTOR: str = "history"
COST_LATEST_SELECTOR: str = "latest"
COST_DESCENDING_ORDER: str = "desc"
COST_DEFAULT_HISTORY_SORT: str = "completed"
COST_DEFAULT_DETAIL_SORT: str = "cost"
COST_DEFAULT_HISTORY_LIMIT: int = 10
ISO_DATE_LENGTH: int = 10
COST_NARROW_TERMINAL_WIDTH: int = 120
COST_TABLE_COLUMN_COUNT: int = 6
COST_HISTORY_NUMERIC_COLUMNS: frozenset[int] = frozenset({4, 5})
COST_RESOURCE_NUMERIC_START_COLUMN: int = 2
BYTE_SCALE: int = 1024
BYTE_UNIT: str = "B"
TERABYTE_UNIT: str = "TiB"
SCOPE_PATH_RELATIVE: str = "relative"
SCOPE_PATH_COMPACT: str = "compact"
SCOPE_PATH_NONE: str = "none"
SCOPE_GLOBAL_SUMMARY: str = "summary"
SCOPE_GLOBAL_ALL: str = "all"
SCOPE_DEFAULT_PAGE_SIZE: int = 100
