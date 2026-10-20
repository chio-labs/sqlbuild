from __future__ import annotations

import json
import multiprocessing
import threading
import time
from multiprocessing.context import SpawnContext
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.sqlite.classes.sqlite_adapter import SqliteAdapter
from tests.integration.src.sqlbuild.adapters.sqlite._test_types import (
    SqliteConcurrentConnectTestCase,
    SqliteInProcessWritersTestCase,
    SqliteKilledWriterTestCase,
    SqliteLockTestCase,
)
from tests.integration.src.sqlbuild.adapters.sqlite.helpers import (
    attempt_write,
    fetch_rows,
    hold_write_lock,
    replace_orders_then_hang,
    run_sql,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteLockTestCase(
            description="second writer fails with a coded error after busy_timeout; reader reads",
            busy_timeout=0.5,
            hold_seconds=4.0,
            expected_code="A702",
            expected_reader_rows=1,
            max_wait_seconds=3.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_held_write_lock_when_second_process_writes_then_it_times_out_with_code(
    test_case: SqliteLockTestCase, adapter: SqliteAdapter, tmp_path: Path
) -> None:
    database_path: Path = tmp_path / "shop.sqlite"
    setup: Any = adapter.connect({"path": str(database_path)})
    run_sql(
        adapter=adapter,
        connection=setup,
        statements=("CREATE TABLE orders (order_id INTEGER)", "INSERT INTO orders VALUES (1)"),
    )
    adapter.close(setup)
    context: SpawnContext = multiprocessing.get_context("spawn")
    ready_path: Path = tmp_path / "ready"
    result_path: Path = tmp_path / "result.json"
    holder: BaseProcess = context.Process(
        target=hold_write_lock,
        kwargs={
            "database_path": str(database_path),
            "ready_path": str(ready_path),
            "hold_seconds": test_case.hold_seconds,
        },
    )
    holder.start()
    try:
        deadline: float = time.monotonic() + 30
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        writer: BaseProcess = context.Process(
            target=attempt_write,
            kwargs={
                "database_path": str(database_path),
                "busy_timeout": test_case.busy_timeout,
                "result_path": str(result_path),
            },
        )
        writer.start()
        reader: Any = adapter.connect({"path": str(database_path)})
        reader_rows: tuple[tuple[object, ...], ...] = fetch_rows(
            adapter=adapter, connection=reader, sql="SELECT COUNT(*) FROM orders"
        )
        writer.join(timeout=30)
        outcome: dict[str, Any] = json.loads(result_path.read_text(encoding="utf-8"))
    finally:
        holder.join(timeout=30)
    committed: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter, connection=reader, sql="SELECT COUNT(*) FROM orders"
    )
    adapter.close(reader)

    assert outcome["code"] == test_case.expected_code
    assert str(database_path) in outcome["message"]
    assert test_case.busy_timeout <= outcome["waited"] < test_case.max_wait_seconds
    assert reader_rows == ((test_case.expected_reader_rows,),)
    assert committed == ((test_case.expected_reader_rows + 1,),)


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteInProcessWritersTestCase(
            description="threads of one process queue for the writer instead of timing out",
            busy_timeout=0.2,
            hold_seconds=1.0,
            expected_rows=((1,), (2,)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_long_write_in_one_thread_when_another_thread_writes_then_it_waits(
    test_case: SqliteInProcessWritersTestCase, adapter: SqliteAdapter, tmp_path: Path
) -> None:
    config: dict[str, object] = {
        "path": str(tmp_path / "shop.sqlite"),
        "busy_timeout": test_case.busy_timeout,
    }
    first: Any = adapter.connect(config)
    second: Any = adapter.connect(config)
    run_sql(
        adapter=adapter, connection=first, statements=("CREATE TABLE orders (order_id INTEGER)",)
    )
    started: threading.Event = threading.Event()
    errors: list[BaseException] = []

    def hold() -> None:
        with adapter.transaction(first):
            adapter.execute(connection=first, sql="INSERT INTO orders VALUES (1)")
            started.set()
            time.sleep(test_case.hold_seconds)

    def write() -> None:
        started.wait(timeout=10)
        try:
            adapter.execute(connection=second, sql="INSERT INTO orders VALUES (2)")
        except BaseException as error:
            errors.append(error)

    threads: tuple[threading.Thread, ...] = (
        threading.Thread(target=hold),
        threading.Thread(target=write),
    )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter, connection=first, sql="SELECT order_id FROM orders ORDER BY 1"
    )
    adapter.close(first)
    adapter.close(second)

    assert errors == []
    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteKilledWriterTestCase(
            description="a writer killed mid-transaction leaves committed data and no lock behind",
            expected_rows=((1,), (2,), (3,)),
            expected_tables=(("orders",),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_writer_killed_mid_transaction_when_reopening_then_target_is_unchanged(
    test_case: SqliteKilledWriterTestCase, adapter: SqliteAdapter, tmp_path: Path
) -> None:
    database_path: Path = tmp_path / "shop.sqlite"
    setup: Any = adapter.connect({"path": str(database_path)})
    run_sql(
        adapter=adapter,
        connection=setup,
        statements=(
            "CREATE TABLE orders (order_id INTEGER)",
            "INSERT INTO orders VALUES (1), (2), (3)",
        ),
    )
    adapter.close(setup)
    context: SpawnContext = multiprocessing.get_context("spawn")
    ready_path: Path = tmp_path / "ready"
    writer: BaseProcess = context.Process(
        target=replace_orders_then_hang,
        kwargs={"database_path": str(database_path), "ready_path": str(ready_path)},
    )
    writer.start()
    try:
        deadline: float = time.monotonic() + 30
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready_path.exists()
    finally:
        writer.kill()
        writer.join(timeout=30)
    reopened: Any = adapter.connect({"path": str(database_path), "busy_timeout": 0.5})
    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter, connection=reopened, sql="SELECT order_id FROM orders ORDER BY 1"
    )
    tables: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=reopened,
        sql="SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'orders%'",
    )
    adapter.execute(connection=reopened, sql="INSERT INTO orders VALUES (4)")
    adapter.close(reopened)

    assert rows == test_case.expected_rows
    assert tables == test_case.expected_tables


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteConcurrentConnectTestCase(
            description="threads opening a new file together all switch it to WAL",
            connections=4,
            attempts=25,
            expected_open_connections=100,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_new_file_when_threads_connect_together_then_every_connection_opens(
    test_case: SqliteConcurrentConnectTestCase, adapter: SqliteAdapter, tmp_path: Path
) -> None:
    errors: list[BaseException] = []
    opened_count: int = 0
    for attempt in range(test_case.attempts):
        config: dict[str, object] = {"path": str(tmp_path / f"shop_{attempt}.sqlite")}
        barrier: threading.Barrier = threading.Barrier(test_case.connections)
        opened: list[Any] = []

        def connect(
            config: dict[str, object] = config,
            barrier: threading.Barrier = barrier,
            opened: list[Any] = opened,
        ) -> None:
            barrier.wait(timeout=10)
            try:
                opened.append(adapter.connect(config))
            except BaseException as error:
                errors.append(error)

        threads: tuple[threading.Thread, ...] = tuple(
            threading.Thread(target=connect) for _ in range(test_case.connections)
        )
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        opened_count += len(opened)
        for connection in opened:
            adapter.close(connection)

    assert (opened_count, errors) == (test_case.expected_open_connections, [])
