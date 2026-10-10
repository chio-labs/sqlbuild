"""Batched analysis preparation must match per-model preparation byte for byte."""

from pathlib import Path

import pytest

from scripts.cold_compile_performance.models import RandomDagProject
from sqlbuild.compiler.compile.main import _build_compile_inputs
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    BatchedPreparationCase,
    PerturbedPreparationCase,
    PreparedCompile,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    dense_writer,
    fixture_writer,
    keep_batched_normalization,
    perturb_batched_normalization,
    prepared_compile,
    random_dag_writer,
    reshape_models,
    use_per_model_normalization,
    use_wave_analysis,
)

pytestmark: pytest.MarkDecorator = pytest.mark.usefixtures("deferred_native_analysis")


@pytest.mark.parametrize(
    "test_case",
    [
        BatchedPreparationCase(
            "inferred shapes",
            random_dag_writer(RandomDagProject(seed=11, model_count=48)),
            (16,),
            0,
        ),
        BatchedPreparationCase(
            "binding errors mid-graph",
            random_dag_writer(RandomDagProject(seed=23, model_count=48, errors=True)),
            (24,),
            1,
        ),
        BatchedPreparationCase(
            "run ids and analysis opt-outs",
            random_dag_writer(
                RandomDagProject(seed=37, model_count=40, run_ids=True, analysis_opt_outs=True)
            ),
            (20,),
            0,
        ),
        BatchedPreparationCase(
            "reference cycle",
            random_dag_writer(RandomDagProject(seed=67, model_count=24, cycle=True)),
            (8,),
            0,
        ),
        BatchedPreparationCase(
            "waffle shop fixture", fixture_writer("tests/e2e/fixtures/waffle_shop"), (), 0
        ),
        BatchedPreparationCase(
            "tidy shop example", fixture_writer("website/examples/tidy-shop"), (), 0
        ),
        BatchedPreparationCase("dense single batch", dense_writer(120), (), 0),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_compiling_in_waves_then_batched_preparation_matches_per_model(
    test_case: BatchedPreparationCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batched_dir: Path = tmp_path / "batched"
    reference_dir: Path = tmp_path / "reference"
    names: tuple[str, ...] = test_case.write_project(batched_dir)
    _ = test_case.write_project(reference_dir)
    monkeypatch.setattr(
        _build_compile_inputs,
        "resolve_run_id",
        lambda *, selected_run_id: selected_run_id or "run-0",
    )
    use_wave_analysis(monkeypatch)
    for step, reshaped, args in (
        ("cold", (), ()),
        ("warm", (), ()),
        ("edit", test_case.reshaped, ()),
        ("uncached", (), ("--no-cache",)),
    ):
        reshape_models(project_dir=batched_dir, names=names, indexes=reshaped)
        reshape_models(project_dir=reference_dir, names=names, indexes=reshaped)
        expected: PreparedCompile = prepared_compile(
            project_dir=reference_dir,
            args=args,
            capsys=capsys,
            monkeypatch=monkeypatch,
            normalization=use_per_model_normalization,
        )
        actual: PreparedCompile = prepared_compile(
            project_dir=batched_dir,
            args=args,
            capsys=capsys,
            monkeypatch=monkeypatch,
            normalization=keep_batched_normalization,
        )

        assert actual[3] == expected[3], f"{step} native batch payloads differ"
        assert actual[1] == expected[1], f"{step} analysis cache keys differ"
        assert actual[2] == expected[2], f"{step} analysis cache hits differ"
        assert actual[0] == expected[0], f"{step} compile differs from per-model preparation"
        assert actual[0][0] == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        BatchedPreparationCase(
            "inferred shapes", random_dag_writer(RandomDagProject(seed=13, model_count=48)), (), 0
        ),
        BatchedPreparationCase(
            "binding errors mid-graph",
            random_dag_writer(RandomDagProject(seed=29, model_count=48, errors=True)),
            (),
            1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_project_when_compiling_dataflow_with_and_without_cache_then_matches_per_model(
    test_case: BatchedPreparationCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batched_dir: Path = tmp_path / "batched"
    reference_dir: Path = tmp_path / "reference"
    _ = test_case.write_project(batched_dir)
    _ = test_case.write_project(reference_dir)
    monkeypatch.setattr(
        _build_compile_inputs,
        "resolve_run_id",
        lambda *, selected_run_id: selected_run_id or "run-0",
    )
    for args in ((), (), ("--no-cache",)):
        expected: PreparedCompile = prepared_compile(
            project_dir=reference_dir,
            args=args,
            capsys=capsys,
            monkeypatch=monkeypatch,
            normalization=use_per_model_normalization,
        )
        actual: PreparedCompile = prepared_compile(
            project_dir=batched_dir,
            args=args,
            capsys=capsys,
            monkeypatch=monkeypatch,
            normalization=keep_batched_normalization,
        )

        assert actual[:3] == expected[:3]
        assert actual[0][0] == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [PerturbedPreparationCase("last member", RandomDagProject(seed=11, model_count=24), False)],
    ids=lambda case: case.description,
)
def test_given_perturbed_batch_result_when_compiling_then_payloads_differ_from_per_model(
    test_case: PerturbedPreparationCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batched_dir: Path = tmp_path / "batched"
    reference_dir: Path = tmp_path / "reference"
    _ = random_dag_writer(test_case.project)(batched_dir)
    _ = random_dag_writer(test_case.project)(reference_dir)
    use_wave_analysis(monkeypatch)

    expected: PreparedCompile = prepared_compile(
        project_dir=reference_dir,
        args=("--no-cache",),
        capsys=capsys,
        monkeypatch=monkeypatch,
        normalization=use_per_model_normalization,
    )
    actual: PreparedCompile = prepared_compile(
        project_dir=batched_dir,
        args=("--no-cache",),
        capsys=capsys,
        monkeypatch=monkeypatch,
        normalization=perturb_batched_normalization,
    )

    assert len(actual[3]) == len(expected[3]) > 0
    assert (actual[3] == expected[3]) is test_case.expected_payloads_match


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
