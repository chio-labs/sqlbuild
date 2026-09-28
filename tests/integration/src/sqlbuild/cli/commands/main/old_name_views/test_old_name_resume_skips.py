"""Integration coverage for resumed old-name steps that must leave the old name alone."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    build_ok,
    order_ids,
    write_project,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views._test_types import (
    OldNameResumeSkipTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views.helpers import (
    DESTINATION_MODEL,
    ORIGIN_MODEL,
    PROJECT_TOML,
    build_result,
    disabled_table_sql,
    fail_destination_build,
    fail_non_transactional_view,
    old_name_facts,
    origin_archive_count,
    plan_text,
    prepare_table_rename,
    relation_type,
    table_sql,
)


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameResumeSkipTestCase(
            description="old model restored before the archive keeps its table",
            install_failure=fail_destination_build,
            retry_models={ORIGIN_MODEL: table_sql(), DESTINATION_MODEL: table_sql()},
            expected_plan_fragment=(
                f"    └── old name  main.{ORIGIN_MODEL}\n"
                f"        └── left for janitor  name reused by model:{ORIGIN_MODEL}\n"
            ),
            expected_facts=("required",),
            expected_old_name_type="BASE TABLE",
            expected_old_name_ids=(1, 2, 3),
        ),
        OldNameResumeSkipTestCase(
            description="old model restored after the archive is rebuilt without a view",
            install_failure=fail_non_transactional_view,
            retry_models={ORIGIN_MODEL: table_sql(), DESTINATION_MODEL: table_sql()},
            expected_plan_fragment=(
                f"        └── left for janitor  name reused by model:{ORIGIN_MODEL}\n"
            ),
            expected_facts=("required", "origin_archived"),
            expected_old_name_type="BASE TABLE",
            expected_old_name_ids=(1, 2, 3),
        ),
        OldNameResumeSkipTestCase(
            description="old-name views turned off before the archive leave the old table",
            install_failure=fail_destination_build,
            retry_models={DESTINATION_MODEL: disabled_table_sql(migrate_from=ORIGIN_MODEL)},
            expected_plan_fragment="        └── left for janitor  old_name_view false\n",
            expected_facts=("required",),
            expected_old_name_type="BASE TABLE",
            expected_old_name_ids=(1, 2, 3),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_pending_old_name_steps_when_old_name_is_no_longer_ours_then_resume_skips_them(
    test_case: OldNameResumeSkipTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume applies the same checks as a new move: no archive and no view."""

    prepare_table_rename(project_dir=tmp_path, capsys=capsys)
    with monkeypatch.context() as patch:
        test_case.install_failure(patch)
        _ = build_result(project_dir=tmp_path, capsys=capsys)
    write_project(project_dir=tmp_path, models=test_case.retry_models, project_toml=PROJECT_TOML)

    plan: str = plan_text(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert old_name_facts(project_dir=tmp_path) == test_case.expected_facts
    assert relation_type(project_dir=tmp_path, name=ORIGIN_MODEL) == (
        test_case.expected_old_name_type
    )
    assert order_ids(project_dir=tmp_path, relation=f"main.{ORIGIN_MODEL}") == (
        test_case.expected_old_name_ids
    )
    assert origin_archive_count(project_dir=tmp_path) == len(test_case.expected_facts) - 1
    assert test_case.expected_plan_fragment in plan, plan
