"""Integration coverage for resuming the old-name steps of a same-model alias move."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    build_ok,
    load_raw_orders,
    order_ids,
    write_project,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views._test_types import (
    OldNameAliasResumeTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views.helpers import (
    PROJECT_TOML,
    aliased_orders_sql,
    build_result,
    fail_non_transactional_view,
    fail_transactional_view,
    old_name_facts,
    plan_text,
    relation_type,
)


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameAliasResumeTestCase(
            description="view creation interrupted and rolled back with the archive",
            install_failure=fail_transactional_view,
            expected_facts_after_failure=("required",),
            expected_plan_fragment="        └── old table  archived",
        ),
        OldNameAliasResumeTestCase(
            description="view creation interrupted after the archive",
            install_failure=fail_non_transactional_view,
            expected_facts_after_failure=("required", "origin_archived"),
            expected_plan_fragment="        └── old table  already archived",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_alias_move_when_retrying_then_view_is_created_at_the_old_alias(
    test_case: OldNameAliasResumeTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorded move proves ownership even after the model's own fingerprint moved on."""

    write_project(
        project_dir=tmp_path,
        models={"orders": aliased_orders_sql(alias="legacy_orders")},
        project_toml=PROJECT_TOML,
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    write_project(
        project_dir=tmp_path,
        models={
            "orders": aliased_orders_sql(alias="current_orders", migrate_from="main.legacy_orders")
        },
        project_toml=PROJECT_TOML,
    )
    with monkeypatch.context() as patch:
        test_case.install_failure(patch)
        _ = build_result(project_dir=tmp_path, capsys=capsys)
    facts_after_failure: tuple[str, ...] = old_name_facts(project_dir=tmp_path)

    plan: str = plan_text(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert facts_after_failure == test_case.expected_facts_after_failure
    assert relation_type(project_dir=tmp_path, name="legacy_orders") == "VIEW"
    assert order_ids(project_dir=tmp_path, relation="main.legacy_orders") == (1, 2, 3)
    assert old_name_facts(project_dir=tmp_path) == ("required", "origin_archived", "view_created")
    assert test_case.expected_plan_fragment in plan, plan
