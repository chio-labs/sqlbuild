"""E2E coverage of project-wide Rules on a selected plan, which must agree with compile."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.rules._test_types import (
    SelectedProjectWideRuleCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.rules.helpers import (
    compile_diagnostics,
    duckdb_rules_project_toml,
    run_compile_cli,
    run_unevaluated_rules_cli,
    write_model_files,
)

_FINDING_LINE: re.Pattern[str] = re.compile(r"^(\S+):\d+:\d+ \[(SQBR\w+)\] ", re.MULTILINE)
_RETURNS_PATH: str = "models/sales/mart/sales__mart__returns__finance.sql"
_REFUNDS_PATH: str = "models/sales/mart/sales__mart__refunds__audit.sql"
_ORDERS_PATH: str = "models/sales/mart/sales__mart__orders.sql"
_CUSTOMERS_PATH: str = "models/sales/mart/sales__mart__customers.sql"
_CONSUMER_PATH: str = "models/finance/staging/finance__stg_v__orders.sql"
_FILES: tuple[tuple[str, str], ...] = (
    (
        "models/sales/intermediate/clean/sales__int_clean__orders.sql",
        "MODEL (description 'Clean orders.');\nSELECT 1 AS order_id\n",
    ),
    (_ORDERS_PATH, "MODEL (description 'Published orders.');\nSELECT 1 AS order_id\n"),
    (
        _CUSTOMERS_PATH,
        "MODEL (description 'Published customers.');\n"
        'SELECT o.order_id FROM __ref("sales__int_clean__orders") AS o\n',
    ),
    (
        "models/sales/mart/sales__mart__products.sql",
        "MODEL (description 'Published products.');\nSELECT 1 AS order_id\n",
    ),
    (
        _RETURNS_PATH,
        "MODEL (description 'Returns for finance.');\n"
        'SELECT o.order_id FROM __ref("sales__int_clean__orders") AS o\n',
    ),
    (_REFUNDS_PATH, "MODEL (description 'Refunds for audit.');\nSELECT 1 AS order_id\n"),
    (
        _CONSUMER_PATH,
        "MODEL (description 'Finance view of sales orders.');\n"
        'SELECT r.order_id FROM __ref("sales__mart__returns__finance") AS r\n'
        'JOIN __ref("sales__mart__refunds__audit") AS f ON r.order_id = f.order_id\n'
        'JOIN __ref("sales__mart__orders") AS o ON r.order_id = o.order_id\n',
    ),
)
_QUALIFIED_IGNORES: str = (
    "\n[[rules.rule_ignores]]\n"
    'rules = ["SQBRPROJECT107"]\n'
    f'paths = ["{_RETURNS_PATH}", "{_REFUNDS_PATH}"]\n'
    'reason = "Reviewed qualified variants."\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        SelectedProjectWideRuleCase(
            description="a slice whose own majority differs keeps the whole-project shape",
            rules_toml='select = ["SQBRPROJECT107"]\n' + _QUALIFIED_IGNORES,
            selection=("+finance__stg_v__orders",),
            expected_compile_findings=(),
            expected_plan_findings=(),
            expected_plan_exit=0,
        ),
        SelectedProjectWideRuleCase(
            description="findings on models outside the slice are left out",
            rules_toml='select = ["SQBRPROJECT107", "SQBRMODEL101"]\n',
            selection=("sales__mart__returns__finance",),
            expected_compile_findings=(
                ("SQBRMODEL101", _CONSUMER_PATH),
                ("SQBRMODEL101", _CUSTOMERS_PATH),
                ("SQBRMODEL101", _RETURNS_PATH),
                ("SQBRPROJECT107", _REFUNDS_PATH),
                ("SQBRPROJECT107", _RETURNS_PATH),
            ),
            expected_plan_findings=(
                ("SQBRMODEL101", _RETURNS_PATH),
                ("SQBRPROJECT107", _RETURNS_PATH),
            ),
            expected_plan_exit=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selection_when_planning_then_project_wide_rules_match_whole_project_compile(
    test_case: SelectedProjectWideRuleCase,
    tmp_path: Path,
) -> None:
    write_model_files(
        project_dir=tmp_path,
        toml=duckdb_rules_project_toml(project_dir=tmp_path, rules_toml=test_case.rules_toml),
        files=_FILES,
    )

    compiled: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)
    plans: tuple[subprocess.CompletedProcess[str], ...] = tuple(
        run_unevaluated_rules_cli(tmp_path, "plan", "--select", *test_case.selection)
        for _ in ("cold", "warm")
    )

    compile_findings: tuple[tuple[str, str], ...] = tuple(
        sorted({(str(item["code"]), str(item["path"])) for item in compile_diagnostics(compiled)})
    )
    assert compile_findings == test_case.expected_compile_findings, compiled.stdout
    for planned in plans:
        plan_output: str = planned.stdout + planned.stderr
        plan_findings: tuple[tuple[str, str], ...] = tuple(
            sorted({(code, path) for path, code in _FINDING_LINE.findall(plan_output)})
        )
        assert plan_findings == test_case.expected_plan_findings, plan_output
        assert planned.returncode == test_case.expected_plan_exit, plan_output
        assert "Traceback" not in plan_output, plan_output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
