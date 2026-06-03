"""Internal Python-node domain types."""

from __future__ import annotations

from enum import StrEnum


class PythonNodeKind(StrEnum):
    """Framework-owned Python node kind."""

    TASK = "task"
    ASSET = "asset"
    LOADER = "loader"
    CHECK = "check"


class PythonNodeStatus(StrEnum):
    """Internal Python-node execution status."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class SkipMode(StrEnum):
    """Python-node skip propagation mode."""

    SOFT = "soft"
    HARD = "hard"


class PythonNodeFanInAction(StrEnum):
    """How a Python node should proceed after evaluating upstream outcomes."""

    RUN = "run"
    SKIP = "skip"
    BLOCK = "block"


class PythonRunPhase(StrEnum):
    """Lifecycle-aware Python execution phase."""

    PRE_SQL_INGRESS = "pre_sql_ingress"
    READ_SIDE = "read_side"
