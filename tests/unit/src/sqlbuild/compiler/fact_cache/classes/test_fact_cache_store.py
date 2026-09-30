from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.fact_cache._helpers import publication
from sqlbuild.compiler.fact_cache.classes import fact_cache_store
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.compiler.profiling.main.collect import collect_compile_timings
from tests.unit.src.sqlbuild.compiler.fact_cache.classes._test_types import (
    FactCacheCodeIdentityTestCase,
    FactCacheCorruptionTestCase,
    FactCacheNoPersistenceTestCase,
    FactCacheParameterLimitTestCase,
    FactCacheReadTestCase,
    FactCacheRetentionTestCase,
    FactCacheWriterErrorTestCase,
)
from tests.unit.src.sqlbuild.compiler.fact_cache.classes.helpers import (
    FACT_ALGORITHM,
    FACT_NAMESPACE,
    FACT_VALUE,
    flip_payload_byte,
    publish_fact,
    publish_facts,
    read_fact,
    replace_database_with_garbage,
    stored_fact_slots,
    truncate_verified_payload,
    write_untrusted_global,
)


@pytest.mark.parametrize(
    "test_case",
    (
        FactCacheReadTestCase(
            description="same_inputs_hit",
            read_key_parts=("orders", "SELECT 1"),
            read_algorithm=FACT_ALGORITHM,
            expected_hit=True,
            expected_metrics=(1, 0),
        ),
        FactCacheReadTestCase(
            description="changed_input_misses",
            read_key_parts=("orders", "SELECT 2"),
            read_algorithm=FACT_ALGORITHM,
            expected_hit=False,
            expected_metrics=(0, 1),
        ),
        FactCacheReadTestCase(
            description="extra_empty_input_misses",
            read_key_parts=("orders", "SELECT 1", ""),
            read_algorithm=FACT_ALGORITHM,
            expected_hit=False,
            expected_metrics=(0, 1),
        ),
        FactCacheReadTestCase(
            description="concatenated_inputs_miss",
            read_key_parts=("ordersSELECT 1",),
            read_algorithm=FACT_ALGORITHM,
            expected_hit=False,
            expected_metrics=(0, 1),
        ),
        FactCacheReadTestCase(
            description="changed_algorithm_misses",
            read_key_parts=("orders", "SELECT 1"),
            read_algorithm="unit-facts-v2",
            expected_hit=False,
            expected_metrics=(0, 1),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_published_fact_when_reading_then_hits_only_for_identical_inputs(
    tmp_path: Path, test_case: FactCacheReadTestCase
) -> None:
    key: str = publish_fact(tmp_path, key_parts=("orders", "SELECT 1"), slot="orders")

    with collect_compile_timings() as timings:
        found: dict[str, object] = read_fact(
            tmp_path, key_parts=test_case.read_key_parts, algorithm=test_case.read_algorithm
        )

    assert (found == {key: FACT_VALUE}) is test_case.expected_hit
    assert (
        timings.metrics["fact_cache_hits"],
        timings.metrics["fact_cache_misses"],
    ) == test_case.expected_metrics


@pytest.mark.parametrize(
    "test_case",
    (
        FactCacheCodeIdentityTestCase(
            description="next_release", next_code_identity="next-release", expected_found_count=0
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_published_fact_when_producing_code_changes_then_misses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: FactCacheCodeIdentityTestCase
) -> None:
    _ = publish_fact(tmp_path, key_parts=("orders",), slot="orders")
    monkeypatch.setattr(
        fact_cache_store, "installed_code_identity", lambda: test_case.next_code_identity
    )

    assert len(read_fact(tmp_path, key_parts=("orders",))) == test_case.expected_found_count


@pytest.mark.parametrize(
    "test_case",
    (
        FactCacheCorruptionTestCase(
            description="payload_bytes_changed",
            corrupt=flip_payload_byte,
            expected_found_count=0,
            expected_republished_hit=True,
        ),
        FactCacheCorruptionTestCase(
            description="verified_payload_references_function",
            corrupt=write_untrusted_global,
            expected_found_count=0,
            expected_republished_hit=True,
        ),
        FactCacheCorruptionTestCase(
            description="verified_payload_truncated",
            corrupt=truncate_verified_payload,
            expected_found_count=0,
            expected_republished_hit=True,
        ),
        FactCacheCorruptionTestCase(
            description="database_file_replaced",
            corrupt=replace_database_with_garbage,
            expected_found_count=0,
            expected_republished_hit=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_corrupted_fact_when_reading_then_misses_and_next_publication_repairs_it(
    tmp_path: Path, test_case: FactCacheCorruptionTestCase
) -> None:
    _ = publish_fact(tmp_path, key_parts=("orders",), slot="orders")
    test_case.corrupt(tmp_path)

    assert len(read_fact(tmp_path, key_parts=("orders",))) == test_case.expected_found_count

    key: str = publish_fact(tmp_path, key_parts=("orders",), slot="orders")
    assert (
        read_fact(tmp_path, key_parts=("orders",)) == {key: FACT_VALUE}
    ) is test_case.expected_republished_hit


@pytest.mark.parametrize(
    "test_case",
    (
        FactCacheRetentionTestCase(
            description="same_slot_replaced",
            publications=(
                (("orders", "v1"), "orders"),
                (("orders", "v2"), "orders"),
                (("customers", "v1"), "customers"),
            ),
            stale_key_parts=("orders", "v1"),
            expected_slots=["customers", "orders"],
            expected_stale_found_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_new_fact_for_same_slot_when_publishing_then_previous_fact_is_pruned(
    tmp_path: Path, test_case: FactCacheRetentionTestCase
) -> None:
    for key_parts, slot in test_case.publications:
        _ = publish_fact(tmp_path, key_parts=key_parts, slot=slot)

    assert stored_fact_slots(tmp_path) == test_case.expected_slots
    assert (
        len(read_fact(tmp_path, key_parts=test_case.stale_key_parts))
        == test_case.expected_stale_found_count
    )


@pytest.mark.parametrize(
    "test_case",
    (
        FactCacheNoPersistenceTestCase(
            description="disabled_root", expected_enabled=False, expected_database_files=[]
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_disabled_root_when_staging_then_nothing_is_persisted(
    tmp_path: Path, test_case: FactCacheNoPersistenceTestCase
) -> None:
    with FactCacheStore(root=None, namespace=FACT_NAMESPACE, algorithm=FACT_ALGORITHM) as store:
        store.stage(key=store.key("orders"), slot="orders", value=FACT_VALUE)
        assert store.enabled is test_case.expected_enabled
        assert store.read_many((("orders", store.key("orders")),)) == {}

    assert list(tmp_path.iterdir()) == test_case.expected_database_files


@pytest.mark.parametrize(
    "test_case",
    (
        FactCacheNoPersistenceTestCase(
            description="failed_invocation", expected_enabled=True, expected_database_files=[]
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_failed_invocation_when_exiting_then_staged_facts_are_discarded(
    tmp_path: Path, test_case: FactCacheNoPersistenceTestCase
) -> None:
    with (
        pytest.raises(RuntimeError),
        FactCacheStore(root=tmp_path, namespace=FACT_NAMESPACE, algorithm=FACT_ALGORITHM) as store,
    ):
        assert store.enabled is test_case.expected_enabled
        store.stage(key=store.key("orders"), slot="orders", value=FACT_VALUE)
        raise RuntimeError("compile failed")

    assert list(tmp_path.rglob("*.sqlite3")) == test_case.expected_database_files


@pytest.mark.parametrize(
    "test_case",
    (
        FactCacheWriterErrorTestCase(
            description="busy_database_keeps_rows",
            error=sqlite3.OperationalError("database is locked"),
            expected_earlier_found_count=1,
        ),
        FactCacheWriterErrorTestCase(
            description="integrity_error_keeps_rows",
            error=sqlite3.IntegrityError("constraint failed"),
            expected_earlier_found_count=1,
        ),
        FactCacheWriterErrorTestCase(
            description="interface_error_keeps_rows",
            error=sqlite3.InterfaceError("bad parameter"),
            expected_earlier_found_count=1,
        ),
        FactCacheWriterErrorTestCase(
            description="unreadable_database_is_replaced",
            error=sqlite3.DatabaseError("file is not a database"),
            expected_earlier_found_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_writer_error_when_publishing_then_only_corruption_discards_rows_and_nothing_escapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: FactCacheWriterErrorTestCase
) -> None:
    _ = publish_fact(tmp_path, key_parts=("orders",), slot="orders")
    escaped: list[threading.ExceptHookArgs] = []
    monkeypatch.setattr(threading, "excepthook", escaped.append)

    def failing_insert(**_: object) -> None:
        raise test_case.error

    monkeypatch.setattr(publication, "_insert_records", failing_insert)
    _ = publish_fact(tmp_path, key_parts=("customers",), slot="customers")
    monkeypatch.undo()

    assert escaped == []
    assert len(read_fact(tmp_path, key_parts=("orders",))) == (
        test_case.expected_earlier_found_count
    )


@pytest.mark.parametrize(
    "test_case",
    (
        FactCacheParameterLimitTestCase(
            description="sqlite_before_3_32",
            max_bound_parameters=999,
            fact_count=600,
            expected_stored_count=600,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sqlite_parameter_limit_when_publishing_many_facts_then_all_are_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: FactCacheParameterLimitTestCase
) -> None:
    connect: Callable[..., sqlite3.Connection] = sqlite3.connect

    def limited_connect(database: Path, timeout: float = 5.0) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(database, timeout=timeout)
        _ = connection.setlimit(
            sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, test_case.max_bound_parameters
        )
        return connection

    monkeypatch.setattr(sqlite3, "connect", limited_connect)
    slots: tuple[str, ...] = tuple(f"order_{index:04d}" for index in range(test_case.fact_count))

    publish_facts(tmp_path, slots=slots)

    stored: list[str] = stored_fact_slots(tmp_path)
    assert len(stored) == test_case.expected_stored_count
    assert stored == list(slots)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
