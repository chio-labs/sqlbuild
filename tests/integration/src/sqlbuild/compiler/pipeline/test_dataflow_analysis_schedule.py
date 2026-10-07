"""Dataflow analysis output must not depend on worker count, batching, or completion order."""

import threading
import time
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from scripts.cold_compile_performance._helpers.random_dag_project import write_random_dag_project
from scripts.cold_compile_performance.models import RandomDagProject
from scripts.compiler_differential._helpers.comparing.compare import first_document_difference
from scripts.compiler_differential.main.generate_project import generate_project
from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    CompileOutcome,
    DataflowCaptureCase,
    DataflowFailureCase,
    DataflowInterruptAfterFaultCase,
    DataflowInterruptCase,
    DataflowPoolCase,
    DataflowScheduleCase,
    DataflowStartFailureCase,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    analysis_pool_thread_ids,
    compile_outcome,
    compiled_project_capture,
    fail_model_analysis,
    fail_worker_start,
    interrupt_after_analysis_fault,
    interrupt_reacquiring_analysis,
    live_model_analysis_threads,
    perturb_dataflow_schedule,
    reshape_models,
    use_wave_analysis,
)

_PROJECT: RandomDagProject = RandomDagProject(seed=97, model_count=40, errors=True)
_SHARED_ANALYSIS_SEED: int = 29
_CAPTURE_SCHEDULES: tuple[DataflowScheduleCase, ...] = (
    DataflowScheduleCase("one worker with single models", 1, 1, 0.0),
    DataflowScheduleCase("four workers with small batches", 4, 2, 0.004),
    DataflowScheduleCase("four workers with wide batches", 4, 64, 0.002),
)
_EDITED: tuple[int, ...] = (10, 25)
_REPEATS: tuple[int, ...] = (0, 1)
_SETTLE_SECONDS: float = 0.3
_INTERRUPT_NOTICE: str = "Interrupted; finishing in-flight model analysis..."


def _write_random_dag(project_dir: Path) -> None:
    _ = write_random_dag_project(project_dir=project_dir, project=_PROJECT)


@pytest.mark.parametrize(
    "test_case",
    [
        DataflowScheduleCase("one worker with whole ready sets", 1, 64, 0.0),
        DataflowScheduleCase("two workers with single models", 2, 1, 0.004),
        DataflowScheduleCase("four workers with small batches", 4, 3, 0.004),
        DataflowScheduleCase("four workers with wide batches", 4, 64, 0.002),
    ],
    ids=lambda case: case.description,
)
def test_given_perturbed_schedule_when_compiling_repeatedly_then_output_is_identical(
    test_case: DataflowScheduleCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_dir: Path = tmp_path / "reference"
    names: tuple[str, ...] = write_random_dag_project(project_dir=reference_dir, project=_PROJECT)
    with monkeypatch.context() as waves_patch:
        use_wave_analysis(waves_patch)
        cold: CompileOutcome = compile_outcome(project_dir=reference_dir, args=(), capsys=capsys)
        reshape_models(project_dir=reference_dir, names=names, indexes=_EDITED)
        edit: CompileOutcome = compile_outcome(project_dir=reference_dir, args=(), capsys=capsys)
    for repeat in _REPEATS:
        project_dir: Path = tmp_path / f"dataflow-{repeat}"
        _ = write_random_dag_project(project_dir=project_dir, project=_PROJECT)
        with monkeypatch.context() as schedule_patch:
            perturb_dataflow_schedule(monkeypatch=schedule_patch, case=test_case, seed=repeat)
            actual_cold: CompileOutcome = compile_outcome(
                project_dir=project_dir, args=(), capsys=capsys
            )
            reshape_models(project_dir=project_dir, names=names, indexes=_EDITED)
            actual_edit: CompileOutcome = compile_outcome(
                project_dir=project_dir, args=(), capsys=capsys
            )

        assert actual_cold == cold, f"cold compile differs in repeat {repeat}"
        assert actual_edit == edit, f"edited compile differs in repeat {repeat}"
        assert actual_cold[0] == test_case.expected_cold_exit_code
        assert actual_edit[0] == test_case.expected_edit_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        DataflowCaptureCase(
            "random dag",
            _write_random_dag,
            _CAPTURE_SCHEDULES,
        ),
        DataflowCaptureCase(
            "differential seed with shared analyses",
            generate_project(seed=_SHARED_ANALYSIS_SEED).write,
            _CAPTURE_SCHEDULES,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_perturbed_schedule_when_capturing_compiled_project_then_capture_is_identical(
    test_case: DataflowCaptureCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "project"
    _ = test_case.write_project(project_dir)
    with monkeypatch.context() as waves_patch:
        use_wave_analysis(waves_patch)
        reference: str = compiled_project_capture(
            project_dir=project_dir,
            capture_dir=tmp_path / "reference",
            capsys=capsys,
            monkeypatch=monkeypatch,
        )
    for index, schedule in enumerate(test_case.schedules):
        with monkeypatch.context() as schedule_patch:
            perturb_dataflow_schedule(monkeypatch=schedule_patch, case=schedule, seed=index)
            actual: str = compiled_project_capture(
                project_dir=project_dir,
                capture_dir=tmp_path / f"schedule-{index}",
                capsys=capsys,
                monkeypatch=monkeypatch,
            )

        assert first_document_difference(left=reference, right=actual) is None, schedule


@pytest.mark.parametrize(
    "test_case",
    [
        DataflowFailureCase("one failing model", ("orders_020",), "analysis fault in orders_020"),
        DataflowFailureCase(
            "an upstream failure wins", ("orders_035", "orders_004"), "analysis fault in orders_004"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_analysis_fault_when_completion_order_varies_then_first_wave_error_is_raised(
    test_case: DataflowFailureCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "orders"
    _ = write_random_dag_project(project_dir=project_dir, project=_PROJECT)
    args: list[str] = ["--project-dir", str(project_dir), "compile", "--json", "--no-cache"]
    fail_model_analysis(monkeypatch=monkeypatch, model_names=test_case.failing_models)
    with monkeypatch.context() as waves_patch:
        use_wave_analysis(waves_patch)
        with pytest.raises(RuntimeError) as expected:
            _ = main(args)
    _ = capsys.readouterr()
    perturb_dataflow_schedule(
        monkeypatch=monkeypatch,
        case=DataflowScheduleCase("four workers with delays", 4, 3, 0.004),
        seed=len(test_case.failing_models),
    )
    with pytest.raises(RuntimeError) as actual:
        _ = main(args)

    assert str(actual.value) == str(expected.value)
    assert str(actual.value) == test_case.expected_message


@pytest.mark.parametrize(
    "test_case",
    [DataflowPoolCase("two multi-batch compiles", 2, 3, 4)],
    ids=lambda case: case.description,
)
def test_given_multi_batch_compiles_when_analyzing_then_each_compile_reuses_one_native_pool(
    test_case: DataflowPoolCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "orders"
    _ = write_random_dag_project(project_dir=project_dir, project=_PROJECT)
    for _ in range(test_case.compiles):
        observed: list[set[str]] = analysis_pool_thread_ids(monkeypatch)
        _ = compile_outcome(project_dir=project_dir, args=("--no-cache",), capsys=capsys)

        started: set[str] = set().union(*observed[1:]) - observed[0]

        assert len(observed) > test_case.minimum_batches
        assert len(started) == test_case.expected_pool_threads


@pytest.mark.parametrize(
    "test_case",
    [DataflowInterruptCase("interrupt while workers reacquire the lock", (), (), 0, 1)],
    ids=lambda case: case.description,
)
def test_given_sigint_while_workers_contend_for_lock_when_analyzing_then_interrupt_propagates_once(
    test_case: DataflowInterruptCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "orders"
    _ = write_random_dag_project(project_dir=project_dir, project=_PROJECT)
    thread_errors: list[threading.ExceptHookArgs] = []
    monkeypatch.setattr(threading, "excepthook", thread_errors.append)
    overlaps: list[str] = interrupt_reacquiring_analysis(monkeypatch=monkeypatch)

    with pytest.raises(KeyboardInterrupt):
        _ = main(["--project-dir", str(project_dir), "compile", "--json", "--no-cache"])
    captured: CaptureResult[str] = capsys.readouterr()

    assert tuple(live_model_analysis_threads()) == test_case.expected_live_workers
    assert tuple(overlaps) == test_case.expected_overlaps
    assert len(thread_errors) == test_case.expected_thread_errors
    assert captured.err.count(_INTERRUPT_NOTICE) == test_case.expected_notices
    assert _INTERRUPT_NOTICE not in captured.out


@pytest.mark.parametrize(
    "test_case",
    [DataflowInterruptAfterFaultCase("interrupt after a fault", "orders_000", "orders_001", 0)],
    ids=lambda case: case.description,
)
def test_given_interrupt_after_analysis_fault_when_analyzing_then_interrupt_wins_without_replay(
    test_case: DataflowInterruptAfterFaultCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "orders"
    _ = write_random_dag_project(project_dir=project_dir, project=_PROJECT)
    replays: list[int] = interrupt_after_analysis_fault(
        monkeypatch=monkeypatch,
        failing_model=test_case.failing_model,
        interrupted_model=test_case.interrupted_model,
    )

    with pytest.raises(KeyboardInterrupt, match=test_case.interrupted_model):
        _ = main(["--project-dir", str(project_dir), "compile", "--json", "--no-cache"])
    _ = capsys.readouterr()

    assert len(replays) == test_case.expected_wave_replays


@pytest.mark.parametrize(
    "test_case",
    [
        DataflowStartFailureCase(
            description="third worker cannot start",
            failing_start=2,
            interrupt_after_start=False,
            expected_error_type=RuntimeError,
            expected_error="cannot start",
            expected_live_workers=(),
            expected_notices=0,
        ),
        DataflowStartFailureCase(
            description="interrupt after the first worker starts",
            failing_start=0,
            interrupt_after_start=True,
            expected_error_type=KeyboardInterrupt,
            expected_error="sqlbuild-model-analysis-0",
            expected_live_workers=(),
            expected_notices=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_worker_start_failure_when_analyzing_then_started_workers_stop_before_raising(
    test_case: DataflowStartFailureCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "orders"
    _ = write_random_dag_project(project_dir=project_dir, project=_PROJECT)
    batches: list[str] = fail_worker_start(
        monkeypatch=monkeypatch,
        failing_start=test_case.failing_start,
        interrupt_after_start=test_case.interrupt_after_start,
    )

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error):
        _ = main(["--project-dir", str(project_dir), "compile", "--json", "--no-cache"])
    live_at_failure: list[str] = live_model_analysis_threads()
    batches_at_failure: int = len(batches)
    captured: CaptureResult[str] = capsys.readouterr()
    time.sleep(_SETTLE_SECONDS)

    assert tuple(live_at_failure) == test_case.expected_live_workers
    assert len(batches) == batches_at_failure
    assert captured.err.count(_INTERRUPT_NOTICE) == test_case.expected_notices
    assert _INTERRUPT_NOTICE not in captured.out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
