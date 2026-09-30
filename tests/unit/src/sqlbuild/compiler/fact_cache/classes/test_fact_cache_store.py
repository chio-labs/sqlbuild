from __future__ import annotations

import hashlib
import pickle
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from sqlbuild.compiler.fact_cache.classes import fact_cache_store
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.compiler.profiling.main.collect import collect_compile_timings
from sqlbuild.spec.contracts.models import SourceLocation
from tests.unit.src.sqlbuild.compiler.fact_cache.classes._test_types import (
    FactCacheCorruptionTestCase,
)

_NAMESPACE: str = "unit"
_ALGORITHM: str = "unit-facts-v1"
_FACT: tuple[SourceLocation, ...] = (
    SourceLocation(path=Path("models/orders.sql"), line=3, column=5, end_line=3, end_column=12),
)


def _database(root: Path) -> Path:
    return next(root.rglob(f"{_NAMESPACE}.sqlite3"))


def _publish(root: Path, *, key_parts: tuple[str, ...], slot: str, value: object) -> str:
    with FactCacheStore(root=root, namespace=_NAMESPACE, algorithm=_ALGORITHM) as store:
        key: str = store.key(*key_parts)
        store.stage(key=key, slot=slot, value=value)
    return key


def _read(root: Path, *, key_parts: tuple[str, ...]) -> dict[str, object]:
    with FactCacheStore(root=root, namespace=_NAMESPACE, algorithm=_ALGORITHM) as store:
        return store.read_many((store.key(*key_parts),))


def _overwrite_payload(database: Path, payload: bytes, *, keep_digest: bool) -> None:
    with closing(sqlite3.connect(database)) as connection, connection:
        cache_key: str = connection.execute("SELECT cache_key FROM fact").fetchone()[0]
        digest: str = (
            hashlib.sha256(cache_key.encode() + b"\0" + payload).hexdigest()
            if keep_digest
            else "0" * 64
        )
        _ = connection.execute("UPDATE fact SET payload = ?, digest = ?", (payload, digest))


def _flip_payload_byte(root: Path) -> None:
    database: Path = _database(root)
    with closing(sqlite3.connect(database)) as connection, connection:
        payload: bytes = connection.execute("SELECT payload FROM fact").fetchone()[0]
        _ = connection.execute("UPDATE fact SET payload = ?", (payload[:-1] + b"\x00",))


def _write_untrusted_global(root: Path) -> None:
    _overwrite_payload(_database(root), pickle.dumps(Path.home, protocol=5), keep_digest=True)


def _truncate_verified_payload(root: Path) -> None:
    _overwrite_payload(_database(root), b"\x80\x05", keep_digest=True)


def _replace_database_with_garbage(root: Path) -> None:
    _database(root).write_bytes(b"not a sqlite database")


CORRUPTION_CASES: list[FactCacheCorruptionTestCase] = [
    FactCacheCorruptionTestCase(description="payload_bytes_changed", corrupt=_flip_payload_byte),
    FactCacheCorruptionTestCase(
        description="verified_payload_references_function", corrupt=_write_untrusted_global
    ),
    FactCacheCorruptionTestCase(
        description="verified_payload_truncated", corrupt=_truncate_verified_payload
    ),
    FactCacheCorruptionTestCase(
        description="database_file_replaced", corrupt=_replace_database_with_garbage
    ),
]


def test_given_published_fact_when_reading_same_inputs_then_returns_equal_value(
    tmp_path: Path,
) -> None:
    key: str = _publish(tmp_path, key_parts=("orders", "SELECT 1"), slot="orders", value=_FACT)

    with collect_compile_timings() as timings:
        found: dict[str, object] = _read(tmp_path, key_parts=("orders", "SELECT 1"))

    assert found == {key: _FACT}
    assert timings.metrics["fact_cache_hits"] == 1
    assert timings.metrics["fact_cache_misses"] == 0


def test_given_published_fact_when_any_input_changes_then_misses(tmp_path: Path) -> None:
    _ = _publish(tmp_path, key_parts=("orders", "SELECT 1"), slot="orders", value=_FACT)

    assert _read(tmp_path, key_parts=("orders", "SELECT 2")) == {}
    assert _read(tmp_path, key_parts=("orders", "SELECT 1", "")) == {}
    assert _read(tmp_path, key_parts=("ordersSELECT 1",)) == {}


def test_given_published_fact_when_producing_code_changes_then_misses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = _publish(tmp_path, key_parts=("orders",), slot="orders", value=_FACT)
    monkeypatch.setattr(fact_cache_store, "installed_code_identity", lambda: "next-release")

    assert _read(tmp_path, key_parts=("orders",)) == {}


def test_given_published_fact_when_algorithm_changes_then_misses(tmp_path: Path) -> None:
    _ = _publish(tmp_path, key_parts=("orders",), slot="orders", value=_FACT)

    with FactCacheStore(root=tmp_path, namespace=_NAMESPACE, algorithm="unit-facts-v2") as store:
        assert store.read_many((store.key("orders"),)) == {}


@pytest.mark.parametrize(
    "test_case", CORRUPTION_CASES, ids=[case.description for case in CORRUPTION_CASES]
)
def test_given_corrupted_fact_when_reading_then_misses_and_republishes(
    tmp_path: Path, test_case: FactCacheCorruptionTestCase
) -> None:
    _ = _publish(tmp_path, key_parts=("orders",), slot="orders", value=_FACT)
    test_case.corrupt(tmp_path)

    assert _read(tmp_path, key_parts=("orders",)) == {}

    _database(tmp_path).unlink()
    key: str = _publish(tmp_path, key_parts=("orders",), slot="orders", value=_FACT)
    assert _read(tmp_path, key_parts=("orders",)) == {key: _FACT}


def test_given_new_fact_for_same_slot_when_publishing_then_previous_fact_is_pruned(
    tmp_path: Path,
) -> None:
    _ = _publish(tmp_path, key_parts=("orders", "v1"), slot="orders", value=_FACT)
    _ = _publish(tmp_path, key_parts=("orders", "v2"), slot="orders", value=_FACT)
    _ = _publish(tmp_path, key_parts=("customers", "v1"), slot="customers", value=_FACT)

    with closing(sqlite3.connect(_database(tmp_path))) as connection:
        slots: list[tuple[str]] = connection.execute(
            "SELECT slot FROM fact ORDER BY slot"
        ).fetchall()
    assert slots == [("customers",), ("orders",)]
    assert _read(tmp_path, key_parts=("orders", "v1")) == {}


def test_given_disabled_root_when_staging_then_nothing_is_persisted(tmp_path: Path) -> None:
    with FactCacheStore(root=None, namespace=_NAMESPACE, algorithm=_ALGORITHM) as store:
        store.stage(key=store.key("orders"), slot="orders", value=_FACT)
        assert not store.enabled
        assert store.read_many((store.key("orders"),)) == {}

    assert not any(tmp_path.iterdir())


def test_given_failed_invocation_when_exiting_then_staged_facts_are_discarded(
    tmp_path: Path,
) -> None:
    with (
        pytest.raises(RuntimeError),
        FactCacheStore(root=tmp_path, namespace=_NAMESPACE, algorithm=_ALGORITHM) as store,
    ):
        store.stage(key=store.key("orders"), slot="orders", value=_FACT)
        raise RuntimeError("compile failed")

    assert not list(tmp_path.rglob("*.sqlite3"))


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
