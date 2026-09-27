"""Stable constants for same-runner compile performance comparisons."""

DEFAULT_RUNS: int = 3
DEFAULT_MAX_RATIO: float = 1.10
DENSE_KIND: str = "dense"
FRESH_KIND: str = "fresh"
PROJECT_KINDS: tuple[str, ...] = (DENSE_KIND, FRESH_KIND)
BASE_LABEL: str = "base"
HEAD_LABEL: str = "head"
COMPILE_ENTRY: str = "import sys; from sqlbuild.cli.entry.main.entry import main; sys.exit(main())"
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
