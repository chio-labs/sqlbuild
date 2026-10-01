from __future__ import annotations

import itertools
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint


def write_fingerprint_from_own_connection(
    *,
    adapter: DuckDbAdapter,
    db_path: Path,
    node_name: str,
    barrier: threading.Barrier,
    failures: list[str],
) -> None:
    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    barrier.wait()
    try:
        write_fingerprint(
            connection=connection,
            execute=adapter.execute,
            database=None,
            schema="main",
            fingerprint=Fingerprint(
                node_type="model",
                node_name=node_name,
                target_database=None,
                target_schema="main",
                target_name=node_name,
                run_id="run_001",
                definition_hash="definition_hash",
                version_hash="version_hash",
                schema_fingerprint="schema_hash",
                definition="SELECT 1",
                metadata_json="{}",
                ts=datetime.now(tz=UTC),
            ),
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_create_table_sql=adapter.render_create_fingerprint_table_sql,
            render_create_index_sqls=adapter.render_create_fingerprint_index_sqls,
        )
    except Exception as error:
        failures.append(f"{node_name}: {type(error).__name__}: {error}")
    finally:
        connection.close()


def run_concurrent_fingerprint_write_round(
    *, adapter: DuckDbAdapter, db_path: Path, writer_count: int, failures: list[str]
) -> int:
    import duckdb

    barrier: threading.Barrier = threading.Barrier(writer_count)
    threads: list[threading.Thread] = [
        threading.Thread(
            target=write_fingerprint_from_own_connection,
            kwargs={
                "adapter": adapter,
                "db_path": db_path,
                "node_name": f"node_{writer_index}",
                "barrier": barrier,
                "failures": failures,
            },
        )
        for writer_index in range(writer_count)
    ]
    thread: threading.Thread
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    check_connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    row: Any = check_connection.execute(
        "SELECT COUNT(DISTINCT node_name) FROM main._sqlbuild_fingerprints"
    ).fetchone()
    check_connection.close()
    return int(getattr(row, "__getitem__", lambda _index: 0)(0))


_MIXED_IDENTITIES: tuple[tuple[str, str], ...] = (
    ("model", "orders"),
    ("model", "customers"),
    ("seed", "orders"),
    ("udf", "is_large_order"),
    ("python", "export_orders"),
)
_HISTORY_RUNS: tuple[tuple[str, int], ...] = (("run_001", 10), ("run_002", 12), ("run_003", 12))


def _history_fingerprint(*, identity: tuple[str, str], run: tuple[str, int]) -> Fingerprint:
    node_type, node_name = identity
    run_id, hour = run
    return Fingerprint(
        node_type=node_type,
        node_name=node_name,
        target_database=None,
        target_schema=None,
        target_name=node_name,
        run_id=run_id,
        definition_hash=f"{node_name}_{run_id}",
        version_hash=f"{node_name}_{run_id}",
        schema_fingerprint="",
        definition=f"SELECT '{run_id}'",
        ts=datetime(2026, 1, 15, hour, 0, 0),
    )


def mixed_fingerprint_history() -> tuple[Fingerprint, ...]:
    """Return three runs of history for models, a seed, a function, and a Python node."""

    return tuple(
        _history_fingerprint(identity=identity, run=run)
        for identity, run in itertools.product(_MIXED_IDENTITIES, _HISTORY_RUNS)
    )
