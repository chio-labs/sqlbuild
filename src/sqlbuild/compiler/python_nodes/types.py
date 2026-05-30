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

    SELF = "self"
    DOWNSTREAM = "downstream"


class PythonNodeFanInAction(StrEnum):
    """How a Python node should proceed after evaluating upstream outcomes."""

    RUN = "run"
    SKIP = "skip"
    BLOCK = "block"
