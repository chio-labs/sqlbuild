from __future__ import annotations

from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.commands._helpers.cost.collection import finalize_build_cost
from sqlbuild.cost.classes.run_cost_store import RunCostStore
from sqlbuild.cost.models import CostRunRecord, RunCostSummary
from sqlbuild.cost.types import CostCapability, CostStatus
from tests.unit.src.sqlbuild.cli.commands._helpers.cost._test_types import (
    CostCollectionTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.cost.helpers import (
    build_cost_finalization,
)


class _CostAdapter:
    def __init__(self, *, error: BaseException | None = None) -> None:
        self.error = error

    def cost_capability(self) -> CostCapability:
        return CostCapability.SNOWFLAKE_QUERY_HISTORY

    def collect_run_cost(self, **kwargs: Any) -> RunCostSummary:
        if self.error is not None:
            raise self.error
        return RunCostSummary(
            status=CostStatus.COMPLETE,
            usd_per_credit=kwargs["usd_per_credit"],
            rate_source=kwargs["rate_source"],
            estimated_compute_credits=Decimal("0.01"),
            estimated_usd=Decimal("0.03"),
        )


class _FailingOutput:
    def write(self, value: str) -> int:
        del value
        raise OSError("output unavailable")

    def flush(self) -> None:
        raise OSError("output unavailable")


class _NoCostAdapter(_CostAdapter):
    def cost_capability(self) -> CostCapability:
        return CostCapability.NONE

    def collect_run_cost(self, **kwargs: Any) -> RunCostSummary:
        del kwargs
        raise AssertionError("collection must not run")


@pytest.mark.parametrize(
    "test_case",
    [
        CostCollectionTestCase(
            description="unsupported adapter leaves output unchanged",
            expected_record_present=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_adapter_when_finalizing_then_build_output_is_unchanged(
    test_case: CostCollectionTestCase,
    tmp_path: Path,
) -> None:
    output: StringIO = StringIO()

    record: CostRunRecord | None = finalize_build_cost(
        build_cost_finalization(tmp_path=tmp_path, adapter=object(), output_stream=output)
    )

    assert (record is not None) is test_case.expected_record_present
    assert output.getvalue() == ""


@pytest.mark.parametrize(
    "test_case",
    [
        CostCollectionTestCase(
            description="adapter with no cost capability remains unchanged",
            expected_record_present=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_without_cost_capability_when_finalizing_then_collection_is_skipped(
    test_case: CostCollectionTestCase,
    tmp_path: Path,
) -> None:
    output: StringIO = StringIO()

    record: CostRunRecord | None = finalize_build_cost(
        build_cost_finalization(
            tmp_path=tmp_path,
            adapter=_NoCostAdapter(),
            output_stream=output,
        )
    )

    assert (record is not None) is test_case.expected_record_present
    assert output.getvalue() == ""


@pytest.mark.parametrize(
    "test_case",
    [
        CostCollectionTestCase(
            description="collection exception persists failed status without raising",
            expected_record_present=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_collection_exception_when_finalizing_then_warning_is_written_without_raising(
    test_case: CostCollectionTestCase,
    tmp_path: Path,
) -> None:
    output: StringIO = StringIO()

    record: CostRunRecord | None = finalize_build_cost(
        build_cost_finalization(
            tmp_path=tmp_path,
            adapter=_CostAdapter(error=RuntimeError("history unavailable")),
            output_stream=output,
        )
    )

    assert (record is not None) is test_case.expected_record_present
    assert record is not None
    assert record.cost.status == CostStatus.COLLECTION_FAILED
    assert record.build_status == "success"
    assert RunCostStore.read(project_dir=tmp_path, run_id="run-1") == record
    assert "Cost telemetry failed during collection (RuntimeError)" in output.getvalue()
    assert "build result unchanged" in output.getvalue()


@pytest.mark.parametrize(
    "test_case",
    [
        CostCollectionTestCase(
            description="collection interrupt preserves the completed build result",
            expected_record_present=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_collection_interrupt_when_finalizing_then_failed_artifact_is_persisted_without_raise(
    test_case: CostCollectionTestCase,
    tmp_path: Path,
) -> None:
    output: StringIO = StringIO()

    record: CostRunRecord | None = finalize_build_cost(
        build_cost_finalization(
            tmp_path=tmp_path,
            adapter=_CostAdapter(error=KeyboardInterrupt()),
            output_stream=output,
        )
    )

    assert (record is not None) is test_case.expected_record_present
    assert record is not None
    assert record.cost.status == CostStatus.COLLECTION_FAILED
    assert record.build_status == "success"
    assert "KeyboardInterrupt" in output.getvalue()
    assert "build result unchanged" in output.getvalue()


@pytest.mark.parametrize(
    "test_case",
    [
        CostCollectionTestCase(
            description="successful collection persists record and writes warning",
            expected_record_present=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_successful_collection_when_finalizing_then_record_and_default_warning_are_written(
    test_case: CostCollectionTestCase,
    tmp_path: Path,
) -> None:
    output: StringIO = StringIO()

    record: CostRunRecord | None = finalize_build_cost(
        build_cost_finalization(tmp_path=tmp_path, adapter=_CostAdapter(), output_stream=output)
    )

    assert (record is not None) is test_case.expected_record_present
    assert RunCostStore.read(project_dir=tmp_path, run_id="run-1") == record
    assert "Cost  $0.0300 estimated" in output.getvalue()
    assert "default $3.00/credit" in output.getvalue()
    assert "Configure cost.usd_per_credit" in output.getvalue()
    assert "not Snowflake-billed credits" in output.getvalue()


@pytest.mark.parametrize(
    "test_case",
    [
        CostCollectionTestCase(
            description="persistence failure returns in-memory record without escaping",
            expected_record_present=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_persistence_failure_when_finalizing_then_warning_does_not_escape(
    test_case: CostCollectionTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output: StringIO = StringIO()

    def fail_write(**kwargs: Any) -> None:
        del kwargs
        raise OSError("disk full")

    monkeypatch.setattr(
        RunCostStore,
        "write",
        fail_write,
    )

    record: CostRunRecord | None = finalize_build_cost(
        build_cost_finalization(tmp_path=tmp_path, adapter=_CostAdapter(), output_stream=output)
    )

    assert (record is not None) is test_case.expected_record_present
    assert RunCostStore.read(project_dir=tmp_path, run_id="run-1") is None
    assert "OSError" in output.getvalue()
    assert "build result unchanged" in output.getvalue()


@pytest.mark.parametrize(
    "test_case",
    [
        CostCollectionTestCase(
            description="output failure preserves the in-memory and persisted record",
            expected_record_present=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_output_failure_when_finalizing_then_record_is_preserved_without_raising(
    test_case: CostCollectionTestCase,
    tmp_path: Path,
) -> None:
    record: CostRunRecord | None = finalize_build_cost(
        build_cost_finalization(
            tmp_path=tmp_path,
            adapter=_CostAdapter(),
            output_stream=_FailingOutput(),
        )
    )

    assert (record is not None) is test_case.expected_record_present
    assert RunCostStore.read(project_dir=tmp_path, run_id="run-1") == record


@pytest.mark.parametrize(
    "test_case",
    [
        CostCollectionTestCase(
            description="no-work finalization persists complete zero without collection",
            expected_record_present=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_executable_work_when_finalizing_then_zero_record_is_persisted_without_query(
    test_case: CostCollectionTestCase,
    tmp_path: Path,
) -> None:
    output: StringIO = StringIO()
    record: CostRunRecord | None = finalize_build_cost(
        build_cost_finalization(
            tmp_path=tmp_path,
            adapter=_CostAdapter(error=AssertionError("collection must not run")),
            output_stream=output,
            collect=False,
            render=False,
            had_executable_work=False,
        )
    )

    assert (record is not None) is test_case.expected_record_present
    assert record is not None
    assert record.cost.status == CostStatus.COMPLETE
    assert record.cost.estimated_compute_credits == Decimal(0)
    assert record.had_executable_work is False
    assert output.getvalue() == ""
