"""Integration coverage for a janitor crash between dropping a view and recording the drop."""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    CliRun,
    build,
    build_ok,
    relation_names,
    run_sqb,
    write_project,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views._test_types import (
    OldNameJanitorClaimTestCase,
    OldNameJanitorResumeTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views.helpers import (
    DESTINATION_MODEL,
    JANITOR_PROJECT_TOML,
    ORIGIN_MODEL,
    claiming_view_models,
    fail_janitor_drop_fact,
    fail_view_fingerprint_write,
    no_build_fault,
    old_name_facts,
    prepare_table_rename,
    relation_type_in,
)

_ONE_BUILD: tuple[tuple[str, ...], ...] = (("build",),)
_CLAIMED: str = "└── record  dropped  (name now used by another relation, model:revenue)"


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameJanitorResumeTestCase(
            description="early drop interrupted before its record",
            early_drop=("janitor", "--auto-approve", "--drop-old-name-view", "dev.revenue"),
            builds_after_crash=0,
            expected_facts_after_crash=("required", "origin_archived", "view_created"),
            expected_retry_fragment="└── record  dropped  (the view no longer exists)",
            expected_final_facts=("required", "origin_archived", "view_created", "view_dropped"),
        ),
        OldNameJanitorResumeTestCase(
            description="destination build after the interrupted drop leaves the view absent",
            early_drop=("janitor", "--auto-approve", "--drop-old-name-view", "dev.revenue"),
            builds_after_crash=1,
            expected_facts_after_crash=("required", "origin_archived", "view_created"),
            expected_retry_fragment="└── record  dropped  (the view no longer exists)",
            expected_final_facts=("required", "origin_archived", "view_created", "view_dropped"),
        ),
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
    for _ in range(test_case.builds_after_crash):
        _ = build_ok(project_dir=tmp_path, capsys=capsys)
    names_before_retry: list[str] = relation_names(project_dir=tmp_path, schema="dev")
    retry: CliRun = run_sqb(project_dir=tmp_path, args=("janitor", "--auto-approve"), capsys=capsys)

    assert first.exit_code != 0, first.output
    assert facts_after_crash == test_case.expected_facts_after_crash
    assert ORIGIN_MODEL not in names_before_retry
    assert retry.exit_code == 0, retry.output
    assert test_case.expected_retry_fragment in retry.output
    assert old_name_facts(project_dir=tmp_path, schema="dev") == test_case.expected_final_facts


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameJanitorClaimTestCase(
            description="plain janitor run records the claimed name without touching it",
            janitor_args=("janitor", "--auto-approve"),
            install_build_fault=no_build_fault,
            claiming_builds=_ONE_BUILD,
            expected_janitor_fragment=_CLAIMED,
            expected_old_name_type="VIEW",
            expected_final_facts=("required", "origin_archived", "view_created", "view_dropped"),
        ),
        OldNameJanitorClaimTestCase(
            description="repeated early drop leaves the project's view in place",
            janitor_args=("janitor", "--auto-approve", "--drop-old-name-view", "dev.revenue"),
            install_build_fault=no_build_fault,
            claiming_builds=_ONE_BUILD,
            expected_janitor_fragment=_CLAIMED,
            expected_old_name_type="VIEW",
            expected_final_facts=("required", "origin_archived", "view_created", "view_dropped"),
        ),
        OldNameJanitorClaimTestCase(
            description="repeated early drop spares a project view built without a fingerprint",
            janitor_args=("janitor", "--auto-approve", "--drop-old-name-view", "dev.revenue"),
            install_build_fault=fail_view_fingerprint_write,
            claiming_builds=_ONE_BUILD,
            expected_janitor_fragment=_CLAIMED,
            expected_old_name_type="VIEW",
            expected_final_facts=("required", "origin_archived", "view_created", "view_dropped"),
        ),
        OldNameJanitorClaimTestCase(
            description="destination built after the project's view leaves that view alone",
            janitor_args=("janitor", "--auto-approve", "--drop-old-name-view", "dev.revenue"),
            install_build_fault=no_build_fault,
            claiming_builds=(
                ("build", "--select", ORIGIN_MODEL),
                ("build", "--select", DESTINATION_MODEL),
            ),
            expected_janitor_fragment=_CLAIMED,
            expected_old_name_type="VIEW",
            expected_final_facts=("required", "origin_archived", "view_created", "view_dropped"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_early_drop_when_project_builds_the_name_then_janitor_leaves_it(
    test_case: OldNameJanitorClaimTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Janitor never drops a relation the project built at a recorded view's name."""

    prepare_table_rename(project_dir=tmp_path, capsys=capsys, project_toml=JANITOR_PROJECT_TOML)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    with monkeypatch.context() as patch:
        fail_janitor_drop_fact(patch)
        with contextlib.suppress(RuntimeError):
            _ = run_sqb(
                project_dir=tmp_path,
                args=("janitor", "--auto-approve", "--drop-old-name-view", "dev.revenue"),
                capsys=capsys,
            )
    write_project(
        project_dir=tmp_path, models=claiming_view_models(), project_toml=JANITOR_PROJECT_TOML
    )
    with monkeypatch.context() as patch:
        test_case.install_build_fault(patch)
        for args in test_case.claiming_builds:
            claiming: CliRun = run_sqb(project_dir=tmp_path, args=args, capsys=capsys)
            assert claiming.exit_code == 0, claiming.output

    janitor: CliRun = run_sqb(project_dir=tmp_path, args=test_case.janitor_args, capsys=capsys)
    old_name_type: str | None = relation_type_in(
        project_dir=tmp_path, schema="dev", name=ORIGIN_MODEL
    )
    facts: tuple[str, ...] = old_name_facts(project_dir=tmp_path, schema="dev")
    rebuild: CliRun = build(project_dir=tmp_path, capsys=capsys)

    assert old_name_type == test_case.expected_old_name_type
    assert facts == test_case.expected_final_facts
    assert janitor.exit_code == 0, janitor.output
    assert test_case.expected_janitor_fragment in janitor.output, janitor.output
    assert rebuild.exit_code == 0, rebuild.output
