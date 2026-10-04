from __future__ import annotations

import orjson
import pytest

from sqlbuild.compiler.compile._helpers.analysis import compact
from sqlbuild.compiler.compile.models import CompactBatchPreparation
from tests.unit.src.sqlbuild.compiler.compile._helpers.analysis._test_types import (
    CompactAnalysisWorkersTestCase,
)

_MIB: int = 1024 * 1024


@pytest.mark.parametrize(
    "test_case",
    (
        CompactAnalysisWorkersTestCase(
            description="small project",
            model_count=3,
            sql_bytes_per_model=64,
            expected_workers=4,
        ),
        CompactAnalysisWorkersTestCase(
            description="dense ten thousand model project",
            model_count=10_000,
            sql_bytes_per_model=(64 * _MIB) // 10_000,
            expected_workers=4,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_project_size_when_running_compact_analysis_then_native_uses_all_workers(
    test_case: CompactAnalysisWorkersTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []

    def analyze(request_json: str) -> str:
        captured.append(orjson.loads(request_json))
        return "{}"

    monkeypatch.setattr(compact._native, "analyze_project_queries_compact_json", analyze)
    sql: str = "SELECT 1 AS order_id" + " " * (test_case.sql_bytes_per_model - 20)
    preparation: CompactBatchPreparation = CompactBatchPreparation(
        cleaned_sql=(sql,) * test_case.model_count,
        queries=({"sql": "SELECT 1 AS order_id", "dialect": "duckdb"},),
        templates=({"queryIndex": 0},),
        projections=({"templateIndex": 0},) * test_case.model_count,
    )

    _ = compact._run_compact_analysis_batch(preparation=preparation)

    assert [request["workers"] for request in captured] == [test_case.expected_workers]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
