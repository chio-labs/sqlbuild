"""Integration coverage for resuming old-name steps after a crash in every failure window."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    CliRun,
    build_ok,
    order_ids,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views._test_types import (
    OldNameResumeTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views.helpers import (
    ORIGIN_MODEL,
    build_result,
    fail_destination_build,
    fail_non_transactional_archive_fact,
    fail_non_transactional_view,
    fail_non_transactional_view_fact,
    fail_transactional_view,
    old_name_facts,
    origin_archive_count,
    prepare_table_rename,
    relation_type,
)

_ALL_FACTS: tuple[str, ...] = ("required", "origin_archived", "view_created")


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameResumeTestCase(
            description="destination build fails after the move is recorded",
            install_failure=fail_destination_build,
            expected_first_exit_code=1,
            expected_facts_after_failure=("required",),
            expected_old_name_type_after_failure="BASE TABLE",
            expected_final_facts=_ALL_FACTS,
            expected_archive_count=1,
        ),
        OldNameResumeTestCase(
            description="transactional crash creating the view rolls the archive back",
            install_failure=fail_transactional_view,
            expected_first_exit_code=1,
            expected_facts_after_failure=("required",),
            expected_old_name_type_after_failure="BASE TABLE",
            expected_final_facts=_ALL_FACTS,
            expected_archive_count=1,
        ),
        OldNameResumeTestCase(
            description="non-transactional crash after archiving adopts the existing archive",
            install_failure=fail_non_transactional_archive_fact,
            expected_first_exit_code=1,
            expected_facts_after_failure=("required",),
            expected_old_name_type_after_failure=None,
            expected_final_facts=_ALL_FACTS,
            expected_archive_count=1,
        ),
        OldNameResumeTestCase(
            description="non-transactional crash before the view creates only the view",
            install_failure=fail_non_transactional_view,
            expected_first_exit_code=1,
            expected_facts_after_failure=("required", "origin_archived"),
            expected_old_name_type_after_failure=None,
            expected_final_facts=_ALL_FACTS,
            expected_archive_count=1,
        ),
        OldNameResumeTestCase(
            description="non-transactional crash after the view records it on retry",
            install_failure=fail_non_transactional_view_fact,
            expected_first_exit_code=1,
            expected_facts_after_failure=("required", "origin_archived"),
            expected_old_name_type_after_failure="VIEW",
            expected_final_facts=_ALL_FACTS,
            expected_archive_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_old_name_steps_when_rebuilding_then_steps_resume_once(
    test_case: OldNameResumeTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry completes the archive and view exactly once from facts and physical state."""

    prepare_table_rename(project_dir=tmp_path, capsys=capsys)

    with monkeypatch.context() as patch:
        test_case.install_failure(patch)
        first: CliRun = build_result(project_dir=tmp_path, capsys=capsys)
    facts_after_failure: tuple[str, ...] = old_name_facts(project_dir=tmp_path)
    type_after_failure: str | None = relation_type(project_dir=tmp_path, name=ORIGIN_MODEL)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert first.exit_code == test_case.expected_first_exit_code, first.output
    assert facts_after_failure == test_case.expected_facts_after_failure
    assert type_after_failure == test_case.expected_old_name_type_after_failure
    assert old_name_facts(project_dir=tmp_path) == test_case.expected_final_facts
    assert relation_type(project_dir=tmp_path, name=ORIGIN_MODEL) == "VIEW"
    assert origin_archive_count(project_dir=tmp_path) == test_case.expected_archive_count
    assert order_ids(project_dir=tmp_path, relation=f"main.{ORIGIN_MODEL}") == (1, 2, 3)
