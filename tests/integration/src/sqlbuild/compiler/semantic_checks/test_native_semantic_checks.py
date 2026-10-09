"""Native semantic completion equals Python's on generated failing projects."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.integration.src.sqlbuild.compiler.semantic_checks._test_types import (
    DeferredSemanticTestCase,
    GeneratedSemanticParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.semantic_checks.helpers import (
    SemanticInputs,
    captured_semantic_inputs,
    completed_natively,
    completion_view,
    deferral_records,
    generated_semantic_files,
    native_completion,
    note_kinds,
    python_completion,
    record_native_statuses,
    with_dialect,
)

_NOTE_KINDS: tuple[str, ...] = ("downstream output uses", "downstream uses of", " has: ")


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedSemanticParityTestCase(
            description="typos, aliases, temporal comparisons, type errors and opt-outs",
            seed=20261009,
            count=8,
            model_count=12,
            dialects=("duckdb", "postgres", "snowflake", "bigquery"),
            expected_minimum_native_completions=32,
            expected_minimum_native_diagnostics=200,
            expected_minimum_type_recovery_plans=16,
            expected_minimum_codes={
                "B002": 100,
                "B212": 4,
                "B217": 8,
                "P009": 16,
                "downstream output uses": 16,
                "downstream uses of": 8,
                " has: ": 40,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_failing_projects_when_completing_natively_then_matches_python(
    test_case: GeneratedSemanticParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    statuses: Counter[str] = record_native_statuses(monkeypatch=monkeypatch)
    codes: Counter[str] = Counter()
    expected_views: list[tuple[object, ...]] = []
    native_views: list[tuple[object, ...]] = []
    for index in range(test_case.count):
        captured: SemanticInputs = captured_semantic_inputs(
            project_dir=tmp_path / f"project_{index}",
            files=generated_semantic_files(
                rng=rng, model_count=test_case.model_count, require_analysis=index % 2 == 0
            ),
            monkeypatch=monkeypatch,
        )
        for dialect in test_case.dialects:
            inputs: SemanticInputs = with_dialect(captured, dialect)
            python: CompiledProject = python_completion(inputs=inputs, monkeypatch=monkeypatch)
            codes.update(item.code for item in python.diagnostics)
            codes.update(note_kinds(python, _NOTE_KINDS))
            expected_views.append(completion_view(python))
            native_views.append(completion_view(completed_natively(inputs)))

    assert native_views == expected_views
    assert statuses["completion_deferred"] == 0
    assert statuses["type_recovery_deferred"] == 0
    assert statuses["completion_native"] >= test_case.expected_minimum_native_completions
    assert statuses["diagnostics_native"] >= test_case.expected_minimum_native_diagnostics
    assert statuses["type_recovery_planned"] >= test_case.expected_minimum_type_recovery_plans
    assert {
        code: min(codes[code], minimum)
        for code, minimum in test_case.expected_minimum_codes.items()
    } == test_case.expected_minimum_codes


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredSemanticTestCase(
            description="a dialect outside the native parser build",
            dialect="mysql",
            keeps_catalog=True,
            non_ascii_comment=False,
            expected_kinds=(("unsupported_dialect", "type_recovery.py"),),
        ),
        DeferredSemanticTestCase(
            description="non-ASCII authored SQL in an explained model",
            dialect="duckdb",
            keeps_catalog=True,
            non_ascii_comment=True,
            expected_kinds=(
                ("metadata_checks", "metadata_validation.py"),
                ("non_ascii_text", "recovery.py"),
            ),
        ),
        DeferredSemanticTestCase(
            description="a project without an analysis catalog to run on",
            dialect="duckdb",
            keeps_catalog=False,
            non_ascii_comment=False,
            expected_kinds=(("no_analysis_catalog", "recovery.py"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deferred_projects_when_completing_then_python_completes_and_records(
    test_case: DeferredSemanticTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_dir: Path = tmp_path / "records"
    captured: SemanticInputs = captured_semantic_inputs(
        project_dir=tmp_path / "project",
        files=generated_semantic_files(rng=random.Random(5), model_count=8, require_analysis=False),
        monkeypatch=monkeypatch,
    )
    inputs: SemanticInputs = with_dialect(captured, test_case.dialect)
    project: CompiledProject = replace(
        inputs.project,
        binding_catalog=(None, inputs.project.binding_catalog)[test_case.keeps_catalog],
        models=tuple(
            replace(
                model,
                authored_sql=model.authored_sql
                + ("", "-- caf\u00e9\n")[test_case.non_ascii_comment],
            )
            for model in inputs.project.models
        ),
    )
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))

    native: CompiledProject | None = native_completion(replace(inputs, project=project))

    assert native is None
    assert deferral_records(record_dir) == test_case.expected_kinds


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
