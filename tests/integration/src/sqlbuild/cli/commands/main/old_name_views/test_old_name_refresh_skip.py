"""Integration coverage for leaving unchanged late-binding compatibility views alone."""

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
    OldNameRefreshSkipTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.old_name_views.helpers import (
    DESTINATION_MODEL,
    ORIGIN_MODEL,
    PROJECT_TOML,
    aliased_table_sql,
    record_old_name_view_ddl,
    table_sql,
)


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameRefreshSkipTestCase(
            description="unchanged select-star view is not redefined",
            renamed_sql=table_sql(migrate_from=ORIGIN_MODEL),
            rebuilt_sql=table_sql(migrate_from=ORIGIN_MODEL),
            expected_view_statements=0,
        ),
        OldNameRefreshSkipTestCase(
            description="unchanged aliased view is not redefined",
            renamed_sql=aliased_table_sql(),
            rebuilt_sql=aliased_table_sql(),
            expected_view_statements=0,
        ),
        OldNameRefreshSkipTestCase(
            description="aliased view whose column list changed is redefined once",
            renamed_sql=aliased_table_sql(),
            rebuilt_sql=aliased_table_sql(extra_column=", order_id * 10 AS order_rank"),
            expected_view_statements=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_live_view_when_destination_rebuilds_then_only_changed_sql_is_redefined(
    test_case: OldNameRefreshSkipTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Views that bind by name at query time need no DDL while their SQL is unchanged."""

    write_project(
        project_dir=tmp_path, models={ORIGIN_MODEL: table_sql()}, project_toml=PROJECT_TOML
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    write_project(
        project_dir=tmp_path,
        models={DESTINATION_MODEL: test_case.renamed_sql},
        project_toml=PROJECT_TOML,
    )
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    write_project(
        project_dir=tmp_path,
        models={DESTINATION_MODEL: test_case.rebuilt_sql},
        project_toml=PROJECT_TOML,
    )
    statements: list[str] = []

    with monkeypatch.context() as patch:
        record_old_name_view_ddl(patch, statements)
        _ = build_ok(project_dir=tmp_path, capsys=capsys)
        _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert len(statements) == test_case.expected_view_statements, statements
    assert order_ids(project_dir=tmp_path, relation=f"main.{ORIGIN_MODEL}") == (1, 2, 3)
