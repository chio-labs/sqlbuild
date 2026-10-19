"""Delta compiles must print exactly what a full compile of the same edit prints."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from scripts.delta_compile_series.constants import DELTA_COMPILE_LINE, PROJECT_CONFIG
from scripts.delta_compile_series.main.run_delta_compile_sequence import (
    run_delta_compile_sequence,
)
from scripts.delta_compile_series.main.run_delta_compile_series import run_delta_compile_series
from scripts.delta_compile_series.main.write_delta_compile_project import (
    write_delta_compile_project,
)
from scripts.delta_compile_series.models import (
    DeltaCompileOutcome,
    DeltaCompileSequence,
    DeltaCompileSeries,
)
from scripts.delta_compile_series.types import SequenceEdit
from sqlbuild._native import DELTA_COMPILE_DISABLE_ENV_VAR, DELTA_COMPILE_VERIFY_ENV_VAR
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    DeltaCompileOptOutTestCase,
    DeltaCompileSequenceTestCase,
    DeltaCompileSeriesTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    replace_project_text,
    run_delta_compile,
    without_compile_timings,
)

_MODEL_COUNT: int = 300
_JSON_COMPILE: tuple[str, ...] = ("compile", "--json")
_TEXT_COMPILE: tuple[str, ...] = ("compile",)
_REUSE_ROOT: str = "target/cache/compiler-native-v1/project-reuse-v3"
_EDITED_MODEL: str = (
    "models/sales000/intermediate/clean/batch00000/sales000__int_clean__orders_00003.sql"
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeltaCompileSeriesTestCase(description="json_report", seed=11, json_output=True, steps=12),
        DeltaCompileSeriesTestCase(description="text_report", seed=12, json_output=False, steps=12),
        DeltaCompileSeriesTestCase(
            description="long_json_series", seed=13, json_output=True, steps=20
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_edit_series_when_compiling_each_edit_then_deltas_match_full_compiles(
    test_case: DeltaCompileSeriesTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "dense_orders"
    write_delta_compile_project(project_dir=project_dir, model_count=_MODEL_COUNT)
    args: tuple[str, ...] = (_TEXT_COMPILE, _JSON_COMPILE)[int(test_case.json_output)]

    series: DeltaCompileSeries = run_delta_compile_series(
        project_dir=project_dir,
        seed=test_case.seed,
        steps=test_case.steps,
        compile_project=partial(
            run_delta_compile,
            project_dir=project_dir,
            args=args,
            env={DELTA_COMPILE_VERIFY_ENV_VAR: "1"},
        ),
    )

    assert series.unexpected == test_case.expected_unexpected_outcomes, series.steps
    assert series.deltas >= test_case.expected_minimum_deltas, series.steps


@pytest.mark.parametrize(
    "test_case",
    [
        DeltaCompileSequenceTestCase(
            description="an unchanged project replays the delta",
            edits=(SequenceEdit.BODY, SequenceEdit.NONE),
            expected_delta_lines=(True, False),
            expected_replayed_last=True,
            expected_same_as_full=True,
        ),
        DeltaCompileSequenceTestCase(
            description="an edit after a multi-round delta is a delta too",
            edits=(SequenceEdit.SHAPE, SequenceEdit.BODY),
            expected_delta_lines=(True, True),
            expected_replayed_last=False,
            expected_same_as_full=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edit_sequence_when_compiling_each_edit_then_deltas_store_and_replay_like_full_compiles(
    test_case: DeltaCompileSequenceTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "dense_orders"
    write_delta_compile_project(project_dir=project_dir, model_count=_MODEL_COUNT)

    sequence: DeltaCompileSequence = run_delta_compile_sequence(
        project_dir=project_dir,
        edits=test_case.edits,
        compile_project=partial(
            run_delta_compile, project_dir=project_dir, args=_JSON_COMPILE, env={}
        ),
        compile_in_full=partial(
            run_delta_compile,
            project_dir=project_dir,
            args=_JSON_COMPILE,
            env={DELTA_COMPILE_DISABLE_ENV_VAR: "1"},
        ),
    )

    assert sequence.delta_lines == test_case.expected_delta_lines
    assert sequence.replayed_last == test_case.expected_replayed_last
    assert (
        without_compile_timings(report=sequence.last_report)
        == without_compile_timings(report=sequence.full_report)
    ) == test_case.expected_same_as_full


@pytest.mark.parametrize(
    "test_case",
    [
        DeltaCompileOptOutTestCase(
            description="project_setting", settings="\n[settings]\ndelta_compile = false\n", env={}
        ),
        DeltaCompileOptOutTestCase(
            description="environment", settings="", env={DELTA_COMPILE_DISABLE_ENV_VAR: "1"}
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_delta_compiles_turned_off_when_compiling_an_edit_then_it_compiles_in_full(
    test_case: DeltaCompileOptOutTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "dense_orders"
    write_delta_compile_project(project_dir=project_dir, model_count=_MODEL_COUNT)
    config: Path = project_dir / PROJECT_CONFIG
    config.write_text(config.read_text(encoding="utf-8") + test_case.settings, encoding="utf-8")
    first: DeltaCompileOutcome = run_delta_compile(
        project_dir=project_dir, args=_TEXT_COMPILE, env=test_case.env
    )
    replace_project_text(
        project_dir, _EDITED_MODEL, "COALESCE(b.amount, ", "COALESCE(b.amount, 1 + "
    )

    edited: DeltaCompileOutcome = run_delta_compile(
        project_dir=project_dir, args=_TEXT_COMPILE, env=test_case.env
    )

    assert (first.returncode, edited.returncode) == (0, 0), edited.stderr[-2000:]
    assert (DELTA_COMPILE_LINE in edited.stderr) == test_case.expected_delta_line
    assert (
        tuple(sorted(path.name for path in (project_dir / _REUSE_ROOT).glob("*.image")))
        == test_case.expected_images
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
