"""Integration coverage for whole-project compile reuse when the stored compile is disrupted."""

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.compile_outputs._test_types import (
    ReuseDisruptionTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.compile_outputs.helpers import (
    OUTPUT_PROJECT_FILES,
    ReuseComparison,
    block_stored_compiles,
    change_native_build,
    change_runtime,
    corrupt_stored_compiles,
    edit_loaded_module,
    edit_then_fail_store,
    load_helper_module,
    record_output_work,
    reuse_against_uncached,
    set_tracked_variable,
    set_untracked_variable,
    stored_compile_files,
    truncate_stored_compiles,
    write_files,
)

_REPLAYED_AFTER: tuple[bool, ...] = (False, True, False, True)
_MISSED_AFTER: tuple[bool, ...] = (False, True, False, False)


@pytest.mark.parametrize(
    "test_case",
    [
        ReuseDisruptionTestCase(
            description="native engine: corrupt stored compile",
            engine="native",
            disrupt=corrupt_stored_compiles,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="native engine: truncated stored compile",
            engine="native",
            disrupt=truncate_stored_compiles,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="native engine: changed interpreter",
            engine="native",
            disrupt=change_runtime,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="native engine: changed native build",
            engine="native",
            disrupt=change_native_build,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="native engine: edited loaded module",
            engine="native",
            disrupt=edit_loaded_module,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="native engine: unwritable stored compile",
            engine="native",
            disrupt=block_stored_compiles,
            expected_reused=_MISSED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="native engine: failing store after an edit",
            engine="native",
            disrupt=edit_then_fail_store,
            expected_reused=_MISSED_AFTER,
            expected_slots=0,
        ),
        ReuseDisruptionTestCase(
            description="native engine: tracked environment variable set",
            engine="native",
            disrupt=set_tracked_variable,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="native engine: untracked environment variable set",
            engine="native",
            disrupt=set_untracked_variable,
            expected_reused=(False, True, True, True),
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="python engine: corrupt stored compile",
            engine="python",
            disrupt=corrupt_stored_compiles,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="python engine: truncated stored compile",
            engine="python",
            disrupt=truncate_stored_compiles,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="python engine: changed interpreter",
            engine="python",
            disrupt=change_runtime,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="python engine: changed native build",
            engine="python",
            disrupt=change_native_build,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="python engine: edited loaded module",
            engine="python",
            disrupt=edit_loaded_module,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="python engine: unwritable stored compile",
            engine="python",
            disrupt=block_stored_compiles,
            expected_reused=_MISSED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="python engine: failing store after an edit",
            engine="python",
            disrupt=edit_then_fail_store,
            expected_reused=_MISSED_AFTER,
            expected_slots=0,
        ),
        ReuseDisruptionTestCase(
            description="python engine: tracked environment variable set",
            engine="python",
            disrupt=set_tracked_variable,
            expected_reused=_REPLAYED_AFTER,
            expected_slots=1,
        ),
        ReuseDisruptionTestCase(
            description="python engine: untracked environment variable set",
            engine="python",
            disrupt=set_untracked_variable,
            expected_reused=(False, True, True, True),
            expected_slots=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_compile_disrupted_when_rerunning_then_it_misses_and_matches_uncached(
    test_case: ReuseDisruptionTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "project"
    write_files(project_dir=project_dir, files=OUTPUT_PROJECT_FILES)
    load_helper_module(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _ = record_output_work(monkeypatch=monkeypatch, engine=test_case.engine, reuse_disabled="0")

    cold: ReuseComparison = reuse_against_uncached(project_dir=project_dir, capsys=capsys)
    warm: ReuseComparison = reuse_against_uncached(project_dir=project_dir, capsys=capsys)
    test_case.disrupt(project_dir, monkeypatch)
    disrupted: ReuseComparison = reuse_against_uncached(project_dir=project_dir, capsys=capsys)
    after: ReuseComparison = reuse_against_uncached(project_dir=project_dir, capsys=capsys)
    runs: tuple[ReuseComparison, ...] = (cold, warm, disrupted, after)

    assert [run.outcome for run in runs] == [run.reference for run in runs]
    assert tuple(run.reused for run in runs) == test_case.expected_reused
    assert len(stored_compile_files(project_dir=project_dir)) == test_case.expected_slots
