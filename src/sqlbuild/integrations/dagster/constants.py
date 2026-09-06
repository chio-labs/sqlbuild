"""Dagster integration protocol constants."""

from __future__ import annotations

from sqlbuild.compiler.dag.types import NodeKind
from sqlbuild.executor.node_results.types import NodeResultStatus
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.python_nodes.types import PythonCheckSeverity

DAGSTER_ASSET_NODE_KIND_MEMBERS: frozenset[NodeKind] = frozenset(
    {
        NodeKind.SOURCE,
        NodeKind.LOADER,
        NodeKind.SEED,
        NodeKind.MODEL,
        NodeKind.UDF,
        NodeKind.TABLE_FN,
        NodeKind.TASK,
        NodeKind.ASSET,
    }
)
DAGSTER_ASSET_NODE_KIND_EXCLUSIONS: frozenset[NodeKind] = frozenset(
    {NodeKind.CHECK, NodeKind.SQL_TEST, NodeKind.AUDIT, NodeKind.SCENARIO, NodeKind.PYTHON_CHECK}
)
DAGSTER_ASSET_NODE_KINDS: frozenset[str] = frozenset(
    kind.value for kind in DAGSTER_ASSET_NODE_KIND_MEMBERS
)
DAGSTER_DIRECT_KIND_NODE_KIND_MEMBERS: frozenset[NodeKind] = frozenset(
    DAGSTER_ASSET_NODE_KIND_MEMBERS - {NodeKind.MODEL}
)
DAGSTER_DIRECT_KIND_NODE_KIND_EXCLUSIONS: frozenset[NodeKind] = frozenset(
    DAGSTER_ASSET_NODE_KIND_EXCLUSIONS | {NodeKind.MODEL}
)
DAGSTER_DIRECT_KIND_NODE_KINDS: frozenset[str] = frozenset(
    kind.value for kind in DAGSTER_DIRECT_KIND_NODE_KIND_MEMBERS
)
MODEL_NODE_KIND: str = NodeKind.MODEL.value
SOURCE_NODE_KIND: str = NodeKind.SOURCE.value
LOADER_NODE_KIND: str = NodeKind.LOADER.value
VIEW_MATERIALIZATION_TYPE: str = "view"

ASSET_SELECTION_COMMANDS: frozenset[str] = frozenset(
    {"build", "run", "test", "check", "audit", "seed", "load", "clone"}
)
CLONE_COMMAND: str = "clone"
CHECK_COMMAND: str = "check"
EVENT_OUTPUT_FLAG: str = "--event-output"
LIVE_EVENT_COMMANDS: frozenset[str] = ASSET_SELECTION_COMMANDS
VIRTUAL_ENV_FLAG: str = "--virtual-env"
VERBOSE_FLAGS: frozenset[str] = frozenset({"--verbose", "-v"})
EXPLICIT_SELECTION_FLAGS: frozenset[str] = frozenset({"--select", "-s", "--select-file"})
JSON_OUTPUT_FLAGS: frozenset[str] = frozenset({"--json", "--json-output"})
JSON_OUTPUT_FLAG: str = "--json-output"
SELECT_FILE_FLAG: str = "--select-file"
SCENARIO_TEST_COMMAND: tuple[str, str] = ("scenario", "test")
SCENARIO_CHECK_KIND: str = NodeKind.SCENARIO.value
SCENARIO_VALUE_FLAGS: frozenset[str] = frozenset(
    {
        "--max-snapshot-rows",
        "--max-snapshot-total-rows",
        "--max-snapshot-bytes",
        "--max-snapshot-total-bytes",
    }
)
LOAD_COMMAND: str = "load"
LOAD_SELECTABLE_NODE_KIND_MEMBERS: frozenset[NodeKind] = frozenset(
    {NodeKind.SOURCE, NodeKind.LOADER}
)
LOAD_SELECTABLE_NODE_KIND_EXCLUSIONS: frozenset[NodeKind] = frozenset(
    {
        NodeKind.SEED,
        NodeKind.UDF,
        NodeKind.TABLE_FN,
        NodeKind.MODEL,
        NodeKind.TASK,
        NodeKind.ASSET,
        NodeKind.CHECK,
        NodeKind.SQL_TEST,
        NodeKind.AUDIT,
        NodeKind.SCENARIO,
        NodeKind.PYTHON_CHECK,
    }
)
LOAD_SELECTABLE_NODE_KINDS: frozenset[str] = frozenset(
    kind.value for kind in LOAD_SELECTABLE_NODE_KIND_MEMBERS
)
DEFAULT_SELECTABLE_NODE_KIND_MEMBERS: frozenset[NodeKind] = frozenset(
    {NodeKind.SOURCE, NodeKind.SEED, NodeKind.MODEL, NodeKind.UDF, NodeKind.TABLE_FN}
)
DEFAULT_SELECTABLE_NODE_KIND_EXCLUSIONS: frozenset[NodeKind] = frozenset(
    {
        NodeKind.LOADER,
        NodeKind.TASK,
        NodeKind.ASSET,
        NodeKind.CHECK,
        NodeKind.SQL_TEST,
        NodeKind.AUDIT,
        NodeKind.SCENARIO,
        NodeKind.PYTHON_CHECK,
    }
)
DEFAULT_SELECTABLE_NODE_KINDS: frozenset[str] = frozenset(
    kind.value for kind in DEFAULT_SELECTABLE_NODE_KIND_MEMBERS
)
MATERIALIZABLE_NODE_KIND_MEMBERS: frozenset[NodeKind] = frozenset(
    {
        NodeKind.SOURCE,
        NodeKind.LOADER,
        NodeKind.SEED,
        NodeKind.MODEL,
        NodeKind.UDF,
        NodeKind.TABLE_FN,
    }
)
MATERIALIZABLE_NODE_KIND_EXCLUSIONS: frozenset[NodeKind] = frozenset(
    {
        NodeKind.TASK,
        NodeKind.ASSET,
        NodeKind.CHECK,
        NodeKind.SQL_TEST,
        NodeKind.AUDIT,
        NodeKind.SCENARIO,
        NodeKind.PYTHON_CHECK,
    }
)
MATERIALIZABLE_NODE_KINDS: frozenset[str] = frozenset(
    kind.value for kind in MATERIALIZABLE_NODE_KIND_MEMBERS
)
COMPLETED_EXECUTION_STATUS_MEMBERS: frozenset[ExecutionStatus] = frozenset(
    {ExecutionStatus.SUCCESS, ExecutionStatus.SKIPPED}
)
COMPLETED_EXECUTION_STATUS_EXCLUSIONS: frozenset[ExecutionStatus] = frozenset(
    {ExecutionStatus.FAILED}
)
COMPLETED_NODE_RESULT_STATUS_MEMBERS: frozenset[NodeResultStatus] = frozenset(
    {NodeResultStatus.SUCCESS, NodeResultStatus.SKIPPED}
)
COMPLETED_NODE_RESULT_STATUS_EXCLUSIONS: frozenset[NodeResultStatus] = frozenset(
    {NodeResultStatus.FAILED, NodeResultStatus.WARN}
)
COMPLETED_EXECUTION_STATUSES: frozenset[str] = frozenset(
    status.value for status in COMPLETED_EXECUTION_STATUS_MEMBERS
)
SUCCESS_EXECUTION_STATUS: str = ExecutionStatus.SUCCESS.value
FAILED_EXECUTION_STATUS: str = ExecutionStatus.FAILED.value
CHECK_NAME_SEPARATOR_CHARACTER: str = "_"
CHECK_METADATA_EXCLUDED_KEYS: frozenset[str] = frozenset(
    {"passed", "steps", "expected_results", "assertion_results"}
)
WARNING_CHECK_SEVERITY_MEMBERS: frozenset[PythonCheckSeverity] = frozenset(
    {PythonCheckSeverity.WARN}
)
WARNING_CHECK_SEVERITY_EXCLUSIONS: frozenset[PythonCheckSeverity] = frozenset(
    {PythonCheckSeverity.ERROR}
)
WARNING_CHECK_SEVERITY: str = PythonCheckSeverity.WARN.value
INSUFFICIENT_CHECK_STATUS: str = "insufficient"
