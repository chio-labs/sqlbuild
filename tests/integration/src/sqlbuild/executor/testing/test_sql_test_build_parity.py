"""SQL tests render the SQL `build` sends, apart from fixture relation substitution."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.executor.testing._test_types import (
    SqlTestBuildParityTestCase,
)
from tests.integration.src.sqlbuild.executor.testing.helpers import (
    build_authored_cte_project_files,
    build_sql_matches_test_body,
    render_project_test_step,
)

_WAFFLE_SHOP: Path = Path(__file__).resolve().parents[6] / "tests/e2e/fixtures/waffle_shop"


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestBuildParityTestCase(
            description="staging model reading a source",
            test_name="test_stg_orders",
            model_name="stg_orders",
            expected_whole_body_rendered=True,
        ),
        SqlTestBuildParityTestCase(
            description="mart model joining refs and calling UDFs",
            test_name="test_fact_orders",
            model_name="fact_orders",
            expected_whole_body_rendered=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fixture_project_test_when_rendering_then_whole_build_sql_appears_verbatim(
    test_case: SqlTestBuildParityTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "waffle_shop"
    shutil.copytree(_WAFFLE_SHOP, project_dir)

    build_sql, test_body, rendered_sql = render_project_test_step(
        project_dir=project_dir, test_name=test_case.test_name, model_name=test_case.model_name
    )

    assert build_sql_matches_test_body(build_sql=build_sql, test_body=test_body), test_body
    assert (test_body in rendered_sql) is test_case.expected_whole_body_rendered, rendered_sql


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestBuildParityTestCase(
            description="CTE bodies with comments, quotes and dollar quotes are lifted verbatim",
            test_name="test_stg_orders",
            model_name="stg_orders",
            expected_whole_body_rendered=False,
            expected_verbatim_fragments=(
                "base AS (\n  -- a comment with an unmatched ) parenthesis\n"
                "  SELECT id AS order_id, amount, 'it''s (fine)' AS note /* ( */\n"
                "  FROM __source__raw_orders)",
                "tagged AS (SELECT order_id, amount, note, $$a ) b$$ AS tag FROM base)",
                "__actual__stg_orders AS (SELECT order_id, amount, note, tag FROM tagged)",
            ),
        ),
        SqlTestBuildParityTestCase(
            description="nested WITH stays inside its lifted CTE beside a colliding fixture CTE",
            test_name="test_orders",
            model_name="orders",
            expected_whole_body_rendered=False,
            expected_verbatim_fragments=(
                "totals AS (\n"
                "  WITH ranked AS (SELECT order_id, amount, tag FROM __ref__stg_orders)\n"
                "  SELECT order_id, amount * 2 AS doubled, tag FROM ranked)",
                "helper_rows AS (SELECT order_id, doubled, tag FROM totals)",
                "__actual__orders AS (SELECT order_id, doubled, tag FROM helper_rows)",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_ctes_when_rendering_then_build_sql_slices_appear_verbatim(
    test_case: SqlTestBuildParityTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, build_authored_cte_project_files())

    build_sql, test_body, rendered_sql = render_project_test_step(
        project_dir=tmp_path, test_name=test_case.test_name, model_name=test_case.model_name
    )

    assert build_sql_matches_test_body(build_sql=build_sql, test_body=test_body), test_body
    assert all(fragment in rendered_sql for fragment in test_case.expected_verbatim_fragments), (
        rendered_sql
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
