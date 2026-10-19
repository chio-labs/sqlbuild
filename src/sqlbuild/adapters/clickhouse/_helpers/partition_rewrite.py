"""Rewrite whole ClickHouse partitions: the write primitive behind merges and deletes."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.clickhouse._helpers.type_text import quote_string
from sqlbuild.adapters.clickhouse.constants import (
    GENERATION_COMMENT_PREFIX,
    MAX_IDENTIFIER_LENGTH,
    REWRITE_DELTA_INFIX,
    REWRITE_STAGING_INFIX,
)
from sqlbuild.adapters.clickhouse.models import PartitionRewrite, RewriteExecutor, RewriteTables
from sqlbuild.runtime.execution_limits.main.execution_deadlines_suspended import (
    execution_deadlines_suspended,
)


def rewrite_partitions(*, request: PartitionRewrite, executor: RewriteExecutor) -> int:
    """Apply one rewrite atomically and return the number of incoming rows."""

    digest: str = hashlib.sha256(
        f"{request.destination}\0{request.delta_insert_sql}\0{request.displaced_predicate}".encode()
    ).hexdigest()[:12]
    delta: str = artifact_relation(
        relation=request.destination, infix=REWRITE_DELTA_INFIX, digest=digest
    )
    tables: RewriteTables = RewriteTables(
        destination=request.destination,
        delta=delta,
        staging=artifact_relation(
            relation=request.destination, infix=REWRITE_STAGING_INFIX, digest=digest
        ),
        displaced_predicate=request.displaced_predicate.replace("{delta}", delta),
    )

    def run(sql: str) -> Any:
        executor.statement_recorder.record(sql)
        return executor.execute(sql)

    try:
        run(f"DROP TABLE IF EXISTS {delta}")
        run(f"CREATE TABLE {delta} AS {request.destination}")
        run(request.delta_insert_sql.replace("{delta}", delta))
        incoming: int = int(run(f"SELECT count() FROM {delta}").fetchone()[0])
        partitions: tuple[str, ...] = tuple(
            sorted(
                str(row[0])
                for row in run(
                    f"SELECT DISTINCT _partition_id FROM {delta} UNION DISTINCT "
                    f"SELECT DISTINCT _partition_id FROM {request.destination} "
                    f"WHERE ifNull({tables.displaced_predicate}, 0)"
                ).fetchall()
            )
        )
        if len(partitions) > 1:
            _exchange_replacement(run=run, tables=tables, partitions=partitions, executor=executor)
        else:
            _replace_partition(run=run, tables=tables, partitions=partitions, executor=executor)
        return incoming
    finally:
        with execution_deadlines_suspended():
            run(f"DROP TABLE IF EXISTS {tables.staging}")
            run(f"DROP TABLE IF EXISTS {delta}")


def _replace_partition(
    *,
    run: Callable[[str], Any],
    tables: RewriteTables,
    partitions: tuple[str, ...],
    executor: RewriteExecutor,
) -> None:
    """Swap the only rewritten partition in place; nothing to do without one."""

    if not partitions:
        return
    with (
        executor.relation_locks.shared(destination=tables.destination),
        executor.partition_locks.locked(destination=tables.destination, partitions=partitions),
    ):
        run(f"DROP TABLE IF EXISTS {tables.staging}")
        run(f"CREATE TABLE {tables.staging} AS {tables.destination}")
        _insert_rewritten_rows(run=run, tables=tables, partitions=partitions)
        run(
            f"ALTER TABLE {tables.destination} REPLACE PARTITION ID "
            f"{quote_string(partitions[0])} FROM {tables.staging}"
        )


def _exchange_replacement(
    *,
    run: Callable[[str], Any],
    tables: RewriteTables,
    partitions: tuple[str, ...],
    executor: RewriteExecutor,
) -> None:
    """Exchange the table for a copy that hard-links the partitions it keeps."""

    drops: str = ", ".join(
        f"DROP PARTITION ID {quote_string(partition)}" for partition in partitions
    )
    with executor.relation_locks.exclusive(destination=tables.destination):
        generation: str = generation_comment(run(executor.generation_query).fetchone())
        run(f"DROP TABLE IF EXISTS {tables.staging}")
        run(f"CREATE TABLE {tables.staging} AS {tables.destination}")
        run(f"ALTER TABLE {tables.staging} ATTACH PARTITION ALL FROM {tables.destination}")
        run(f"ALTER TABLE {tables.staging} {drops}")
        _insert_rewritten_rows(run=run, tables=tables, partitions=partitions)
        run(f"ALTER TABLE {tables.staging} MODIFY COMMENT {quote_string(generation)}")
        run(f"EXCHANGE TABLES {tables.staging} AND {tables.destination}")


def _insert_rewritten_rows(
    *, run: Callable[[str], Any], tables: RewriteTables, partitions: tuple[str, ...]
) -> None:
    """Fill the staging table with the kept rows of ``partitions`` and every delta row."""

    partition_list: str = ", ".join(quote_string(partition) for partition in partitions)
    run(
        f"INSERT INTO {tables.staging} SELECT * FROM {tables.destination} "
        f"WHERE _partition_id IN ({partition_list}) "
        f"AND NOT ifNull({tables.displaced_predicate}, 0)"
    )
    run(f"INSERT INTO {tables.staging} SELECT * FROM {tables.delta}")


def generation_comment(row: tuple[object, ...] | None) -> str:
    """The comment naming a table's generation: its own, else one made from its UUID."""

    if row is None:
        raise AdapterUserError(message="the partition rewrite target no longer exists")
    comment: str = str(row[1] or "")
    if comment.startswith(GENERATION_COMMENT_PREFIX):
        return comment
    return f"{GENERATION_COMMENT_PREFIX}{row[0]}"


def artifact_relation(*, relation: str, infix: str, digest: str) -> str:
    """Return a sibling relation name bounded by the identifier limit."""

    parts: list[str] = relation.rsplit(".", 1)
    name: str = parts[-1].strip('"`')
    suffix: str = f"{infix}{digest}"
    fitted: str = name[: max(1, MAX_IDENTIFIER_LENGTH - len(suffix))] + suffix
    quoted: str = '"' + fitted.replace('"', '""') + '"'
    return quoted if len(parts) == 1 else f"{parts[0]}.{quoted}"
