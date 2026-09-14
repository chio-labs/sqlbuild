"""Integration coverage for compiler-integrated built-in and custom rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    RulesIntegrationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("selected SQL rule blocks artifacts", 1, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_selected_sql_rule_when_compiling_then_authored_diagnostic_blocks_artifacts(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL004"]\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders LIMIT 1\n',
        encoding="utf-8",
    )

    first_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--manifest"])
    first: dict[str, object] = json.loads(capsys.readouterr().out)
    second_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--manifest"])
    second: dict[str, object] = json.loads(capsys.readouterr().out)
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders ORDER BY order_id LIMIT 1\n',
        encoding="utf-8",
    )
    third_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--manifest"])
    third: dict[str, object] = json.loads(capsys.readouterr().out)

    assert first_exit == second_exit == test_case.expected_exit_code
    diagnostics: object = first["diagnostics"]
    assert isinstance(diagnostics, list)
    assert diagnostics[0]["code"] == test_case.expected_code
    assert diagnostics[0]["path"] == "models/orders.sql"
    assert second["compile_timings"]["rule_cache_hits"] == 1
    assert third_exit == 0
    assert third["compile_timings"]["rule_cache_misses"] == 1
    assert third["diagnostics"] == []
    assert (tmp_path / "target" / "manifest.json").is_file()


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("custom rule is enforced and cached", 1, "XSQBRARCH001")],
    ids=lambda case: case.description,
)
def test_given_typed_custom_rule_when_compiling_then_same_rule_is_enforced_and_cached(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n'
        '[rules]\nselect = ["XSQBRARCH001"]\n\n'
        "[rules.thresholds]\nmin_custom_rule_test_cases = 0\n",
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id\n', encoding="utf-8")
    rule_file: Path = tmp_path / "rules" / "architecture.py"
    rule_file.parent.mkdir()
    rule_file.write_text(
        """from sqlbuild.rules import Finding, Model, RuleContext, rule

@rule(
    code="XSQBRARCH001",
    message="Final models must use the final directory",
    remediation="Move this model beneath models/final/.",
)
def final_directory(*, model: Model, ctx: RuleContext) -> list[Finding]:
    return [] if "final" in model.path.parts else [ctx.finding(subject=model)]
""",
        encoding="utf-8",
    )

    first_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    first: dict[str, object] = json.loads(capsys.readouterr().out)
    second_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    second: dict[str, object] = json.loads(capsys.readouterr().out)

    assert first_exit == second_exit == test_case.expected_exit_code
    assert first["diagnostics"][0]["code"] == test_case.expected_code
    assert second["compile_timings"]["rule_cache_hits"] >= 1
    host_inputs: Path = tmp_path / "target" / "rules-cache" / "host-inputs"
    assert not tuple(host_inputs.glob("*.pickle"))


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("focused SQL rule reports requested code", 1, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_project_when_running_focused_rule_family_then_only_that_family_runs(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders LIMIT 1\n',
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            "SQBRSQL004",
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    assert test_case.expected_code in json.dumps(payload["findings"])
    assert "Rule selection SQBRSQL004 failed with 1 finding(s)." in captured.err


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("inline join query is rejected", 1, "SQBRSQL039")],
    ids=lambda case: case.description,
)
def test_given_inline_query_relation_when_running_readability_rule_then_finding_is_reported(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        """MODEL (description "Orders");
WITH actual_orders AS (
  SELECT 1 AS order_id
)
SELECT COALESCE(actual.order_id, expected.order_id) AS order_id
FROM actual_orders AS actual
FULL OUTER JOIN (
  SELECT column0 AS order_id
  FROM VALUES (1), (2)
) AS expected
  ON actual.order_id = expected.order_id
""",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    assert test_case.expected_code in json.dumps(payload["findings"])
    assert "Inline query relation obscures data flow" in json.dumps(payload["findings"])


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("SQL function arguments are not columns", 0, "SQBRSQL027")],
    ids=lambda case: case.description,
)
def test_given_sql_function_argument_when_running_qualification_rule_then_argument_is_not_reported(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    function: Path = tmp_path / "functions" / "sql" / "orders_by_date.sql"
    function.parent.mkdir(parents=True)
    function.write_text(
        """FUNCTION (
  arguments (start_date DATE),
  returns table (order_id INTEGER)
);

SELECT current_orders.order_id
FROM current_orders
INNER JOIN order_statuses ON current_orders.order_id = order_statuses.order_id
WHERE current_orders.created_at >= start_date
""",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("table function argument preserves left alias", 0, "SQBRSQL023")],
    ids=lambda case: case.description,
)
def test_given_table_function_argument_when_running_alias_rule_then_left_alias_is_preserved(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    function: Path = tmp_path / "functions" / "sql" / "expand_order.sql"
    function.parent.mkdir(parents=True)
    function.write_text(
        """FUNCTION (
  description "Expand one order",
  arguments (order_id INTEGER),
  returns table (order_id INTEGER)
);

SELECT order_id
""",
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "expanded_orders.sql"
    model.parent.mkdir()
    model.write_text(
        """MODEL (description "Expanded orders");
SELECT expanded.order_id
FROM orders AS source_orders
CROSS JOIN __table_fn("expand_order")(source_orders.order_id) AS expanded
""",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("ceremonial SQL test passes terminal rule", 0, "SQBRSQL035")],
    ids=lambda case: case.description,
)
def test_given_ceremonial_sql_test_when_compiling_with_rule_035_then_project_is_valid(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL035"]\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        """MODEL (description "Orders");
WITH final AS (SELECT 1 AS order_id)
SELECT order_id FROM final
""",
        encoding="utf-8",
    )
    test: Path = tmp_path / "tests" / "unit" / "test_orders.sql"
    test.parent.mkdir(parents=True)
    test.write_text(
        """TEST ();
WITH
__ref__orders AS (SELECT 1 AS order_id),
__expected__orders AS (SELECT 1 AS order_id)
SELECT 1
""",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json"])

    assert exit_code == test_case.expected_exit_code
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert payload["diagnostics"] == []


@pytest.mark.parametrize(
    "test_case",
    [
        RulesIntegrationTestCase(
            "assertion and expected result must be independent",
            1,
            "expected results and assertions must be independent",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_assertion_expected_dependency_when_compiling_then_compiler_rejects_test(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id\n', encoding="utf-8")
    test: Path = tmp_path / "tests" / "unit" / "test_orders.sql"
    test.parent.mkdir(parents=True)
    test.write_text(
        """TEST ();
WITH
__ref__orders AS (SELECT 1 AS order_id),
__expected__orders AS (SELECT 1 AS order_id),
__assert__expected_is_nonempty AS (SELECT * FROM __expected__orders)
SELECT 1
""",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json"])

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    assert captured.out == ""
    assert test_case.expected_code in captured.err


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("non-source references are not source tokens", 0, "SQBRPROJECT103")],
    ids=lambda case: case.description,
)
def test_given_seed_and_function_references_when_running_source_rule_then_they_are_not_tokens(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\napproved_source_tokens = ["partner"]\n',
        encoding="utf-8",
    )
    seed: Path = tmp_path / "seeds" / "order_statuses.csv"
    seed.parent.mkdir()
    seed.write_text("status\nopen\n", encoding="utf-8")
    (tmp_path / "seeds" / "schema.yml").write_text(
        """seeds:
  - name: order_statuses
    description: Supported order statuses.
    columns:
      - name: status
        type: VARCHAR
""",
        encoding="utf-8",
    )
    function: Path = tmp_path / "functions" / "sql" / "normalize_quantity.sql"
    function.parent.mkdir(parents=True)
    function.write_text(
        """FUNCTION (
  arguments (quantity INTEGER),
  returns INTEGER,
);

quantity
""",
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "sales__stg__orders__partner.sql"
    model.parent.mkdir()
    model.write_text(
        """MODEL (description "Partner orders");
SELECT __udf("normalize_quantity")(1) AS quantity
FROM __seed("order_statuses")
""",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "test_case",
    [
        RulesIntegrationTestCase(
            "dependency import star is compatible with output-shape rule",
            0,
            "SQBRSQL021",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dependency_import_star_when_running_output_shape_rule_then_import_is_accepted(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    staging: Path = tmp_path / "models" / "stg_orders.sql"
    staging.parent.mkdir()
    staging.write_text(
        'MODEL (description "Staged orders");\nSELECT 1 AS order_id\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.write_text(
        """MODEL (description "Orders");
WITH imported_orders AS (
  SELECT *
  FROM __ref("stg_orders")
),
final AS (
  SELECT order_id
  FROM imported_orders
)
SELECT order_id
FROM final
""",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("cross join used by filter is not unused", 0, "SQBRSQL032")],
    ids=lambda case: case.description,
)
def test_given_cross_join_used_by_filter_when_running_unused_join_rule_then_no_finding_is_reported(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "recent_orders.sql"
    model.parent.mkdir()
    model.write_text(
        """MODEL (description "Recent orders");
SELECT orders.order_id
FROM orders
CROSS JOIN processing_cutoff AS cutoff
WHERE orders.created_at < cutoff.created_at
""",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("ceremonial SQL test select is ignored", 0, "SQBRSQL022")],
    ids=lambda case: case.description,
)
def test_given_ceremonial_test_select_when_running_alias_rule_then_control_projection_is_not_reported(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id\n', encoding="utf-8")
    test: Path = tmp_path / "tests" / "unit" / "orders.sql"
    test.parent.mkdir(parents=True)
    test.write_text(
        "TEST();\n\nWITH __ref__orders AS (SELECT 1 AS order_id), "
        "__expected__orders AS (SELECT 1 AS order_id)\nSELECT 1\n",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "test_case",
    [
        RulesIntegrationTestCase(
            "direct ceremonial select satisfies terminal shape", 0, "SQBRSQL035"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_ceremonial_select_when_running_terminal_rule_then_test_is_accepted(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id\n', encoding="utf-8")
    test: Path = tmp_path / "tests" / "unit" / "orders.sql"
    test.parent.mkdir(parents=True)
    test.write_text(
        "TEST();\n\nWITH __ref__orders AS (SELECT 1 AS order_id), "
        "__expected__orders AS (SELECT 1 AS order_id)\nSELECT 1\n",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("scalar subquery after prior CTE is stable", 0, "SQBRSQL022")],
    ids=lambda case: case.description,
)
def test_given_prior_cte_when_scalar_subquery_is_aliased_then_inner_aggregate_is_not_reported(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "support"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "ticket_totals.sql"
    model.parent.mkdir()
    model.write_text(
        """MODEL (description "Support ticket totals");
WITH products_used AS (
    SELECT product_id FROM products
),
ticket_totals AS (
    SELECT
        ticket.ticket_id,
        (SELECT MAX(change_id) FROM support_changes) AS latest_change_id
    FROM support_tickets AS ticket
)
SELECT * FROM ticket_totals
""",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("cast type is not a self alias", 0, "SQBRSQL016")],
    ids=lambda case: case.description,
)
def test_given_cast_and_relation_aliases_when_running_self_alias_rule_then_no_finding_is_reported(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        """MODEL (description "Orders");
SELECT CAST(orders.order_id::INTEGER AS INTEGER) AS order_id
FROM orders AS orders
""",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("upstream graph selector scopes an ignore", 1, "SQBRSQL021")],
    ids=lambda case: case.description,
)
def test_given_graph_scoped_rule_ignore_when_running_rules_then_only_matched_resources_are_ignored(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n'
        "[[rules.rule_ignores]]\n"
        'rules = ["SQBRSQL021"]\n'
        'selectors = ["+orders*"]\n'
        'reason = "Reviewed upstream interface boundary"\n',
        encoding="utf-8",
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "base_orders.sql").write_text(
        'MODEL (description "Base orders");\nSELECT 1 AS order_id\n',
        encoding="utf-8",
    )
    (models / "orders.sql").write_text(
        'MODEL (description "Orders");\nSELECT * FROM __ref("base_orders")\n',
        encoding="utf-8",
    )
    (models / "customer_orders.sql").write_text(
        'MODEL (description "Customer orders");\nSELECT * FROM __ref("orders")\n',
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            test_case.expected_code,
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    findings: list[dict[str, object]] = cast(list[dict[str, object]], payload["findings"])
    finding_paths: list[object] = [finding.get("path") for finding in findings]
    assert finding_paths == ["models/customer_orders.sql"]


@pytest.mark.parametrize(
    "test_case",
    [
        RulesIntegrationTestCase(
            "default-off custom family is explicitly selected", 1, "XSQBRARCH001"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_default_off_custom_rule_when_running_exact_and_prefix_then_both_select_rule(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n'
        "[rules.thresholds]\nmin_custom_rule_test_cases = 0\n",
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id\n', encoding="utf-8")
    rule_file: Path = tmp_path / "rules" / "architecture.py"
    rule_file.parent.mkdir()
    rule_file.write_text(
        """from sqlbuild.rules import Finding, Model, RuleContext, rule

@rule(code="XSQBRARCH001", message="Forbidden name", remediation="Rename the model.")
def forbidden_name(*, model: Model, ctx: RuleContext) -> list[Finding]:
    return [ctx.finding(subject=model)]
""",
        encoding="utf-8",
    )

    exact_exit: int = main(
        ["--project-dir", str(tmp_path), "rules", "--json", "run", "XSQBRARCH001"]
    )
    exact: dict[str, object] = json.loads(capsys.readouterr().out)
    prefix_exit: int = main(["--project-dir", str(tmp_path), "rules", "--json", "run", "XSQBRARCH"])
    prefix: dict[str, object] = json.loads(capsys.readouterr().out)

    assert exact_exit == prefix_exit == test_case.expected_exit_code
    assert exact["findings"][0]["code"] == test_case.expected_code
    assert prefix["findings"][0]["code"] == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("SQL rule exception suppresses finding", 0, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_sql_rule_exception_when_compiling_then_unified_suppression_is_applied(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n'
        '[rules]\nselect = ["SQBRSQL004"]\n\n'
        '[[rules.rule_exceptions]]\nrule = "SQBRSQL004"\n'
        'path = "models/orders.sql"\nreason = "The fixture intentionally selects one row."\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders LIMIT 1\n',
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json"])

    assert exit_code == test_case.expected_exit_code
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert test_case.expected_code not in json.dumps(payload["diagnostics"])


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("module constant edit invalidates custom rule", 0, "")],
    ids=lambda case: case.description,
)
def test_given_custom_rule_module_constant_edit_when_compiling_then_cached_result_is_invalidated(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n'
        '[rules]\nselect = ["XSQBRARCH001"]\n\n'
        "[rules.thresholds]\nmin_custom_rule_test_cases = 0\n",
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text("MODEL ();\nSELECT 1 AS order_id\n", encoding="utf-8")
    rule_file: Path = tmp_path / "rules" / "architecture.py"
    rule_file.parent.mkdir()
    rule_source: str = """from sqlbuild.rules import Finding, Model, RuleContext, rule

FORBIDDEN, UNUSED = ("orders", "unused")

@rule(code="XSQBRARCH001", message="Forbidden name", remediation="Rename the model.")
def forbidden_name(*, model: Model, ctx: RuleContext) -> list[Finding]:
    return [ctx.finding(subject=model)] if model.name == FORBIDDEN else []
"""
    rule_file.write_text(rule_source, encoding="utf-8")

    first_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    _ = capsys.readouterr()
    rule_file.write_text(
        rule_source.replace(
            'FORBIDDEN, UNUSED = ("orders", "unused")',
            'FORBIDDEN, UNUSED = ("customers", "unused")',
        ),
        encoding="utf-8",
    )
    second_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    second: dict[str, object] = json.loads(capsys.readouterr().out)

    assert first_exit == 1
    assert second_exit == test_case.expected_exit_code
    assert second["diagnostics"] == []
    assert second["compile_timings"]["rule_cache_misses"] >= 1


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("focused project cache cannot poison full compile", 0, "")],
    ids=lambda case: case.description,
)
def test_given_focused_project_rule_result_when_compiling_full_project_then_subset_cache_is_not_used(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n'
        '[rules]\nselect = ["XSQBRARCH001"]\n\n'
        "[rules.thresholds]\nmin_custom_rule_test_cases = 0\n",
        encoding="utf-8",
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "orders.sql").write_text("MODEL ();\nSELECT 1 AS order_id\n", encoding="utf-8")
    (models / "customers.sql").write_text("MODEL ();\nSELECT 1 AS customer_id\n", encoding="utf-8")
    rule_file: Path = tmp_path / "rules" / "architecture.py"
    rule_file.parent.mkdir()
    rule_file.write_text(
        """from sqlbuild.rules import Finding, Project, RuleContext, rule

@rule(code="XSQBRARCH001", message="Two models required", remediation="Add the other model.")
def two_models(*, project: Project, ctx: RuleContext) -> list[Finding]:
    del project
    return [] if len(ctx.project.models) == 2 else [ctx.finding(subject="models")]
""",
        encoding="utf-8",
    )

    focused_exit: int = main(
        ["--project-dir", str(tmp_path), "compile", "--json", "--select", "orders"]
    )
    _ = capsys.readouterr()
    full_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    full: dict[str, object] = json.loads(capsys.readouterr().out)

    assert focused_exit == 1
    assert full_exit == test_case.expected_exit_code
    assert full["diagnostics"] == []


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("default compile evaluates audit SQL", 1, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_non_model_sql_violation_when_compiling_then_compile_is_authoritative(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL004"]\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text("MODEL ();\nSELECT 1 AS order_id\n", encoding="utf-8")
    audit: Path = tmp_path / "audits" / "order_sample.sql"
    audit.parent.mkdir()
    audit.write_text('AUDIT ();\nSELECT * FROM __ref("orders") LIMIT 1\n', encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    payload: dict[str, object] = json.loads(capsys.readouterr().out)

    assert exit_code == test_case.expected_exit_code
    assert payload["diagnostics"][0]["code"] == test_case.expected_code
    assert payload["diagnostics"][0]["path"] == "audits/order_sample.sql"


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("focused compile ignores unselected exact exception", 0, "")],
    ids=lambda case: case.description,
)
def test_given_exception_for_other_model_when_compiling_selection_then_exception_is_not_stale(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL004"]\n\n'
        '[[rules.rule_exceptions]]\nrule = "SQBRSQL004"\npath = "models/customers.sql"\n'
        'reason = "The fixture intentionally selects one row."\n',
        encoding="utf-8",
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "orders.sql").write_text("MODEL ();\nSELECT 1 AS order_id\n", encoding="utf-8")
    (models / "customers.sql").write_text(
        "MODEL ();\nSELECT customer_id FROM customers LIMIT 1\n", encoding="utf-8"
    )

    exit_code: int = main(
        ["--project-dir", str(tmp_path), "compile", "--json", "--select", "orders"]
    )
    payload: dict[str, object] = json.loads(capsys.readouterr().out)

    assert exit_code == test_case.expected_exit_code
    assert payload["diagnostics"] == []


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("relative project path retains cached SQL finding", 1, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_relative_project_path_when_compiling_twice_then_sql_finding_remains_cached(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL004"]\n',
        encoding="utf-8",
    )
    model: Path = project_dir / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text("MODEL ();\nSELECT order_id FROM orders LIMIT 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    first_exit: int = main(["--project-dir", "project", "compile", "--json"])
    _ = capsys.readouterr()
    second_exit: int = main(["--project-dir", "project", "compile", "--json"])
    second: dict[str, object] = json.loads(capsys.readouterr().out)

    assert first_exit == second_exit == test_case.expected_exit_code
    assert second["diagnostics"][0]["code"] == test_case.expected_code
    assert second["compile_timings"]["rule_cache_hits"] == 1


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("unused inline suppression is diagnosed", 1, "SQBRSQL000")],
    ids=lambda case: case.description,
)
def test_given_unused_inline_suppression_when_compiling_then_stale_directive_is_reported(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL004"]\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        "MODEL ();\n-- sqb: ignore SQBRSQL004 because this fixture checks stale directives\n"
        "SELECT 1 AS order_id\n",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    payload: dict[str, object] = json.loads(capsys.readouterr().out)

    assert exit_code == test_case.expected_exit_code
    assert payload["diagnostics"][0]["code"] == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("unselected custom options validate consistently", 0, "")],
    ids=lambda case: case.description,
)
def test_given_unselected_custom_rule_options_when_compiling_then_configuration_is_validated(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = []\n\n'
        '[rules.rule_options.XSQBRARCH001]\nrequired_prefix = "order"\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text("MODEL ();\nSELECT 1 AS order_id\n", encoding="utf-8")
    rule_file: Path = tmp_path / "rules" / "architecture.py"
    rule_file.parent.mkdir()
    rule_file.write_text(
        """from sqlbuild.rules import Finding, Model, RuleContext, RuleOption, rule

REQUIRED_PREFIX = RuleOption.string(
    name="required_prefix", default="model", description="Required model prefix."
)

@rule(
    code="XSQBRARCH001",
    message="Wrong prefix",
    remediation="Rename the model.",
    options=(REQUIRED_PREFIX,),
)
def required_prefix(*, model: Model, ctx: RuleContext) -> list[Finding]:
    return [] if model.name.startswith(ctx.option(REQUIRED_PREFIX)) else [ctx.finding(subject=model)]
""",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    payload: dict[str, object] = json.loads(capsys.readouterr().out)

    assert exit_code == test_case.expected_exit_code
    assert payload["diagnostics"] == []
