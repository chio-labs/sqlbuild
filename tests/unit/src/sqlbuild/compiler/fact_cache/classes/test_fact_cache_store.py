from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.fact_cache.classes import fact_cache_store
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.compiler.profiling.main.collect import collect_compile_timings
from tests.unit.src.sqlbuild.compiler.fact_cache.classes._test_types import (
    FactCacheCodeIdentityTestCase,
    FactCacheCorruptionTestCase,
    FactCacheNoPersistenceTestCase,
    FactCacheReadTestCase,
    FactCacheRetentionTestCase,
)
from tests.unit.src.sqlbuild.compiler.fact_cache.classes.helpers import (
    FACT_ALGORITHM,
    FACT_NAMESPACE,
    FACT_VALUE,
    flip_payload_byte,
    publish_fact,
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


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
