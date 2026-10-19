"""ClickHouse adapter request models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapters.clickhouse.classes.partition_locks import PartitionLocks
from sqlbuild.adapters.clickhouse.classes.relation_write_locks import RelationWriteLocks


@dataclass(frozen=True)
class PartitionRewrite:
    """Incoming delta rows and the target rows they displace; ``{delta}`` names the delta."""

    destination: str
    delta_insert_sql: str
    displaced_predicate: str


@dataclass(frozen=True)
class RewriteTables:
    """The live table, the staged delta and staging relations, and the displaced rows."""

    destination: str
    delta: str
    staging: str
    displaced_predicate: str


@dataclass(frozen=True)
class RewriteExecutor:
    """The adapter operations and process-wide locks a rewrite needs."""

    execute: Callable[[str], Any]
    statement_recorder: StatementRecorder
    partition_locks: PartitionLocks
    relation_locks: RelationWriteLocks
    generation_query: str


@dataclass(frozen=True)
class SnapshotWorkspace:
    """The live snapshot and the two working relations that stand in for it."""

    destination: str
    work: str
    rebuild: str
    valid_to_column: str
