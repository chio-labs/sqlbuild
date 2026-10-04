"""Stable constants for same-runner compile performance comparisons."""

import re

DEFAULT_RUNS: int = 3
DEFAULT_MAX_RATIO: float = 1.10
DENSE_KIND: str = "dense"
FRESH_KIND: str = "fresh"
PROJECT_KINDS: tuple[str, ...] = (DENSE_KIND, FRESH_KIND)
COLD_MODE: str = "cold"
WARM_MODE: str = "warm"
EDIT_MODE: str = "edit"
COMPILE_MODES: tuple[str, ...] = (COLD_MODE, WARM_MODE, EDIT_MODE)
MODE_TITLES: dict[str, str] = {
    COLD_MODE: "cold compile without cache",
    WARM_MODE: "unchanged warm compile",
    EDIT_MODE: "one-model edit on a warm cache",
}
ANALYSIS_CACHE_MISSES: str = "analysis_cache_misses"
MODELS_DIRECTORY: str = "models"
MODEL_FILE_PATTERN: str = "*.sql"
EDIT_COMMENT: str = "-- Benchmark edit {revision}.\n"
STATEMENT_START: re.Pattern[str] = re.compile(r"^(WITH|SELECT)\b", re.MULTILINE)
BASE_LABEL: str = "base"
HEAD_LABEL: str = "head"
EXCLUDED_ENVIRONMENT_KEYS: frozenset[str] = frozenset({"VIRTUAL_ENV"})
EXCLUDED_ENVIRONMENT_PREFIX: str = "DBT_"
COMPILE_ENTRY: str = "import sys; from sqlbuild.cli.entry.main.entry import main; sys.exit(main())"
BASE_GENERATOR_ENTRY: str = (
    "import sys; from pathlib import Path; "
    "from scripts.compile_performance_ratio._helpers.measure import write_benchmark_project; "
    "write_benchmark_project("
    "kind=sys.argv[1], project_dir=Path(sys.argv[2]), models=int(sys.argv[3]))"
)
PYTHONPATH_KEY: str = "PYTHONPATH"
ERROR_TAIL_CHARACTERS: int = 2000
FRESH_SOURCE_SHARE: float = 713 / 3000
FRESH_SEED_SHARE: float = 141 / 3000
FRESH_FUNCTION_SHARE: float = 71 / 3000
FRESH_MACRO_SHARE: float = 37 / 3000
FRESH_TEST_SHARE: float = 2945 / 3000
FRESH_AUDIT_SHARE: float = 5056 / 3000
REPORTED_PHASES: tuple[str, ...] = (
    "total_ms",
    "graph_ms",
    "model_analysis_ms",
    "analysis_native_ms",
    "built_in_rules_ms",
    "custom_rules_ms",
    "test_planning_ms",
    "write_ms",
)
