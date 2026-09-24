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

CLONES_MODE: str = "clones"
REPORT_MODE: str = "report"
PAIR_MODE: str = "pair"
PAIR_ARGUMENT_COUNT: int = 2

WORKTREE_LABEL: str = "worktree"
HEAD_REVISION: str = "HEAD"

HELPERS_ROLE_SEGMENT: str = "_helpers"
MAIN_ROLE_SEGMENT: str = "main"

LANGUAGE_PYTHON: str = "python"
LANGUAGE_RUST: str = "rust"
SUPPORTED_LANGUAGES: tuple[str, ...] = (LANGUAGE_PYTHON, LANGUAGE_RUST)
PYTHON_TEST_ROOT: str = "tests"
RUST_CRATES_ROOT: str = "crates"
RUST_SOURCE_DIRECTORY: str = "src"
RUST_TEST_DIRECTORIES: frozenset[str] = frozenset({"tests", "benches"})

CLONE_KGRAM_SIZE: int = 12
CLONE_WINNOW_WINDOW: int = 6
CLONE_MIN_FINGERPRINTS: int = 6
CLONE_CANDIDATE_MIN_JACCARD: float = 0.2
CLONE_MAX_FINGERPRINT_UNITS: int = 25
CLONE_SMALL_NEAR_MISS_TOKENS: int = 80
CLONE_SMALL_NEAR_MISS_MIN_SIMILARITY: float = 0.9
DEFAULT_CLONE_MIN_TOKENS: int = 60
DEFAULT_CLONE_MIN_SIMILARITY: float = 0.8
DEFAULT_CLONE_TOP_RESULTS: int = 30
CLONE_TEXT_MAX_MEMBERS: int = 12

CATEGORY_EXACT: str = "exact"
CATEGORY_RENAMED: str = "renamed"
CATEGORY_NEAR_MISS: str = "near-miss"
CATEGORY_ORDER: tuple[str, ...] = (CATEGORY_EXACT, CATEGORY_RENAMED, CATEGORY_NEAR_MISS)

CHANGE_NEW: str = "new"
CHANGE_CHANGED: str = "changed"

PLACEHOLDER_IDENTIFIER: str = "$id"
PLACEHOLDER_NUMBER: str = "$num"
PLACEHOLDER_STRING: str = "$str"
PLACEHOLDER_FSTRING: str = "$fstr"
PLACEHOLDER_BYTE_STRING: str = "$bstr"
PLACEHOLDER_CHAR: str = "$char"
PLACEHOLDER_BYTE: str = "$byte"
PLACEHOLDER_LIFETIME: str = "$life"

RUST_KIND_IDENTIFIER: str = "identifier"
RUST_KIND_LIFETIME: str = "lifetime"
RUST_KIND_STRING: str = "string"
RUST_KIND_BYTE_STRING: str = "byte_string"
RUST_KIND_CHAR: str = "char"
RUST_KIND_BYTE: str = "byte"
RUST_KIND_NUMBER: str = "number"
RUST_KIND_PUNCTUATION: str = "punctuation"
