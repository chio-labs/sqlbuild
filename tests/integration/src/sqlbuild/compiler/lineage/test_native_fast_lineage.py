"""Native fast column lineage equals Python's on generated projects, model by model."""

from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

import sqlbuild._native as native_module
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.lineage.main._build_native_column_lineage import (
    build_native_column_lineage,
)
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.integration.src.sqlbuild.compiler.helpers import mismatches
from tests.integration.src.sqlbuild.compiler.lineage._test_types import (
    FormerlyDeferredLineageTestCase,
    GeneratedLineageParityTestCase,
    ParserPanicLineageTestCase,
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
def test_given_generated_projects_when_building_fast_lineage_then_restored_projects_agree(
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
                    names, with_catalog = lineage_views(
                        project=variant, dialect=dialect, model_names=model_names
                    )
                    _, restored = lineage_views(
                        project=replace(variant, binding_catalog=None),
                        dialect=dialect,
                        model_names=model_names,
                    )
                    differences.extend(
                        mismatches(inputs=names, expected=with_catalog, actual=restored)
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
def test_given_unparsable_model_when_building_fast_lineage_then_logs_and_omits_it(
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
        native: ProjectColumnLineage | None = build_native_column_lineage(
            project=broken, dialect=None, model_names=None
        )
        native_records: list[tuple[str, str, object]] = lineage_log_records(caplog)

    assert native is not None
    assert not native.has_model(project.models[0].name)
    assert statuses[test_case.expected_status] == 1
    assert tuple(message for _, message, _ in native_records) == test_case.expected_messages


@pytest.mark.parametrize(
    "test_case",
    [
        FormerlyDeferredLineageTestCase(
            description="a dialect outside the old native parser build",
            dialect="mysql",
            keeps_catalog=True,
            expected_native_statuses={"built": _MODEL_COUNT},
            expected_error=None,
        ),
        FormerlyDeferredLineageTestCase(
            description="a project restored without its analysis catalog",
            dialect="duckdb",
            keeps_catalog=False,
            expected_native_statuses={"built": _MODEL_COUNT},
            expected_error=None,
        ),
        FormerlyDeferredLineageTestCase(
            description="a dialect name Polyglot does not know raises Python's error",
            dialect="nonsense",
            keeps_catalog=True,
            expected_native_statuses={"unknown_dialect": _MODEL_COUNT},
            expected_error="Unknown dialect: nonsense",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_formerly_deferred_models_when_building_fast_lineage_then_native_answers(
    test_case: FormerlyDeferredLineageTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    statuses: Counter[str] = record_native_outcomes(monkeypatch=monkeypatch)
    compiled: CompiledProject = without_compact_facts(
        compiled_project(
            project_dir=tmp_path / "project",
            files=generated_lineage_files(rng=random.Random(7), model_count=_MODEL_COUNT),
        )
    )
    project: CompiledProject = replace(
        compiled, binding_catalog=(None, compiled.binding_catalog)[test_case.keeps_catalog]
    )

    if test_case.expected_error is None:
        _ = lineage_views(project=project, dialect=test_case.dialect, model_names=None)
    else:
        with pytest.raises(ValueError, match=test_case.expected_error):
            _ = lineage_views(project=project, dialect=test_case.dialect, model_names=None)

    assert statuses == Counter(test_case.expected_native_statuses), test_case.description
    assert deferral_records(record_dir) == []


@pytest.mark.parametrize(
    "test_case",
    [
        ParserPanicLineageTestCase(
            description="truncated T-SQL the parser panics on, which crashes the wheel's process",
            dialect="tsql",
            query_sql="SELECT IF(region > 1, re",
            expected_message=(
                "NativeCompilerError: native SQL compilation panicked "
                "(native fast lineage of request model 0)"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_parser_panic_when_building_fast_lineage_then_raises_native_compiler_error(
    test_case: ParserPanicLineageTestCase, tmp_path: Path
) -> None:
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

    with pytest.raises(native_module.NativeCompilerError) as raised:
        _ = build_native_column_lineage(project=broken, dialect=test_case.dialect, model_names=None)

    assert str(raised.value) == test_case.expected_message


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
