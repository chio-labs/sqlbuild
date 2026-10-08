"""Native fast column lineage equals Python's on generated projects, model by model."""

from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.lineage._helpers.fast_columns import build_fast_project_column_lineage
from sqlbuild.compiler.lineage.main._build_native_column_lineage import (
    build_native_column_lineage,
)
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.integration.src.sqlbuild.compiler.helpers import mismatches
from tests.integration.src.sqlbuild.compiler.lineage._test_types import (
    DeferredLineageTestCase,
    GeneratedLineageParityTestCase,
    UnparsedLineageTestCase,
)
from tests.integration.src.sqlbuild.compiler.lineage.helpers import (
    compiled_project,
    deferral_records,
    generated_lineage_files,
    lineage_log_records,
    lineage_views,
    record_native_outcomes,
    without_compact_facts,
)

_MODEL_COUNT: int = 16


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedLineageParityTestCase(
            description="stars, nested CTEs, set operations, quoting and opted-out models",
            seed=20261008,
            count=4,
            dialects=(None, "duckdb", "postgres", "snowflake"),
            expected_minimum_native=400,
            expected_minimum_parsed=250,
            expected_minimum_star_expansions=20,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_projects_when_building_fast_lineage_natively_then_matches_python(
    test_case: GeneratedLineageParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    statuses: Counter[str] = record_native_outcomes(monkeypatch=monkeypatch)
    differences: list[tuple[object, object, object]] = []
    for index in range(test_case.count):
        project: CompiledProject = compiled_project(
            project_dir=tmp_path / f"project_{index}",
            files=generated_lineage_files(rng=rng, model_count=_MODEL_COUNT),
        )
        selected: frozenset[str] = frozenset(
            rng.sample([model.name for model in project.models], k=_MODEL_COUNT // 2)
        )
        for variant in (project, without_compact_facts(project)):
            for dialect in test_case.dialects:
                for model_names in (None, selected):
                    names, python_views, native_views = lineage_views(
                        project=variant, dialect=dialect, model_names=model_names
                    )
                    differences.extend(
                        mismatches(inputs=names, expected=python_views, actual=native_views)
                    )

    assert differences == []
    assert statuses["deferred"] == 0
    assert sum(statuses.values()) >= test_case.expected_minimum_native
    assert statuses["built"] + statuses["omitted"] >= test_case.expected_minimum_parsed
    assert statuses["star"] >= test_case.expected_minimum_star_expansions


@pytest.mark.parametrize(
    "test_case",
    [
        UnparsedLineageTestCase(
            description="an unterminated subquery",
            query_sql='SELECT order_id FROM (SELECT * FROM __ref("orders_model_0")',
            expected_status="unparsed",
            expected_messages=("fast column lineage parse failed; falling back",),
        ),
        UnparsedLineageTestCase(
            description="two statements",
            query_sql="SELECT 1; SELECT 2",
            expected_status="unparsed",
            expected_messages=("fast column lineage parse failed; falling back",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unparsable_model_when_building_fast_lineage_then_logs_and_omits_like_python(
    test_case: UnparsedLineageTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    statuses: Counter[str] = record_native_outcomes(monkeypatch=monkeypatch)
    project: CompiledProject = compiled_project(
        project_dir=tmp_path / "project",
        files=generated_lineage_files(rng=random.Random(11), model_count=_MODEL_COUNT),
    )
    broken: CompiledProject = replace(
        project,
        models=(
            replace(project.models[0], query_sql=test_case.query_sql, fast_lineage_columns=None),
            *project.models[1:],
        ),
    )

    with caplog.at_level(logging.DEBUG, logger="sqlbuild.lineage"):
        python: ProjectColumnLineage | None = build_fast_project_column_lineage(project=broken)
        python_records: list[tuple[str, str, object]] = lineage_log_records(caplog)
        caplog.clear()
        native: ProjectColumnLineage | None = build_native_column_lineage(
            project=broken, dialect=None, model_names=None
        )
        native_records: list[tuple[str, str, object]] = lineage_log_records(caplog)

    assert native == python
    assert native is not None
    assert not native.has_model(project.models[0].name)
    assert statuses[test_case.expected_status] == 1
    assert native_records == python_records
    assert tuple(message for _, message, _ in native_records) == test_case.expected_messages


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredLineageTestCase(
            description="a dialect outside the native parser build",
            dialect="mysql",
            expected_kind="unsupported_dialect",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_dialect_when_building_fast_lineage_then_python_builds_and_records(
    test_case: DeferredLineageTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    statuses: Counter[str] = record_native_outcomes(monkeypatch=monkeypatch)
    project: CompiledProject = without_compact_facts(
        compiled_project(
            project_dir=tmp_path / "project",
            files=generated_lineage_files(rng=random.Random(7), model_count=_MODEL_COUNT),
        )
    )

    names, python_views, native_views = lineage_views(
        project=project, dialect=test_case.dialect, model_names=None
    )

    assert mismatches(inputs=names, expected=python_views, actual=native_views) == []
    assert statuses == Counter({"deferred": _MODEL_COUNT})
    assert deferral_records(record_dir) == (
        [{"kind": test_case.expected_kind, "site": "fast_columns.py"}] * _MODEL_COUNT
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
