"""Tuned scoring constants for the dupscore duplication-risk advisory tool."""

from __future__ import annotations

SOURCE_ROOT: str = "src"
PROJECT_PACKAGE: str = "sqlbuild"
EXCLUDED_MODULE_PREFIX: str = "sqlbuild.integrations.dbt"
PACKAGE_DEPTH: int = 3

MIN_REACHABLE_FUNCTIONS: int = 5
MIN_SHARED_LEAVES: int = 3
MAX_LEAF_USERS_FOR_PAIRING: int = 200

MIN_SHARED_DATACLASS_FIELDS: int = 4

MIN_SAME_NAME_WORDS: int = 1
MAX_NAME_WEIGHT_WORDS: int = 6

STATE_READ_PREFIXES: tuple[str, ...] = ("get_", "read_", "fetch_", "list_", "iter_", "load_")
MIN_STATE_FANIN_PACKAGES: int = 2

MAX_FILES_PER_COMMIT: int = 30
MIN_COCHANGES: int = 5

SIGNAL_NAME_CALLGRAPH: str = "callgraph_shape"
SIGNAL_NAME_STATE_FANIN: str = "state_fanin"
SIGNAL_NAME_DATACLASS_OVERLAP: str = "dataclass_overlap"
SIGNAL_NAME_SAME_NAME: str = "same_name_symbols"
SIGNAL_NAME_COCHANGE: str = "cochange"

RRF_RANK_OFFSET: int = 10
SIGNAL_WEIGHTS: dict[str, float] = {
    SIGNAL_NAME_CALLGRAPH: 1.0,
    SIGNAL_NAME_STATE_FANIN: 1.0,
    SIGNAL_NAME_DATACLASS_OVERLAP: 1.0,
    SIGNAL_NAME_SAME_NAME: 1.0,
    SIGNAL_NAME_COCHANGE: 0.75,
}

GENERIC_FUNCTION_NAMES: frozenset[str] = frozenset(
    {"main", "run", "build", "execute", "register", "create", "apply", "render"}
)

DEFAULT_TOP_RESULTS: int = 20
CONFIG_FILENAME: str = "dupscore.toml"

REPORT_MODE: str = "report"
PAIR_MODE: str = "pair"
PAIR_ARGUMENT_COUNT: int = 2

WORKTREE_LABEL: str = "worktree"
HEAD_REVISION: str = "HEAD"

HELPERS_ROLE_SEGMENT: str = "_helpers"
MAIN_ROLE_SEGMENT: str = "main"
