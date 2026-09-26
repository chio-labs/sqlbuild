"""Real CLI coverage of compiler-accepted SQL beyond the Rules parser budget."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.rules._test_types import (
    UnevaluatedResourceCase,
    UnevaluatedRuleCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.rules.helpers import (
    run_unevaluated_rules_cli,
    write_unevaluated_rules_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        UnevaluatedResourceCase(
            "model guard",
            "models/staging/orders.sql",
            "MODEL ();\nSELECT {expression} AS order_id",
            0,
        ),
        UnevaluatedResourceCase(
            "opaque predicate",
            "models/staging/orders.sql",
            "MODEL (database warehouse, schema analytics);\nSELECT 1 AS order_id WHERE NOT SPLIT_PART('orders:pending', ':', 2) LIKE 'pending%'",
            0,
            "unsupported syntax: native parser retained an opaque SQL node",
            "snowflake",
        ),
        UnevaluatedResourceCase(
            "audit guard", "audits/orders.sql", "AUDIT ();\nSELECT {expression} AS order_id"
        ),
        UnevaluatedResourceCase(
            "SQL-test guard",
            "tests/unit/test_orders.sql",
            "TEST ();\nWITH __ref__orders AS (SELECT {expression} AS order_id), __expected__orders AS (SELECT 1 AS order_id) SELECT 1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_guarded_resource_when_running_rules_then_reports_failure_and_coverage(
    test_case: UnevaluatedResourceCase,
    tmp_path: Path,
) -> None:
    write_unevaluated_rules_project(
        project_dir=tmp_path,
        resource_path=test_case.path,
        resource_template=test_case.template,
        adapter=test_case.adapter,
    )
    for _ in range(2):
        result: subprocess.CompletedProcess[str] = run_unevaluated_rules_cli(
            tmp_path, "rules", "--json", "run", "SQBRSQL035"
        )
        assert result.returncode == 1, result.stdout + result.stderr
        payload: dict[str, Any] = json.loads(result.stdout)
        assert payload["unevaluated_resources"] == 1
        assert payload["evaluated_models"] == test_case.expected_evaluated_models
        (finding,) = payload["findings"]
        assert finding["code"] == "rules-unevaluated"
        assert finding["path"] == test_case.path
        assert "SQBRSQL035" in finding["message"]
        assert test_case.expected_reason in finding["message"]
    human: subprocess.CompletedProcess[str] = run_unevaluated_rules_cli(
        tmp_path, "rules", "run", "SQBRSQL035"
    )
    assert human.returncode == 1
    assert (
        f"{test_case.expected_evaluated_models} models evaluated, 1 resources could not be evaluated"
        in human.stdout
    )
    assert "passed" not in human.stdout
    compiled: subprocess.CompletedProcess[str] = run_unevaluated_rules_cli(
        tmp_path, "compile", "--no-cache", "--json"
    )
    assert compiled.returncode == 1, compiled.stdout + compiled.stderr
    diagnostics: list[dict[str, Any]] = json.loads(compiled.stdout)["diagnostics"]
    assert any(
        item["code"] == "rules-unevaluated" and item["path"] == test_case.path
        for item in diagnostics
    )


@pytest.mark.parametrize(
    "test_case",
    [
        UnevaluatedRuleCase(
            "model analysis opt out", model_options="sql_analysis false", expected_exit=0
        ),
        UnevaluatedRuleCase(
            "path analysis opt out",
            configuration="\n[path_defaults.staging]\nsql_analysis = false\n",
            expected_exit=0,
        ),
        UnevaluatedRuleCase(
            "explicit scoped rule ignore",
            configuration='\n[[rules.rule_ignores]]\nrules = ["SQBRSQL035"]\npaths = ["models/staging/orders.sql"]\nreason = "External SQL syntax"\n',
            expected_exit=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_escape_hatch_when_running_rules_then_honors_policy(
    test_case: UnevaluatedRuleCase,
    tmp_path: Path,
) -> None:
    write_unevaluated_rules_project(
        project_dir=tmp_path,
        model_options=test_case.model_options,
        configuration=test_case.configuration,
    )
    result: subprocess.CompletedProcess[str] = run_unevaluated_rules_cli(
        tmp_path, "rules", "--json", "run", "SQBRSQL035"
    )
    assert result.returncode == test_case.expected_exit, result.stdout + result.stderr
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["unevaluated_resources"] == 0
    assert payload["findings"] == []
    compiled: subprocess.CompletedProcess[str] = run_unevaluated_rules_cli(
        tmp_path, "compile", "--no-cache", "--json"
    )
    assert compiled.returncode == test_case.expected_exit, compiled.stdout + compiled.stderr
    assert json.loads(compiled.stdout)["diagnostics"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
