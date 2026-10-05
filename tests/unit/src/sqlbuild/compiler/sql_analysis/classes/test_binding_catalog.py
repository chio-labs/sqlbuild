"""Prepared compact analysis jobs keep their catalog snapshot and run beside catalog updates."""

from concurrent.futures import Future, ThreadPoolExecutor

import pytest

from sqlbuild.compiler.sql_analysis.classes.binding_catalog import BindingCatalog
from sqlbuild.compiler.sql_analysis.types import NativeCompactAnalysisJob
from tests.unit.src.sqlbuild.compiler.sql_analysis.classes._test_types import (
    CompactJobRerunCase,
    CompactJobSnapshotCase,
    ConcurrentCompactJobCase,
)
from tests.unit.src.sqlbuild.compiler.sql_analysis.classes.helpers import (
    analyze_now,
    orders_catalog,
    orders_payload,
    retype_orders,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CompactJobSnapshotCase(
            description="retyped input",
            query_sql="SELECT id, amount + 1 AS amount FROM orders",
            prepared_types={"id": "INTEGER", "amount": "DOUBLE"},
            updated_types={"id": "VARCHAR", "amount": "VARCHAR"},
            expected_changed_by_update=True,
        ),
        CompactJobSnapshotCase(
            description="star over a widened input",
            query_sql="SELECT * FROM orders",
            prepared_types={"id": "INTEGER"},
            updated_types={"id": "INTEGER", "status": "VARCHAR"},
            expected_changed_by_update=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_prepared_job_when_catalog_changes_before_run_then_uses_prepared_shapes(
    test_case: CompactJobSnapshotCase,
) -> None:
    catalog: BindingCatalog = orders_catalog(test_case.prepared_types)
    payload: bytes = orders_payload(test_case.query_sql)
    expected: bytes = analyze_now(catalog=catalog, payload=payload)
    job: NativeCompactAnalysisJob = catalog.native.prepare_compact(payload)
    retype_orders(catalog=catalog, types=test_case.updated_types)

    assert job.run() == expected
    assert (analyze_now(catalog=catalog, payload=payload) != expected) is (
        test_case.expected_changed_by_update
    )


@pytest.mark.parametrize(
    "test_case",
    [CompactJobRerunCase("finished job", "SELECT id FROM orders", "already ran")],
    ids=lambda case: case.description,
)
def test_given_finished_job_when_running_again_then_rejects_the_rerun(
    test_case: CompactJobRerunCase,
) -> None:
    catalog: BindingCatalog = orders_catalog({"id": "INTEGER"})
    job: NativeCompactAnalysisJob = catalog.native.prepare_compact(
        orders_payload(test_case.query_sql)
    )
    _ = job.run()

    with pytest.raises(ValueError, match=test_case.expected_error):
        _ = job.run()


@pytest.mark.parametrize(
    "test_case",
    [
        ConcurrentCompactJobCase(
            description="eight jobs beside repeated retyping",
            job_count=8,
            prepared_types={"id": "INTEGER", "amount": "DOUBLE"},
            expected_matches_serial=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_running_jobs_when_catalog_updates_concurrently_then_each_matches_serial_run(
    test_case: ConcurrentCompactJobCase,
) -> None:
    catalog: BindingCatalog = orders_catalog(test_case.prepared_types)
    payloads: list[bytes] = [
        orders_payload(f"SELECT id, amount * {index} AS amount FROM orders")
        for index in range(test_case.job_count)
    ]
    expected: list[bytes] = [analyze_now(catalog=catalog, payload=payload) for payload in payloads]
    jobs: list[NativeCompactAnalysisJob] = [
        catalog.native.prepare_compact(payload) for payload in payloads
    ]
    with ThreadPoolExecutor(max_workers=test_case.job_count) as executor:
        futures: list[Future[bytes]] = [executor.submit(job.run) for job in jobs]
        for index in range(test_case.job_count):
            retype_orders(
                catalog=catalog, types={"id": "BIGINT", "amount": f"DECIMAL(18, {index})"}
            )
        actual: list[bytes] = [future.result() for future in futures]

    assert (actual == expected) is test_case.expected_matches_serial


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
