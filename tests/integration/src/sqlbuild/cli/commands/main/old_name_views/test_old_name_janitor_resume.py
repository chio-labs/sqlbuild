"""Integration coverage for a janitor crash between dropping a view and recording the drop."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    CliRun,
    build_ok,
    relation_names,
    run_sqb,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views._test_types import (
    OldNameJanitorResumeTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views.helpers import (
    JANITOR_PROJECT_TOML,
    ORIGIN_MODEL,
    fail_janitor_drop_fact,
    old_name_facts,
    prepare_table_rename,
)


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameJanitorResumeTestCase(
            description="early drop interrupted before its record",
            early_drop=("janitor", "--auto-approve", "--drop-old-name-view", "dev.revenue"),
            expected_facts_after_crash=("required", "origin_archived", "view_created"),
            expected_retry_fragment="└── record  dropped  (the view no longer exists)",
            expected_final_facts=("required", "origin_archived", "view_created", "view_dropped"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_janitor_crash_after_drop_when_rerunning_then_drop_is_recorded_as_missing(
    test_case: OldNameJanitorResumeTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vanished compatibility view is recorded as dropped instead of lingering in state."""

    prepare_table_rename(project_dir=tmp_path, capsys=capsys, project_toml=JANITOR_PROJECT_TOML)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    with monkeypatch.context() as patch:
        fail_janitor_drop_fact(patch)
        try:
            first: CliRun = run_sqb(project_dir=tmp_path, args=test_case.early_drop, capsys=capsys)
        except RuntimeError as error:
            first = CliRun(exit_code=1, output=str(error))
    facts_after_crash: tuple[str, ...] = old_name_facts(project_dir=tmp_path, schema="dev")
    retry: CliRun = run_sqb(project_dir=tmp_path, args=("janitor", "--auto-approve"), capsys=capsys)

    assert first.exit_code != 0, first.output
    assert facts_after_crash == test_case.expected_facts_after_crash
    assert ORIGIN_MODEL not in relation_names(project_dir=tmp_path, schema="dev")
    assert retry.exit_code == 0, retry.output
    assert test_case.expected_retry_fragment in retry.output
    assert old_name_facts(project_dir=tmp_path, schema="dev") == test_case.expected_final_facts
