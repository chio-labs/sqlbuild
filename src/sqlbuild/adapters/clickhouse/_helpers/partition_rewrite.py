"""Rewrite whole ClickHouse partitions: the write primitive behind merges and deletes."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlbuild.adapters.clickhouse._helpers.type_text import quote_string
from sqlbuild.adapters.clickhouse.constants import (
    MAX_IDENTIFIER_LENGTH,
    REWRITE_DELTA_INFIX,
    REWRITE_STAGING_INFIX,
)
from sqlbuild.adapters.clickhouse.models import PartitionRewrite, RewriteExecutor
from sqlbuild.runtime.execution_limits.main.execution_deadlines_suspended import (
    execution_deadlines_suspended,
)


def rewrite_partitions(*, request: PartitionRewrite, executor: RewriteExecutor) -> int:
    """Apply one rewrite and return the number of incoming rows."""

    digest: str = hashlib.sha256(
        f"{request.destination}\0{request.delta_insert_sql}\0{request.displaced_predicate}".encode()
    ).hexdigest()[:12]
    delta: str = artifact_relation(
        relation=request.destination, infix=REWRITE_DELTA_INFIX, digest=digest
    )
    staging: str = artifact_relation(
        relation=request.destination, infix=REWRITE_STAGING_INFIX, digest=digest
    )
    predicate: str = request.displaced_predicate.replace("{delta}", delta)

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
                    f"WHERE ifNull({predicate}, 0)"
                ).fetchall()
            )
        )
        if not partitions:
            return incoming
        partition_list: str = ", ".join(quote_string(partition) for partition in partitions)
        with executor.partition_locks.locked(
            destination=request.destination, partitions=partitions
        ):
            run(f"DROP TABLE IF EXISTS {staging}")
            run(f"CREATE TABLE {staging} AS {request.destination}")
            run(
                f"INSERT INTO {staging} SELECT * FROM {request.destination} "
                f"WHERE _partition_id IN ({partition_list}) AND NOT ifNull({predicate}, 0)"
            )
            run(f"INSERT INTO {staging} SELECT * FROM {delta}")
            partition: str
            for partition in partitions:
                run(
                    f"ALTER TABLE {request.destination} REPLACE PARTITION ID "
                    f"{quote_string(partition)} FROM {staging}"
                )
        return incoming
    finally:
        with execution_deadlines_suspended():
            run(f"DROP TABLE IF EXISTS {staging}")
            run(f"DROP TABLE IF EXISTS {delta}")


def artifact_relation(*, relation: str, infix: str, digest: str) -> str:
    """Return a sibling relation name bounded by the identifier limit."""

    parts: list[str] = relation.rsplit(".", 1)
    name: str = parts[-1].strip('"`')
    suffix: str = f"{infix}{digest}"
    fitted: str = name[: max(1, MAX_IDENTIFIER_LENGTH - len(suffix))] + suffix
    quoted: str = '"' + fitted.replace('"', '""') + '"'
    return quoted if len(parts) == 1 else f"{parts[0]}.{quoted}"
