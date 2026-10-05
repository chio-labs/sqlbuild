"""Dependency-driven model analysis must compile exactly what wave-by-wave analysis compiles."""

import shutil
from pathlib import Path

import pytest

from scripts.cold_compile_performance._helpers.dense_project import write_dense_compile_project
from scripts.cold_compile_performance._helpers.random_dag_project import write_random_dag_project
from scripts.cold_compile_performance.models import RandomDagProject
from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.compile.main import _build_compile_inputs
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    CompileOutcome,
    DataflowBuildCase,
    DataflowDenseCase,
    DataflowFixtureCase,
    DataflowOracleCase,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    compile_outcome,
    reshape_models,
    use_wave_analysis,
)

_REPOSITORY_ROOT: Path = Path(__file__).resolve().parents[6]


@pytest.mark.parametrize(
    "test_case",
    [
        DataflowOracleCase(
            description="inferred shapes",
            project=RandomDagProject(seed=11, model_count=48),
            reshaped_steps=((), (), (16,), (24, 40), ()),
            expected_exit_codes=(0, 0, 0, 0, 0),
        ),
        DataflowOracleCase(
            description="binding errors mid-graph",
            project=RandomDagProject(seed=23, model_count=48, errors=True),
            reshaped_steps=((), (), (16,), (24, 40), ()),
            expected_exit_codes=(1, 1, 1, 1, 1),
        ),
        DataflowOracleCase(
            description="run ids and analysis opt-outs",
            project=RandomDagProject(seed=37, model_count=40, run_ids=True, analysis_opt_outs=True),
            reshaped_steps=((), (), (13,), (20,), ()),
            expected_exit_codes=(0, 0, 0, 0, 0),
        ),
        DataflowOracleCase(
            description="built-in rules",
            project=RandomDagProject(seed=41, model_count=32, rules=("SQBR",)),
            reshaped_steps=((), (10,), ()),
            expected_exit_codes=(1, 1, 1),
        ),
        DataflowOracleCase(
            description="analysis cache disabled",
            project=RandomDagProject(seed=53, model_count=48, errors=True),
            reshaped_steps=((), (16,)),
            expected_exit_codes=(1, 1),
            compile_args=("--no-cache",),
        ),
        DataflowOracleCase(
            description="missing reference",
            project=RandomDagProject(seed=61, model_count=24, missing_reference=True),
            reshaped_steps=((), (8,)),
            expected_exit_codes=(1, 1),
        ),
        DataflowOracleCase(
            description="reference cycle",
            project=RandomDagProject(seed=67, model_count=24, cycle=True),
            reshaped_steps=((), (8,)),
            expected_exit_codes=(0, 0),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_random_dag_edit_sequence_when_compiling_then_dataflow_matches_waves(
    test_case: DataflowOracleCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waves_dir: Path = tmp_path / "waves"
    dataflow_dir: Path = tmp_path / "dataflow"
    names: tuple[str, ...] = write_random_dag_project(
        project_dir=waves_dir, project=test_case.project
    )
    _ = write_random_dag_project(project_dir=dataflow_dir, project=test_case.project)
    exit_codes: list[int] = []
    for step, indexes in enumerate(test_case.reshaped_steps):
        monkeypatch.setattr(
            _build_compile_inputs,
            "resolve_run_id",
            lambda *, selected_run_id, run_id=f"run-{step}": selected_run_id or run_id,
        )
        reshape_models(project_dir=waves_dir, names=names, indexes=indexes)
        reshape_models(project_dir=dataflow_dir, names=names, indexes=indexes)
        with monkeypatch.context() as waves_patch:
            use_wave_analysis(waves_patch)
            expected: CompileOutcome = compile_outcome(
                project_dir=waves_dir, args=test_case.compile_args, capsys=capsys
            )
        actual: CompileOutcome = compile_outcome(
            project_dir=dataflow_dir, args=test_case.compile_args, capsys=capsys
        )
        uncached: CompileOutcome = compile_outcome(
            project_dir=dataflow_dir, args=("--no-cache",), capsys=capsys
        )
        exit_codes.append(actual[0])

        assert actual == expected, f"step {step} differs from wave analysis"
        assert actual == uncached, f"step {step} differs from an uncached compile"

    assert tuple(exit_codes) == test_case.expected_exit_codes


@pytest.mark.parametrize(
    "test_case",
    [
        DataflowFixtureCase("waffle shop fixture", "tests/e2e/fixtures/waffle_shop", 0),
        DataflowFixtureCase("waffle shop example", "website/examples/waffle-shop", 0),
        DataflowFixtureCase("tidy shop example", "website/examples/tidy-shop", 0),
        DataflowFixtureCase("hero shop example", "website/examples/hero-shop", 0),
    ],
    ids=lambda case: case.description,
)
def test_given_repository_fixture_when_compiling_cold_then_dataflow_matches_waves(
    test_case: DataflowFixtureCase,
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
    monkeypatch.setattr(
        _build_compile_inputs,
        "resolve_run_id",
        lambda *, selected_run_id: selected_run_id or "run-0",
    )
    with monkeypatch.context() as waves_patch:
        use_wave_analysis(waves_patch)
        expected: CompileOutcome = compile_outcome(project_dir=project_dir, args=(), capsys=capsys)
    shutil.rmtree(project_dir / "target")
    actual: CompileOutcome = compile_outcome(project_dir=project_dir, args=(), capsys=capsys)

    assert actual == expected
    assert actual[0] == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [DataflowDenseCase("dense joins unions macros and functions", 64, (0, 0))],
    ids=lambda case: case.description,
)
def test_given_dense_fixture_when_compiling_cold_and_warm_then_dataflow_matches_waves(
    test_case: DataflowDenseCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waves_dir: Path = tmp_path / "waves"
    dataflow_dir: Path = tmp_path / "dataflow"
    write_dense_compile_project(project_dir=waves_dir, model_count=test_case.model_count)
    write_dense_compile_project(project_dir=dataflow_dir, model_count=test_case.model_count)
    with monkeypatch.context() as waves_patch:
        use_wave_analysis(waves_patch)
        expected: tuple[CompileOutcome, CompileOutcome] = (
            compile_outcome(project_dir=waves_dir, args=(), capsys=capsys),
            compile_outcome(project_dir=waves_dir, args=(), capsys=capsys),
        )
    actual: tuple[CompileOutcome, CompileOutcome] = (
        compile_outcome(project_dir=dataflow_dir, args=(), capsys=capsys),
        compile_outcome(project_dir=dataflow_dir, args=(), capsys=capsys),
    )

    assert actual == expected
    assert (actual[0][0], actual[1][0]) == test_case.expected_exit_codes


@pytest.mark.parametrize(
    "test_case",
    [DataflowBuildCase("inferred shapes", RandomDagProject(seed=79, model_count=24), 0, 0)],
    ids=lambda case: case.description,
)
def test_given_random_dag_when_building_on_duckdb_then_every_model_materializes(
    test_case: DataflowBuildCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project_dir: Path = tmp_path / "orders"
    names: tuple[str, ...] = write_random_dag_project(
        project_dir=project_dir, project=test_case.project
    )
    config: Path = project_dir / "sqlbuild_project.toml"
    _ = config.write_text(
        config.read_text(encoding="utf-8")
        + f'[connection]\ndatabase = "{project_dir / "orders.duckdb"}"\n',
        encoding="utf-8",
    )

    compiled: int = main(["--project-dir", str(project_dir), "compile", "--json"])
    compile_output: str = capsys.readouterr().out
    built: int = main(["--project-dir", str(project_dir), "build", "--no-tests", "--no-audits"])
    build_output: str = "".join(capsys.readouterr())

    assert compiled == test_case.expected_compile_exit_code, compile_output
    assert built == test_case.expected_build_exit_code, build_output
    assert all(name in build_output for name in names)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
