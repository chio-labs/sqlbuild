"""Native model rendering must compile exactly what the Python renderer compiles."""

import shutil
from pathlib import Path

import pytest

from scripts.cold_compile_performance._helpers.dense_project import write_dense_compile_project
from scripts.cold_compile_performance._helpers.random_dag_project import write_random_dag_project
from scripts.cold_compile_performance._helpers.random_render_project import (
    write_random_render_project,
)
from scripts.cold_compile_performance.models import RandomDagProject, RandomRenderProject
from tests.integration.src.sqlbuild.compiler.compile._test_types import (
    NativeRenderDagCase,
    NativeRenderDenseCase,
    NativeRenderFixtureCase,
    NativeRenderMutationCase,
    NativeRenderProjectCase,
)
from tests.integration.src.sqlbuild.compiler.compile.helpers import (
    NativeRenderComparison,
    compare_native_rendering,
    drop_last_declaration_start,
    ignore_dialect_comments,
    rename_native_references,
    render_differences,
    rendered_model_counts,
    replay_stale_macro_results,
)

_REPOSITORY_ROOT: Path = Path(__file__).resolve().parents[6]


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRenderFixtureCase("waffle shop fixture", "tests/e2e/fixtures/waffle_shop", 0, 8),
        NativeRenderFixtureCase(
            "source loader fixture", "tests/e2e/fixtures/source_loader_strategies", 0, 0
        ),
        NativeRenderFixtureCase("waffle shop example", "website/examples/waffle-shop", 0, 6),
        NativeRenderFixtureCase("tidy shop example", "website/examples/tidy-shop", 0, 1),
        NativeRenderFixtureCase("hero shop example", "website/examples/hero-shop", 0, 1),
    ],
    ids=lambda case: case.description,
)
def test_given_repository_fixture_when_rendering_natively_then_matches_python_rendering(
    test_case: NativeRenderFixtureCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "project"
    _ = shutil.copytree(
        _REPOSITORY_ROOT / test_case.fixture,
        project_dir,
        ignore=shutil.ignore_patterns("target", "*.duckdb"),
    )

    comparison: NativeRenderComparison = compare_native_rendering(
        project_dir=project_dir, capsys=capsys, monkeypatch=monkeypatch
    )

    assert render_differences(comparison) == test_case.expected_differences
    assert comparison[1][0] == test_case.expected_exit_code
    assert rendered_model_counts(comparison)[0] >= test_case.expected_minimum_native_models


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRenderProjectCase(
            "duckdb constructs", RandomRenderProject(seed=3, model_count=40), 0, 3
        ),
        NativeRenderProjectCase(
            "snowflake dialect constructs",
            RandomRenderProject(seed=5, model_count=40, adapter="snowflake"),
            0,
            5,
        ),
        NativeRenderProjectCase(
            "macro generated references",
            RandomRenderProject(seed=7, model_count=40, generated_references=True),
            1,
            3,
        ),
        NativeRenderProjectCase(
            "one rendering error", RandomRenderProject(seed=11, model_count=40, errors=1), 1, 0
        ),
        NativeRenderProjectCase(
            "first of several rendering errors",
            RandomRenderProject(seed=13, model_count=40, errors=4),
            1,
            0,
        ),
        NativeRenderProjectCase(
            "snowflake rendering errors",
            RandomRenderProject(seed=17, model_count=40, adapter="snowflake", errors=3),
            1,
            0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_render_project_when_rendering_natively_then_matches_python_rendering(
    test_case: NativeRenderProjectCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "orders"
    write_random_render_project(project_dir=project_dir, project=test_case.project)

    comparison: NativeRenderComparison = compare_native_rendering(
        project_dir=project_dir, capsys=capsys, monkeypatch=monkeypatch
    )

    assert render_differences(comparison) == test_case.expected_differences
    assert comparison[1][0] == test_case.expected_exit_code
    assert rendered_model_counts(comparison)[0] >= test_case.expected_minimum_native_models


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRenderDagCase("inferred shapes", RandomDagProject(seed=11, model_count=48)),
        NativeRenderDagCase(
            "binding errors", RandomDagProject(seed=23, model_count=48, errors=True)
        ),
        NativeRenderDagCase(
            "run ids and analysis opt-outs",
            RandomDagProject(seed=37, model_count=40, run_ids=True, analysis_opt_outs=True),
        ),
        NativeRenderDagCase(
            "missing reference",
            RandomDagProject(seed=61, model_count=24, missing_reference=True),
        ),
        NativeRenderDagCase(
            "reference cycle", RandomDagProject(seed=67, model_count=24, cycle=True)
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_random_dag_project_when_rendering_natively_then_matches_python_rendering(
    test_case: NativeRenderDagCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "orders"
    _ = write_random_dag_project(project_dir=project_dir, project=test_case.project)

    comparison: NativeRenderComparison = compare_native_rendering(
        project_dir=project_dir, capsys=capsys, monkeypatch=monkeypatch
    )

    assert render_differences(comparison) == test_case.expected_differences


@pytest.mark.parametrize(
    "test_case",
    [NativeRenderDenseCase("dense joins unions macros and functions", 120, 84, 36)],
    ids=lambda case: case.description,
)
def test_given_dense_project_when_rendering_natively_then_matches_python_rendering(
    test_case: NativeRenderDenseCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "dense_orders"
    write_dense_compile_project(project_dir=project_dir, model_count=test_case.model_count)

    comparison: NativeRenderComparison = compare_native_rendering(
        project_dir=project_dir, capsys=capsys, monkeypatch=monkeypatch
    )

    assert render_differences(comparison) == test_case.expected_differences
    assert rendered_model_counts(comparison) == (
        test_case.expected_native_models,
        test_case.expected_fallback_models,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRenderMutationCase(
            "declaration scan misses a reference",
            RandomRenderProject(seed=3, model_count=40),
            drop_last_declaration_start,
        ),
        NativeRenderMutationCase(
            "batch references name the wrong producer",
            RandomRenderProject(seed=3, model_count=40),
            rename_native_references,
        ),
        NativeRenderMutationCase(
            "reference scan ignores dialect comments",
            RandomRenderProject(seed=5, model_count=40, adapter="snowflake"),
            ignore_dialect_comments,
        ),
        NativeRenderMutationCase(
            "macro memo replays a stale result",
            RandomRenderProject(seed=3, model_count=40),
            replay_stale_macro_results,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_broken_native_construct_when_comparing_then_oracle_reports_difference(
    test_case: NativeRenderMutationCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "orders"
    write_random_render_project(project_dir=project_dir, project=test_case.project)
    test_case.break_native(monkeypatch)

    comparison: NativeRenderComparison = compare_native_rendering(
        project_dir=project_dir, capsys=capsys, monkeypatch=monkeypatch
    )

    assert test_case.expected_difference in render_differences(comparison)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
