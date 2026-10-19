"""Delta compiles must print exactly what a full compile of the same edit prints."""

from __future__ import annotations

import random
import re
from pathlib import Path

import pytest

from scripts.cold_compile_performance._helpers.dense_project import write_dense_compile_project
from sqlbuild._native import DELTA_COMPILE_DISABLE_ENV_VAR, DELTA_COMPILE_VERIFY_ENV_VAR
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    DeltaCompileEdit,
    DeltaCompileOptOutTestCase,
    DeltaCompileSeriesTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    COMPILE_REUSE_HIT_LINE,
    DELTA_COMPILE_LINE,
    DeltaCompileRun,
    replace_project_text,
    run_delta_compile,
)

_MODEL_COUNT: int = 300
_VERIFY_ENV: dict[str, str] = {DELTA_COMPILE_VERIFY_ENV_VAR: "1"}
_MISMATCH_EXIT_CODE: int = 70
_REVERT_PROBABILITY: float = 0.5
_MINIMUM_DELTAS: int = 3
# Edits that compile as deltas are drawn more often than those that must compile in full.
_DELTA_WEIGHT: int = 3
_FALLBACK_WEIGHT: int = 1
_EDIT_ATTEMPTS: int = 50
_PROJECT_CONFIG: str = "sqlbuild_project.toml"
# Problems a full compile reported in files a delta does not compile again keep it full.
_STALE_PROBLEMS: str = "reports problems in files the edit leaves alone"
_REUSE_ROOT: str = "target/cache/compiler-native-v1/project-reuse-v3"

_EDITS: tuple[DeltaCompileEdit, ...] = (
    DeltaCompileEdit("body_constant", r"COALESCE\(b\.amount, \d+\)", "COALESCE(b.amount, {value})"),
    DeltaCompileEdit("body_comment", r"\Z", "\n-- reviewed {value}\n"),
    DeltaCompileEdit(
        "description", r'MODEL \(description "[^"]*"', 'MODEL (description "Edited {value}."'
    ),
    DeltaCompileEdit(
        "column_description",
        r'description "Order quantity measure"',
        'description "Edited measure {value}"',
    ),
    DeltaCompileEdit("type_error", r"quantity_000 \(type DOUBLE", "quantity_000 (type VARCHAR"),
    DeltaCompileEdit("parse_error", r"projected AS \(SELECT", "projected AS (SELEC"),
    DeltaCompileEdit(
        "test_expectation",
        r"(__expected__\w+ AS \(SELECT CAST\()\d+",
        r"\g<1>{value}",
        on_test_file=True,
    ),
    DeltaCompileEdit(
        "materialization",
        r"materialized table",
        "materialized view",
        fallback_reason="custom rules select models by their materialization",
    ),
    DeltaCompileEdit(
        "contract",
        r"contract enforced, ",
        "",
        fallback_reason="a custom rule reads",
    ),
    DeltaCompileEdit(
        "unknown_reference",
        r'__ref\("([^"]+)"\)',
        r'__ref("\1_missing")',
        fallback_reason="changed what it references",
    ),
)
_CONFIG_EDIT: DeltaCompileEdit = DeltaCompileEdit(
    "project_config",
    r"\Z",
    "\n# reviewed {value}\n",
    fallback_reason="sqlbuild_project.toml is not a model or SQL test file",
)


def write_delta_compile_project(*, project_dir: Path, model_count: int) -> None:
    """Write the dense synthetic project on DuckDB: sources, seeds, functions, macros, SQL tests
    and custom rules."""

    write_dense_compile_project(project_dir=project_dir, model_count=model_count)
    replace_project_text(
        project_dir, _PROJECT_CONFIG, 'adapter = "snowflake"', 'adapter = "duckdb"'
    )


def _project_files(project_dir: Path, on_test_file: bool) -> list[Path]:
    root: Path = project_dir / ("tests" if on_test_file else "models")
    return sorted(path for path in root.rglob("*.sql") if "/_" not in path.as_posix())


def _applied(path: Path, edit: DeltaCompileEdit, rng: random.Random) -> bool:
    text: str = path.read_text(encoding="utf-8")
    replacement: str = edit.replacement.replace("{value}", str(rng.randint(1, 10**6)))
    edited, count = re.subn(edit.pattern, replacement, text, count=1)
    if count == 0 or edited == text:
        return False
    path.write_text(edited, encoding="utf-8")
    return True


def _edited_file(project_dir: Path, edit: DeltaCompileEdit, rng: random.Random) -> tuple[Path, str]:
    """Apply `edit` to a randomly chosen file it changes; return the file and its old text."""

    if edit is _CONFIG_EDIT:
        candidates: list[Path] = [project_dir / _PROJECT_CONFIG]
    else:
        candidates = _project_files(project_dir, edit.on_test_file)
    for _ in range(_EDIT_ATTEMPTS):
        path: Path = rng.choice(candidates)
        original: str = path.read_text(encoding="utf-8")
        if _applied(path, edit, rng):
            return path, original
    raise AssertionError(f"no file takes the {edit.kind} edit")


def _assert_outcome(
    run: DeltaCompileRun, edit: DeltaCompileEdit, step: str, other_files_edited: bool
) -> bool:
    """Assert `run` compiled `edit` as it must; return whether it compiled as a delta."""

    assert run.returncode != _MISMATCH_EXIT_CODE, f"{step}: {run.mismatches}"
    assert run.mismatches == [], step
    if COMPILE_REUSE_HIT_LINE in run.stderr:
        # A revert to the state of a compile that stored nothing, such as one that raised,
        # replays the compile stored before it.
        assert "revert" in step, step
        return False
    reason: str | None = run.fallback_reason
    if other_files_edited and reason is not None and _STALE_PROBLEMS in reason:
        return False
    if edit.fallback_reason is None:
        assert run.verified, f"{step}: fell back: {reason}\n{run.stderr[-2000:]}"
        return True
    assert reason is not None and edit.fallback_reason in reason, f"{step}: {reason}"
    return False


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
    rng: random.Random = random.Random(test_case.seed)
    baseline: DeltaCompileRun = run_delta_compile(
        project_dir=project_dir, json_output=test_case.json_output, env=_VERIFY_ENV
    )
    assert baseline.returncode == 0, baseline.stderr[-2000:]
    pending: list[tuple[Path, str, DeltaCompileEdit]] = []
    edits: tuple[DeltaCompileEdit, ...] = (*_EDITS, _CONFIG_EDIT)
    weights: list[int] = [
        _FALLBACK_WEIGHT if edit.fallback_reason else _DELTA_WEIGHT for edit in edits
    ]
    failing: bool = False
    deltas: int = 0
    for index in range(test_case.steps):
        if pending and (failing or rng.random() < _REVERT_PROBABILITY):
            path, original, edit = pending.pop()
            path.write_text(original, encoding="utf-8")
            step: str = f"step {index}: revert {edit.kind} in {path.name}"
        else:
            edit = rng.choices(edits, weights=weights)[0]
            path, original = _edited_file(project_dir, edit, rng)
            pending.append((path, original, edit))
            step = f"step {index}: {edit.kind} in {path.name}"
        run: DeltaCompileRun = run_delta_compile(
            project_dir=project_dir, json_output=test_case.json_output, env=_VERIFY_ENV
        )
        other_files_edited: bool = any(other != path for other, _, _ in pending)
        deltas += _assert_outcome(run, edit, step, other_files_edited)
        failing = run.returncode != 0
    assert deltas >= _MINIMUM_DELTAS


def test_given_unchanged_project_when_compiling_after_a_delta_then_the_delta_is_replayed(
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "dense_orders"
    write_delta_compile_project(project_dir=project_dir, model_count=_MODEL_COUNT)
    full: DeltaCompileRun = run_delta_compile(project_dir=project_dir, json_output=True)
    edited: Path = _project_files(project_dir, on_test_file=False)[7]
    rng: random.Random = random.Random(5)
    assert _applied(edited, _EDITS[0], rng)
    delta: DeltaCompileRun = run_delta_compile(project_dir=project_dir, json_output=True)
    replayed: DeltaCompileRun = run_delta_compile(project_dir=project_dir, json_output=True)

    assert full.returncode == delta.returncode == replayed.returncode == 0
    assert DELTA_COMPILE_LINE in delta.stderr
    assert DELTA_COMPILE_LINE not in replayed.stderr
    assert COMPILE_REUSE_HIT_LINE in replayed.stderr
    assert replayed.stdout.count('"compile_timings"') == 1
    assert _without_timings(replayed.stdout) == _without_timings(delta.stdout)


def test_given_edit_changing_downstream_shapes_when_compiling_the_next_edit_then_both_are_deltas(
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "dense_orders"
    write_delta_compile_project(project_dir=project_dir, model_count=_MODEL_COUNT)
    models: list[Path] = _project_files(project_dir, on_test_file=False)
    reshaped: Path = next(
        path for path in models if "quantity_000 (type DOUBLE" in path.read_text(encoding="utf-8")
    )
    baseline: DeltaCompileRun = run_delta_compile(project_dir=project_dir, json_output=True)
    reshaped.write_text(
        reshaped.read_text(encoding="utf-8")
        .replace("quantity_000 (type DOUBLE", "quantity_000 (type FLOAT", 1)
        .replace("AS DOUBLE) AS quantity_000", "AS FLOAT) AS quantity_000"),
        encoding="utf-8",
    )
    shape_edit: DeltaCompileRun = run_delta_compile(project_dir=project_dir, json_output=True)
    assert _applied(models[11], _EDITS[0], random.Random(3))
    next_edit: DeltaCompileRun = run_delta_compile(project_dir=project_dir, json_output=True)
    full: DeltaCompileRun = run_delta_compile(
        project_dir=project_dir, json_output=True, env={DELTA_COMPILE_DISABLE_ENV_VAR: "1"}
    )

    assert baseline.returncode == 0, baseline.stderr[-2000:]
    assert re.search(r"\(([2-9]|\d\d+) model\(s\)", shape_edit.stderr), shape_edit.stderr[-2000:]
    assert DELTA_COMPILE_LINE in next_edit.stderr, next_edit.stderr[-2000:]
    assert DELTA_COMPILE_LINE not in full.stderr
    assert _without_timings(next_edit.stdout) == _without_timings(full.stdout)


def _without_timings(report: str) -> str:
    return re.sub(r'"compile_timings": \{[^}]*\}', "", report)


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
    config: Path = project_dir / _PROJECT_CONFIG
    config.write_text(config.read_text(encoding="utf-8") + test_case.settings, encoding="utf-8")
    first: DeltaCompileRun = run_delta_compile(
        project_dir=project_dir, json_output=False, env=test_case.env
    )
    replace_project_text(
        project_dir,
        _project_files(project_dir, on_test_file=False)[3].relative_to(project_dir).as_posix(),
        "COALESCE(b.amount, ",
        "COALESCE(b.amount, 1 + ",
    )
    edited: DeltaCompileRun = run_delta_compile(
        project_dir=project_dir, json_output=False, env=test_case.env
    )

    assert first.returncode == edited.returncode == 0, edited.stderr[-2000:]
    assert DELTA_COMPILE_LINE not in edited.stderr
    assert sorted((project_dir / _REUSE_ROOT).glob("*.image")) == []


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
