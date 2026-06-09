"""Direct changes-only JSON output E2E tests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    DirectChangesOnlyJsonE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_direct_changes_only_project_toml,
    direct_changes_only_stg_orders_sql,
    plan_changes_only_json,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyJsonE2ETestCase(
            description="reports semantic staleness without raw hashes",
            expected_reasons_by_name={
                "stg_orders": "query_changed",
                "fact_orders": "upstream_changed",
            },
            unexpected_json_fragments=(
                "expected_version_hash",
                "built_version_hash",
                "version_hash",
            ),
        )
    ],
    ids=["reports semantic staleness without raw hashes"],
)
def test_given_upstream_change_when_planning_json_then_reports_semantic_staleness(
    test_case: DirectChangesOnlyJsonE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_json_staleness",
        repo_files={
            "sqlbuild_project.toml": build_direct_changes_only_project_toml(
                project_name="direct_changes_only_json_staleness"
            ),
            "models/stg_orders.sql": direct_changes_only_stg_orders_sql(amount_cents=100),
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __ref("stg_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        direct_changes_only_stg_orders_sql(amount_cents=125),
        encoding="utf-8",
    )

    payload: dict[str, object] = plan_changes_only_json(project_dir=project_dir)

    models: list[dict[str, object]] = cast(list[dict[str, object]], payload["models"])
    assert {str(model["name"]): str(model["reason"]) for model in models} == (
        test_case.expected_reasons_by_name
    )
    serialized_payload: str = str(payload)
    for fragment in test_case.unexpected_json_fragments:
        assert fragment not in serialized_payload
