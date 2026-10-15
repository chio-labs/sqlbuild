"""Bound native SQL rule cache publication work while preserving persisted findings."""

import json
from concurrent.futures import Future
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from typing import Any, cast

import pytest

import sqlbuild._native as native
from sqlbuild._native import SqlRulesEvaluation
from sqlbuild.rule_engine.models import Finding
from tests.integration.src.sqlbuild.rule_engine.native_rows._test_types import (
    SqlRulePublicationTestCase,
)
from tests.integration.src.sqlbuild.rule_engine.native_rows.helpers import CountingRulePath


@pytest.mark.parametrize(
    "test_case",
    [
        SqlRulePublicationTestCase(
            "doubling paths and findings", (4, 8, 16), [(4, 12), (8, 24), (16, 48)]
        )
    ],
    ids=lambda case: case.description,
)
def test_given_increasing_findings_when_publishing_cache_then_work_is_linear_and_order_preserved(
    test_case: SqlRulePublicationTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise planning, finding conversion, encoding and disk publication through the binding."""
    monkeypatch.setattr(native, "compiled_relation_keys", lambda project: {})
    counts: list[tuple[int, int]] = []
    started: float = monotonic()
    for size in test_case.sizes:
        project_dir: Path = tmp_path / str(size)
        paths: list[Path] = [Path(f"models/orders_{index}.sql") for index in range(size)]
        models: list[SimpleNamespace] = [
            SimpleNamespace(
                relative_path=path,
                authored_sql="SELECT 1 AS order_id",
                query_sql="SELECT 1 AS order_id",
                config=SimpleNamespace(values={}),
                dynamic_column_contract=None,
            )
            for path in paths
        ]
        project: SimpleNamespace = SimpleNamespace(
            settings=SimpleNamespace(sql_analysis=True), models=models, sql_expansions={}
        )
        plan: SimpleNamespace = SimpleNamespace(
            project_dir=project_dir,
            project=project,
            model_paths=frozenset(paths),
            selected=(SimpleNamespace(code="SQBRSQL004", custom=False),),
            effective_config=SimpleNamespace(
                thresholds={}, allow_exceptions=True, cache=SimpleNamespace(enabled=True)
            ),
        )
        violations: list[SimpleNamespace] = [
            SimpleNamespace(
                file_path=CountingRulePath(project_dir / paths[index % (size - 1)]),
                code="SQBRSQL004",
                line=index + 1,
                column=1,
                message=f"Finding {index}",
                remediation="Use an explicit projection.",
                fix=None,
            )
            for index in range(size)
        ]
        future: Future[Any] = Future()
        future.set_result(SimpleNamespace(result=SimpleNamespace(violations=violations)))
        CountingRulePath.conversions = 0
        result: SqlRulesEvaluation = native.run_planned_sql_rules(
            plan=cast(Any, plan),
            graph=cast(Any, SimpleNamespace(project=project)),
            dialect="duckdb",
            discovered_inputs=cast(Any, None),
            prepared_sql=cast(Any, SimpleNamespace(codes=("SQBRSQL004",), future=future)),
            expansion_reuse=None,
        )
        conversions: int = CountingRulePath.conversions
        assert result.cache_misses == size
        assert len(result.findings) == size
        stored: dict[str, tuple[str, str]] = native.load_sql_rule_cache(
            path=native.rules_bulk_cache_path(project_dir=project_dir, file_name="sql.json")
        )
        assert set(stored) == {path.as_posix() for path in paths}
        expected: list[list[Finding]] = [[] for _ in paths]
        for position, finding in enumerate(result.findings):
            expected[position % (size - 1)].append(finding)
        for path, own in zip(paths, expected, strict=True):
            assert stored[path.as_posix()][1] == native.encode_sql_rule_findings(findings=own)
        assert json.loads(stored[paths[-1].as_posix()][1]) == []
        # One conversion each for grouping, encoding, and duplicate-literal hints.
        counts.append((size, conversions))
    assert counts == test_case.expected_counts
    assert monotonic() - started < 30


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
