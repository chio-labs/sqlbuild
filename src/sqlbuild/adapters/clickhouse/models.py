"""ClickHouse adapter request models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapters.clickhouse.classes.partition_locks import PartitionLocks


@dataclass(frozen=True)
class PartitionRewrite:
    """Incoming delta rows and the target rows they displace; ``{delta}`` names the delta."""

    destination: str
    delta_insert_sql: str
    displaced_predicate: str


@dataclass(frozen=True)
class RewriteExecutor:
    """The adapter operations and process-wide partition locks a rewrite needs."""

    execute: Callable[[str], Any]
    statement_recorder: StatementRecorder
    partition_locks: PartitionLocks


@dataclass(frozen=True)
class SnapshotWorkspace:
    """The live snapshot and the two working relations that stand in for it."""

    destination: str
    work: str
    rebuild: str
    valid_to_column: str
